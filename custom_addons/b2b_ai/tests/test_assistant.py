import json
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from ..models.service import BoundedNativeAPI


@tagged("post_install", "-at_install")
class TestPartnerAI(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.write({"b2b_ai_agent_id": cls.env.ref("b2b_ai.customer_agent").id,
                           "b2b_ai_enabled": True})
        cls.customer = cls.env["res.partner"].create({"name": "AI Approved Customer", "is_company": True, "b2b_approved": True})
        cls.user = mail_new_test_user(cls.env, login="ai-customer-test", groups="base.group_portal",
                                     partner_id=cls.env["res.partner"].create({"name": "AI Contact", "parent_id": cls.customer.id}).id)
        cls.other = mail_new_test_user(cls.env, login="ai-other-test", groups="base.group_portal",
                                      partner_id=cls.env["res.partner"].create({"name": "AI Colleague", "parent_id": cls.customer.id}).id)
        cls.service = cls.env["b2b.ai.service"].with_user(cls.user)
        cls.public_product = cls.env["product.template"].create({"name": "AI Ceiling Speaker", "sale_ok": True,
                            "is_published": True, "b2b_visibility_mode": "all", "description_sale": "A ceiling speaker for indoor use."})
        cls.hidden_product = cls.public_product.copy({"name": "Secret AI Ceiling Speaker", "b2b_visibility_mode": "hidden", "is_published": True})
        category = cls.env["b2b.faq.category"].create({"name": "AI Test Knowledge", "website_id": cls.website.id})
        faq = cls.env["b2b.faq.item"].create({"question": "How to connect Dante?", "answer": "<p>Use the documented network settings for your model.</p>", "category_id": category.id})
        cls.source = cls.env["b2b.ai.source"].create({"name": "Dante setup", "website_id": cls.website.id, "faq_id": faq.id, "published": True})
        cls.agent = cls.env.ref("b2b_ai.customer_agent")

    def _project(self):
        return self.service._new(self.website, "advisor")

    def _ask(self, session, website, text, key, revision):
        """Drive both durable phases in one test transaction (no cron commit)."""
        self.service._enqueue(session, website, text, key, revision)
        turn = session.turn_ids.filtered(lambda t: t.request_key == key)
        if turn.state == "queued":
            turn.write({"state": "running", "started_at": fields.Datetime.now()})
            self.service._process_turn(turn)
        return self.service._view(session, website)

    def test_queue_is_durable_and_idempotent_without_calling_model(self):
        session = self.service._new(self.website)
        self.assertEqual(session.mode, "assistant")
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"), \
                patch.object(type(self.service), "_json_call") as call:
            result = self.service._enqueue(session, self.website, "Dante question", "queued-request-00001", 0)
            self.assertEqual(result["turns"][0]["state"], "queued")
            self.service._enqueue(session, self.website, "Dante question", "queued-request-00001", 0)
            self.assertEqual(len(session.turn_ids), 1)
            with self.assertRaises(ValidationError):
                self.service._enqueue(session, self.website, "Different question", "queued-request-00001", 1)
            with self.assertRaises(UserError):
                self.service._enqueue(session, self.website, "Another question", "queued-request-00002", 1)
            with self.assertRaises(UserError):
                self.service._update_facts(session, self.website, 1, {})
            call.assert_not_called()

    def test_worker_drops_superuser_and_claim_is_committed_first(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            self.service._enqueue(session, self.website, "Dante", "queued-request-00003", 0)
        events = []
        def process(service, turn):
            self.assertEqual(service.env.uid, self.user.id)
            self.assertFalse(service.env.su)
            self.assertEqual(turn.state, "running")
            self.assertTrue(turn.started_at)
            self.assertEqual(events, ["commit"])
            events.append("process")
            turn.write({"state": "failed"})
        def commit(*args, **kwargs):
            events.append("commit")
            return 100
        with patch.object(type(self.service), "_process_turn", process), \
                patch.object(type(self.env["ir.cron"]), "_commit_progress", side_effect=commit):
            self.env["b2b.ai.turn"]._cron_process_queue()
        self.assertEqual(events, ["commit", "process", "commit"])

    def test_archived_queue_never_calls_model(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"), \
                patch.object(type(self.service), "_json_call") as call:
            self.service._enqueue(session, self.website, "Dante", "queued-request-00004", 0)
            turn = session.turn_ids
            turn.state = "running"
            session.active = False
            with self.assertLogs("odoo.addons.b2b_ai.models.service", level="WARNING") as logs:
                self.env["b2b.ai.turn"]._run_claimed(turn)
            self.assertEqual([record.getMessage() for record in logs.records],
                             [f"Partner Hub AI request {turn.id} failed (AccessError)"])
            self.assertEqual(turn.state, "failed")
            call.assert_not_called()

    def test_key_removed_after_queue_never_calls_model(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            self.service._enqueue(session, self.website, "Dante", "queued-request-00005", 0)
        turn = session.turn_ids
        turn.state = "running"
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="key_required"), \
                patch.object(type(self.service), "_json_call") as call:
            with self.assertLogs("odoo.addons.b2b_ai.models.service", level="WARNING") as logs:
                self.env["b2b.ai.turn"]._run_claimed(turn)
            self.assertEqual([record.getMessage() for record in logs.records],
                             [f"Partner Hub AI request {turn.id} failed (AccessError)"])
            self.assertEqual(turn.state, "failed")
            call.assert_not_called()

    def test_interrupted_turn_expires_without_automatic_replay(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            self.service._enqueue(session, self.website, "Dante", "queued-request-00006", 0)
        turn = session.turn_ids
        turn.write({"state": "running", "started_at": fields.Datetime.now() - timedelta(minutes=6)})
        with patch.object(type(self.service), "_json_call") as call:
            self.env["b2b.ai.turn"]._expire_interrupted()
            self.env["b2b.ai.turn"]._run_claimed(turn)
            self.assertEqual(turn.state, "failed")
            self.assertEqual(turn.error_code, "interrupted")
            call.assert_not_called()

    def test_company_colleague_cannot_read_project(self):
        session = self._project()
        with self.assertRaises(AccessError):
            session._assert_owner(self.other, self.website)
        with self.assertRaises(AccessError):
            session.with_user(self.user).read(["facts"])

    def test_configuration_action_opens_existing_websites_first(self):
        action = self.env.ref("b2b_ai.website_ai_action")
        self.assertEqual(action.views[0][1], "list")

    def test_faq_selector_displays_question_not_internal_record_id(self):
        self.assertEqual(self.source.faq_id.display_name, self.source.faq_id.question)

    def test_public_cannot_create_project(self):
        with self.assertRaises(AccessError):
            self.service.with_user(self.env.ref("base.public_user"))._new(self.website, "advisor")

    def test_approval_change_invalidates_project(self):
        session = self._project()
        self.customer.b2b_approved = False
        with self.assertRaises(AccessError):
            session._assert_owner(self.user, self.website)

    def test_product_retrieval_excludes_hidden(self):
        evidence, products, _ = self.service._retrieve("AI Ceiling Speaker", self.website, self.agent)
        self.assertIn(self.public_product.id, products.ids)
        self.assertNotIn(self.hidden_product.id, products.ids)
        self.assertNotIn(f"P:{self.hidden_product.id}", evidence)

    def test_retrieval_without_optional_taxonomy_permission(self):
        application = self.env["b2b.product.application"]
        with patch.object(type(application), "has_access", return_value=False):
            evidence, products, _ = self.service._retrieve("AI Ceiling Speaker", self.website, self.agent)
        self.assertIn(self.public_product.id, products.ids)
        self.assertNotIn(f"P:{self.hidden_product.id}", evidence)

    def test_faq_must_be_explicitly_approved(self):
        evidence, _, _ = self.service._retrieve("Dante", self.website, self.agent)
        self.assertIn(f"S:{self.source.id}", evidence)
        self.source.published = False
        evidence, _, _ = self.service._retrieve("Dante", self.website, self.agent)
        self.assertNotIn(f"S:{self.source.id}", evidence)

    def test_cross_website_source_denied(self):
        other_site = self.env["website"].create({"name": "Other AI Site", "company_id": self.website.company_id.id})
        self.assertFalse(self.source._allowed_for(self.user, other_site))

    def test_invalid_citation_and_unknown_product_rejected(self):
        evidence = {"S:1": {"text": "A speaker for indoor use."}}
        good = {"points": [{"text": "Indoor speaker.", "source_id": "S:1", "evidence_quote": "speaker for indoor use"}], "product_ids": [], "question": ""}
        self.service._validate_answer(good, evidence, self.public_product)
        bad = dict(good, product_ids=[self.hidden_product.id])
        with self.assertRaises(ValueError):
            self.service._validate_answer(bad, evidence, self.public_product)
        bad = dict(good, points=[{"text": "Certified for life safety.", "source_id": "S:1", "evidence_quote": "certified"}])
        with self.assertRaises(ValueError):
            self.service._validate_answer(bad, evidence, self.public_product)

    def test_project_facts_revision_and_validation(self):
        session = self._project()
        self.service._update_facts(session, self.website, 0, {"zones": "24 classrooms"})
        self.assertEqual(session.facts["zones"], "24 classrooms")
        with self.assertRaises(UserError):
            self.service._update_facts(session, self.website, 0, {})
        with self.assertRaises(ValidationError):
            self.service._update_facts(session, self.website, 1, {"price": "0"})

    def test_unconfigured_provider_does_not_call_model(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="key_required"), patch.object(type(self.service), "_json_call") as call:
            with self.assertRaises(UserError):
                self._ask(session, self.website, "Need speaker", "test-request-00001", 0)
            call.assert_not_called()

    def test_success_idempotency_and_explicit_fact_preservation(self):
        session = self._project()
        session.facts = {"zones": "24 classrooms"}
        evidence = {f"S:{self.source.id}": {"text": "Use the documented network settings for your model."}}
        plan = {"query": "Dante", "facts": [{"key": "zones", "value": "12 rooms", "source_quote": "12 rooms"}]}
        answer = {"points": [{"text": "Check the documented settings.", "source_id": f"S:{self.source.id}", "evidence_quote": "documented network settings"}], "product_ids": [], "question": "Which model?"}
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"), \
                patch.object(type(self.service), "_json_call", side_effect=[plan, answer]) as call, \
                patch.object(type(self.service), "_retrieve", return_value=(evidence, self.public_product, self.source)), \
                patch.object(type(self.service), "_cards", return_value=[]):
            self._ask(session, self.website, "Dante for 12 rooms", "test-request-00002", 0)
            self.assertEqual(session.turn_ids.state, "done")
            self.assertEqual(session.facts["zones"], "24 classrooms")
            self._ask(session, self.website, "Dante for 12 rooms", "test-request-00002", 0)
            self.assertEqual(call.call_count, 2)
            self.assertEqual(len(session.turn_ids), 1)

    def test_provider_failure_is_recorded_without_raw_error(self):
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"), \
                patch.object(type(self.service), "_json_call", side_effect=UserError("secret provider error")), \
                patch.object(type(self.service), "_cards", return_value=[]):
            # Capture expected failure logs without hiding real runtime warnings.
            with self.assertLogs("odoo.addons.b2b_ai.models.service", level="WARNING") as logs:
                result = self._ask(session, self.website, "Need speaker", "test-request-00003", 0)
        self.assertEqual([record.getMessage() for record in logs.records],
                         [f"Partner Hub AI request {session.turn_ids.id} failed (UserError)"])
        self.assertEqual(session.turn_ids.state, "failed")
        self.assertNotIn("secret provider", json.dumps(result))

    def test_result_only_lists_cited_and_still_authorized_resources(self):
        session = self._project()
        turn = self.env["b2b.ai.turn"].create({"session_id": session.id, "request_key": "resource-test-00001",
            "input_digest": "test", "user_text": "Dante", "state": "done",
            "result": {"source_ids": self.source.ids, "points": [], "product_ids": []}})
        self.assertEqual(turn._public_result(self.service, self.website)["answer"]["sources"], [])
        turn.result = dict(turn.result, points=[{"text": "Check settings", "source_id": f"S:{self.source.id}",
                                              "evidence_quote": "documented network settings"}])
        self.assertEqual(len(turn._public_result(self.service, self.website)["answer"]["sources"]), 1)
        self.source.published = False
        answer = turn._public_result(self.service, self.website)["answer"]
        self.assertEqual(answer["sources"], [])
        self.assertEqual(answer["points"], [])

    def test_archiving_project_does_not_reset_daily_quota(self):
        self.website.b2b_ai_user_daily_limit = 1
        session = self._project()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"), \
                patch.object(type(self.service), "_json_call", side_effect=ValueError("test")), \
                patch.object(type(self.service), "_cards", return_value=[]):
            with self.assertLogs("odoo.addons.b2b_ai.models.service", level="WARNING") as logs:
                self._ask(session, self.website, "Need speaker", "test-request-00004", 0)
            self.assertEqual([record.getMessage() for record in logs.records],
                             [f"Partner Hub AI request {session.turn_ids.id} failed (ValueError)"])
            session.active = False
            second = self._project()
            with self.assertRaisesRegex(UserError, "daily assistant limit"):
                self._ask(second, self.website, "Need speaker", "test-request-00005", 0)

    def test_native_transport_is_bounded_and_not_stored(self):
        from odoo.addons.ai.utils.llm_api_service import LLMApiService
        body = {}
        with patch.object(LLMApiService, "_request", return_value={"status": "completed"}) as call:
            BoundedNativeAPI(self.env)._request(method="post", endpoint="/responses", headers={}, body=body)
            self.assertEqual(call.call_args.kwargs["timeout"], 20)
            self.assertEqual(body["max_output_tokens"], 1600)
            self.assertFalse(body["store"])

    def test_native_price_payload_is_reused(self):
        product_service = self.env["b2b.product.service"].with_user(self.user)
        pricelist = self.env["product.pricelist"].search([], limit=1)
        with MockRequest(self.service.env, website=self.website) as http_request, \
                patch.object(type(product_service), "price_payload", return_value={self.public_product.id: {"state": "visible", "price": 123.45, "currency": self.website.currency_id}}) as native:
            http_request.pricelist = pricelist
            cards = self.service._cards([self.public_product.id, self.hidden_product.id], self.website)
            self.assertEqual(len(cards), 1)
            self.assertIn("123.45", cards[0]["price"])
            native.assert_called_once()

    def _document_source(self, visibility="product"):
        document = self.env["product.document"].create({
            "name": "AI Test Datasheet.txt", "res_model": "product.template", "res_id": self.public_product.id,
            "raw": b"The AI ceiling speaker uses documented indoor mounting.", "mimetype": "text/plain",
            "shown_on_product_page": True, "b2b_visibility_mode": visibility,
        })
        source = self.env["b2b.ai.source"].create({"name": "AI Test Datasheet", "website_id": self.website.id,
                                                "product_document_id": document.id, "published": True})
        return document, source

    def test_native_index_does_not_reparent_original_product_file(self):
        document, source = self._document_source()
        original = document.ir_attachment_id
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            source.action_index()
        self.assertEqual(original.res_model, "product.template")
        self.assertEqual(original.res_id, self.public_product.id)
        self.assertNotEqual(original.id, source.native_source_id.attachment_id.id)
        self.assertEqual(source.indexed_checksum, original.checksum)
        self.assertFalse(source.native_source_id.attachment_id.public)

    def test_internal_document_is_never_sent_for_retrieval(self):
        _, source = self._document_source("internal")
        self.assertFalse(source._allowed_for(self.user, self.website))

    def test_changed_product_file_invalidates_old_index(self):
        document, source = self._document_source()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            source.action_index()
        self.assertTrue(self.service._sources_by_ids(source.ids, self.website))
        document.raw = b"Updated content requires a fresh native index."
        self.assertFalse(self.service._sources_by_ids(source.ids, self.website))

    def test_vector_retrieval_uses_native_chunks_and_authorized_source_link(self):
        document, source = self._document_source()
        with patch.object(type(self.website), "_b2b_ai_ready", return_value="ready"):
            source.action_index()
        vector = [1.0] + [0.0] * 1535
        self.env["ai.embedding"].create({"attachment_id": source.native_source_id.attachment_id.id,
            "content": "The AI ceiling speaker uses documented indoor mounting.",
            "embedding_model": "text-embedding-3-small", "embedding_vector": vector})
        source.native_source_id.write({"status": "indexed", "is_active": True})
        with patch.object(BoundedNativeAPI, "get_embedding", return_value={"data": [{"embedding": vector}]}):
            evidence, _, found = self.service._retrieve("mounting", self.website, self.agent)
        self.assertIn(f"S:{source.id}", evidence)
        self.assertIn(source.id, found.ids)
        self.assertEqual(self.service._source_links(source)[0]["url"], f"/resources/{document.id}")

    def test_monetary_model_content_rejected_even_with_valid_quote(self):
        evidence = {"S:1": {"text": "The price is USD 5.00."}}
        output = {"points": [{"text": "The price is USD 5.00.", "source_id": "S:1", "evidence_quote": "The price is USD 5.00."}], "product_ids": [], "question": ""}
        with self.assertRaises(ValueError):
            self.service._validate_answer(output, evidence, self.public_product)

    def test_two_customer_types_get_their_native_prices_without_mocking(self):
        self.website.b2b_price_display_mode = "approved"
        self.public_product.taxes_id = False
        self.public_product.b2b_default_moq = 2
        second_company = self.env["res.partner"].create({"name": "AI Second Customer", "is_company": True, "b2b_approved": True})
        self.other.partner_id.parent_id = second_company
        values = []
        for user, company, amount in [(self.user, self.customer, 71.25), (self.other, second_company, 89.50)]:
            pricelist = self.env["product.pricelist"].create({"name": company.name + " AI Base", "currency_id": self.website.currency_id.id,
                "item_ids": [Command.create({"compute_price": "fixed", "fixed_price": amount})]})
            customer_type = self.env["b2b.customer.type"].create({"name": company.name + " AI Type"})
            self.env["b2b.customer.type.pricelist"].create({"customer_type_id": customer_type.id, "website_id": self.website.id, "pricelist_id": pricelist.id})
            company.b2b_customer_type_id = customer_type
            effective = company._b2b_get_effective_pricelist(self.website, pricelist.currency_id)
            service = self.service.with_user(user)
            website = self.website.with_user(user)
            with MockRequest(service.env, website=website, website_sale_current_pl=effective.id) as http_request:
                self.assertEqual(http_request.pricelist, effective)
                card = service._cards(self.public_product.ids, website)[0]
                self.assertIn(f"{amount:.2f}", card["price"])
                self.assertEqual(card["moq"], 2)
                values.append(card["price"])
        self.assertNotEqual(*values)
