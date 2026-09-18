import os
from unittest.mock import patch

from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestAIInstallation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.website = self.env["website"].search([], limit=1)
        self.parameters = self.env["ir.config_parameter"].sudo()

    def test_existing_site_initialized_without_manual_agent_selection(self):
        self.assertTrue(self.website.b2b_ai_initialized)
        self.assertTrue(self.website.b2b_ai_agent_id)
        self.assertEqual(self.website.b2b_ai_agent_id._get_provider(), "openai")

    def test_new_site_defaults_and_idempotent_upgrade_preserve_choices(self):
        site = self.env["website"].create({"name": "AI Bootstrap Test"})
        self.assertTrue(site.b2b_ai_enabled)
        self.assertTrue(site.b2b_ai_initialized)
        self.assertEqual(site.b2b_ai_agent_id, self.env.ref("b2b_ai.customer_agent"))
        site.write({"b2b_ai_enabled": False, "b2b_ai_agent_id": False, "b2b_ai_user_daily_limit": 17})
        site._b2b_ai_initialize()
        self.assertFalse(site.b2b_ai_enabled)
        self.assertFalse(site.b2b_ai_agent_id)
        self.assertEqual(site.b2b_ai_user_daily_limit, 17)

    def test_bootstrap_public_faq_only_and_never_reapproves_disabled_source(self):
        category = self.env["b2b.faq.category"].create({"name": "AI Bootstrap FAQ", "website_id": self.website.id})
        other_site = self.env["website"].create({"name": "Other AI Bootstrap Test"})
        other_category = self.env["b2b.faq.category"].create({"name": "Other FAQs", "website_id": other_site.id})
        faqs = self.env["b2b.faq.item"].create([
            {"question": "Public bootstrap", "answer": "<p>Public answer</p>", "category_id": category.id},
            {"question": "Draft bootstrap", "answer": "<p>Draft answer</p>", "category_id": category.id, "published": False},
            {"question": "Archived bootstrap", "answer": "<p>Archived answer</p>", "category_id": category.id, "active": False},
            {"question": "Other website", "answer": "<p>Other answer</p>", "category_id": other_category.id},
        ])
        self.website.b2b_ai_initialized = False
        self.website._b2b_ai_initialize()
        sources = self.env["b2b.ai.source"].search([("website_id", "=", self.website.id), ("faq_id", "in", faqs.ids)])
        self.assertEqual(sources.faq_id, faqs[0])
        self.assertTrue(sources.published)
        sources.published = False
        self.website.b2b_ai_initialized = False
        self.website._b2b_ai_initialize()
        self.assertFalse(sources.published)
        self.assertEqual(self.env["b2b.ai.source"].search_count([("website_id", "=", self.website.id), ("faq_id", "=", faqs[0].id)]), 1)

    def test_saving_native_key_is_the_only_first_time_setup_step(self):
        self.parameters.set_param("ai.openai_key", False)
        self.website.write({"b2b_ai_enabled": True, "b2b_ai_environment_token": False})
        with patch.dict(os.environ, {"ODOO_STAGE": "staging", "ODOO_AI_CHATGPT_TOKEN": ""}):
            self.assertEqual(self.website._b2b_ai_ready(), "key_required")
            settings = self.env["res.config.settings"].create({"openai_key": "non-live-installation-test-key", "openai_key_enabled": True})
            settings.set_values()
            self.assertEqual(self.parameters.get_param("ai.openai_key"), "non-live-installation-test-key")
            self.assertEqual(self.website._b2b_ai_ready(), "ready")

    def test_production_key_ready_but_copy_to_staging_not_authorized(self):
        self.parameters.set_param("ai.openai_key", "non-live-installation-test-key")
        self.website.write({"b2b_ai_enabled": True, "b2b_ai_environment_token": False})
        with patch.dict(os.environ, {"ODOO_STAGE": "production"}):
            self.assertEqual(self.website._b2b_ai_ready(), "ready")
            self.website.action_b2b_ai_authorize_environment()
        with patch.dict(os.environ, {"ODOO_STAGE": "staging"}):
            self.assertEqual(self.website._b2b_ai_ready(), "test_calls_disabled")
            # An unrelated Settings save must not authorize the copied key.
            self.env["res.config.settings"].create({}).set_values()
            self.assertEqual(self.website._b2b_ai_ready(), "test_calls_disabled")
            self.website.action_b2b_ai_authorize_environment()
            self.assertEqual(self.website._b2b_ai_ready(), "ready")

    def test_key_does_not_override_explicit_disable(self):
        self.parameters.set_param("ai.openai_key", False)
        self.website.b2b_ai_enabled = False
        self.env["res.config.settings"].create({"openai_key": "non-live-installation-test-key"}).set_values()
        self.assertEqual(self.website._b2b_ai_ready(), "disabled")

    def test_customer_cannot_authorize_model_spending(self):
        with self.assertRaises(AccessError):
            self.website.with_user(self.env.ref("base.public_user")).action_b2b_ai_authorize_environment()

    def test_missing_key_stays_disabled_even_after_environment_authorization(self):
        self.parameters.set_param("ai.openai_key", False)
        self.website.b2b_ai_enabled = True
        self.website.action_b2b_ai_authorize_environment()
        with patch.dict(os.environ, {"ODOO_AI_CHATGPT_TOKEN": ""}):
            self.assertEqual(self.website._b2b_ai_ready(), "key_required")

    def test_settings_admin_can_save_native_key_without_erp_permissions(self):
        admin = mail_new_test_user(self.env, login="ai-settings-admin-only", groups="base.group_system")
        self.assertFalse(admin.has_group("b2b_erp_connector.group_b2b_integration_manager"))
        self.parameters.set_param("ai.openai_key", False)
        self.parameters.set_param("b2b_erp.api_token", "private-erp-test-token")
        settings = self.env["res.config.settings"].with_user(admin).create({
            "openai_key": "non-live-installation-test-key", "openai_key_enabled": True,
        })
        with self.assertRaises(AccessError):
            settings.read(["b2b_erp_api_token"])
        with self.assertRaises(AccessError):
            settings.write({"b2b_erp_api_token": "unauthorized-replacement"})
        settings.set_values()
        self.assertEqual(self.parameters.get_param("ai.openai_key"), "non-live-installation-test-key")
        self.assertEqual(self.parameters.get_param("b2b_erp.api_token"), "private-erp-test-token")
