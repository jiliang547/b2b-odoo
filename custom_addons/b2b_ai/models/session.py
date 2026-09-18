import hashlib
import json
from datetime import timedelta

from odoo import fields, models
from odoo.exceptions import AccessError, ValidationError


class AISession(models.Model):
    _name = "b2b.ai.session"
    _description = "Partner Hub AI Project"
    _inherit = ["mail.thread"]
    _order = "write_date desc, id desc"

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    owner_id = fields.Many2one("res.users", required=True, ondelete="cascade", index=True)
    commercial_partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade")
    website_id = fields.Many2one("website", required=True, ondelete="cascade", index=True)
    mode = fields.Selection([("assistant", "Assistant"), ("advisor", "Product Advisor"), ("knowledge", "Knowledge Base")], required=True, default="assistant")
    facts = fields.Json(default=dict)
    revision = fields.Integer(default=0)
    audience_signature = fields.Char(required=True)
    turn_ids = fields.One2many("b2b.ai.turn", "session_id")

    def _assert_owner(self, user, website):
        self.ensure_one()
        if (not self.active or user._is_public() or self.owner_id != user or self.website_id != website
                or self.commercial_partner_id != user.partner_id.commercial_partner_id):
            raise AccessError("This AI project is not available.")
        if self.audience_signature != self._audience(user, website):
            raise AccessError("Your account access has changed. Please start a new AI project.")

    def _audience(self, user, website):
        partner = user.partner_id.commercial_partner_id.sudo()
        value = [user.id, partner.id, website.id, bool(partner.b2b_approved),
                 sorted(partner.b2b_segment_ids.ids), sorted(user.group_ids.ids)]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()


class AITurn(models.Model):
    _name = "b2b.ai.turn"
    _description = "Partner Hub AI Request"
    _order = "id"

    session_id = fields.Many2one("b2b.ai.session", required=True, ondelete="cascade", index=True)
    request_key = fields.Char(required=True)
    input_digest = fields.Char(required=True)
    user_text = fields.Text(required=True)
    result = fields.Json(default=dict)
    state = fields.Selection([("queued", "Queued"), ("running", "Running"), ("done", "Completed"), ("failed", "Failed")], default="queued", required=True, index=True)
    started_at = fields.Datetime()
    request_lang = fields.Char()
    error_code = fields.Char()
    _request_unique = models.Constraint("UNIQUE(session_id, request_key)", "This request has already been submitted.")

    def _expire_interrupted(self):
        now = fields.Datetime.now()
        self.sudo().search([
            "|", "&", ("state", "=", "running"), "|", ("started_at", "<", now - timedelta(minutes=5)),
            "&", ("started_at", "=", False), ("create_date", "<", now - timedelta(minutes=5)),
            "&", ("state", "=", "queued"), ("create_date", "<", now - timedelta(minutes=10)),
        ]).write({"state": "failed", "error_code": "interrupted"})

    def _cron_process_queue(self):
        """Native cron owns this cursor. Persist the claim BEFORE the paid call.

        Interrupted calls are failed, never automatically replayed: a provider
        may have charged even if its response was lost. No web-request thread.
        """
        self._expire_interrupted()
        cron = self.env["ir.cron"]
        for _ in range(3):
            self.env.cr.execute("SELECT id FROM b2b_ai_turn WHERE state='queued' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1")
            row = self.env.cr.fetchone()
            if not row:
                break
            turn = self.sudo().browse(row[0])
            turn.write({"state": "running", "started_at": fields.Datetime.now()})
            cron._commit_progress(remaining=self.search_count([("state", "=", "queued")]) + 1)
            self._run_claimed(turn)
            if not cron._commit_progress(1):
                break

    def _run_claimed(self, turn):
        owner = turn.session_id.owner_id
        # Explicitly drop superuser privileges before product/knowledge lookup.
        service = self.env["b2b.ai.service"].with_user(owner).with_context(
            allowed_company_ids=owner.company_ids.ids, lang=turn.request_lang or owner.lang or "en_US")
        service._process_turn(turn)

    def _public_result(self, service, website):
        self.ensure_one()
        result = dict(self.result or {})
        # Prices and permissions are re-evaluated, including for repeated requests.
        allowed_ids = service._products_by_ids(result.get("product_ids", []), website).ids
        sources = service._sources_by_ids(result.get("source_ids", []), website)
        valid_keys = {f"P:{id_}" for id_ in allowed_ids} | {f"S:{s.id}" for s in sources}
        result["points"] = [p for p in result.get("points", []) if p.get("source_id") in valid_keys]
        result["products"] = service._cards(allowed_ids, website)
        cited = {p.get("source_id") for p in result["points"]}
        result["sources"] = service._source_links(sources.filtered(lambda s: f"S:{s.id}" in cited))
        result.pop("product_ids", None)
        result.pop("source_ids", None)
        return {"id": self.id, "question": self.user_text, "state": self.state,
                "error_code": self.error_code or "", "answer": result}
