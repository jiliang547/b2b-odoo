import hashlib
import json
import os

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import config as odoo_config

SUPPORTED_MODELS = {"gpt-4o", "gpt-4.1", "gpt-4.1-mini", "gpt-5", "gpt-5-mini"}

class Website(models.Model):
    _inherit = "website"

    b2b_ai_enabled = fields.Boolean(string="Enable Customer AI", default=True, groups="base.group_system")
    b2b_ai_initialized = fields.Boolean(copy=False, groups="base.group_system")
    b2b_ai_environment_token = fields.Char(copy=False, groups="base.group_system")
    b2b_ai_environment_authorized = fields.Boolean(
        string="AI calls authorized in this environment", compute="_compute_b2b_ai_environment_authorized",
        groups="base.group_system",
    )
    b2b_ai_agent_id = fields.Many2one(
        "ai.agent", string="Website AI Agent", groups="base.group_system",
        default=lambda self: self.env.ref("b2b_ai.customer_agent", raise_if_not_found=False),
        ondelete="restrict",
    )
    b2b_ai_user_daily_limit = fields.Integer(default=30, string="Daily requests per customer", groups="base.group_system")
    b2b_ai_daily_limit = fields.Integer(default=300, string="Daily requests per website", groups="base.group_system")
    b2b_ai_session_limit = fields.Integer(default=50, string="Projects per customer", groups="base.group_system")

    @api.model_create_multi
    def create(self, vals_list):
        websites = super().create(vals_list)
        websites.sudo()._b2b_ai_initialize()
        return websites

    def _b2b_ai_initialize(self):
        """Native installation data calls this after the default agent exists.

        Product lookup is live. Seed only already-public FAQs; do not upload
        documents, index anything, call a model or overwrite operator choices.
        """
        agent = self.env.ref("b2b_ai.customer_agent", raise_if_not_found=False)
        if not agent:
            return
        websites = self or self.search([])
        Source = self.env["b2b.ai.source"].with_context(active_test=False)
        for website in websites.filtered(lambda w: not w.b2b_ai_initialized):
            values = {"b2b_ai_initialized": True}
            if not website.b2b_ai_agent_id:
                values["b2b_ai_agent_id"] = agent.id
            website.write(values)
            faqs = self.env["b2b.faq.item"].search([
                ("active", "=", True), ("published", "=", True), ("category_id.active", "=", True),
                ("website_id", "in", [False, website.id]),
            ])
            existing = Source.search([("website_id", "=", website.id), ("faq_id", "in", faqs.ids)]).faq_id
            Source.create([{"name": faq.question, "website_id": website.id,
                            "faq_id": faq.id, "published": True} for faq in faqs - existing])

    def _b2b_ai_environment_fingerprint(self):
        # A copied authorization must not authorize a different database/stage.
        identity = [os.getenv("ODOO_STAGE", "local"), self.env.cr.dbname,
                    odoo_config["db_host"], odoo_config["db_port"],
                    self.env["ir.config_parameter"].sudo().get_param("database.uuid")]
        return hashlib.sha256(json.dumps(identity).encode()).hexdigest()

    @api.depends("b2b_ai_environment_token")
    def _compute_b2b_ai_environment_authorized(self):
        token = self._b2b_ai_environment_fingerprint()
        for website in self:
            website.b2b_ai_environment_authorized = (
                os.getenv("ODOO_STAGE") == "production" or website.b2b_ai_environment_token == token)

    def action_b2b_ai_authorize_environment(self):
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only Settings administrators can authorize AI calls."))
        self.write({"b2b_ai_environment_token": self._b2b_ai_environment_fingerprint()})
        return True

    @api.constrains("b2b_ai_user_daily_limit", "b2b_ai_daily_limit", "b2b_ai_session_limit", "b2b_ai_agent_id")
    def _check_b2b_ai_configuration(self):
        for website in self:
            if not (1 <= website.b2b_ai_user_daily_limit <= 1000
                    and 1 <= website.b2b_ai_daily_limit <= 10000
                    and 1 <= website.b2b_ai_session_limit <= 200):
                raise ValidationError(_("Set positive, bounded AI request and project limits."))
            agent = website.b2b_ai_agent_id
            if agent and (agent._get_provider() != "openai" or agent.llm_model not in SUPPORTED_MODELS or agent.topic_ids):
                raise ValidationError(_("Select an OpenAI agent without generic Topics. Website tools are controlled by Partner Hub."))

    def _b2b_ai_ready(self):
        self.ensure_one()
        config = self.sudo()
        if not config.b2b_ai_enabled:
            return "disabled"
        agent = config.b2b_ai_agent_id
        if not agent or not agent.active or agent._get_provider() != "openai" or agent.llm_model not in SUPPORTED_MODELS or agent.topic_ids:
            return "configuration_required"
        key = self.env["ir.config_parameter"].sudo().get_param("ai.openai_key") or os.getenv("ODOO_AI_CHATGPT_TOKEN")
        if not key or key == "False":
            return "key_required"
        # Check directly rather than a cached computed field after cloning.
        if (os.getenv("ODOO_STAGE") != "production"
                and config.b2b_ai_environment_token != self._b2b_ai_environment_fingerprint()):
            return "test_calls_disabled"
        return "ready"

    def action_b2b_ai_preview(self):
        self.ensure_one()
        if not self.env.user.has_group("base.group_system"):
            raise AccessError(_("Only Settings administrators can configure AI."))
        return {"type": "ir.actions.act_url", "url": "/ai-assistant", "target": "new"}


class Settings(models.TransientModel):
    _inherit = "res.config.settings"

    b2b_ai_enabled = fields.Boolean(related="website_id.b2b_ai_enabled", readonly=False)
    b2b_ai_agent_id = fields.Many2one(related="website_id.b2b_ai_agent_id", readonly=False)
    b2b_ai_user_daily_limit = fields.Integer(related="website_id.b2b_ai_user_daily_limit", readonly=False)
    b2b_ai_daily_limit = fields.Integer(related="website_id.b2b_ai_daily_limit", readonly=False)

    def set_values(self):
        # Reuse the native key field/storage. Saving a NEW key is explicit
        # authorization for this environment; an unrelated settings save in a
        # production clone must not silently authorize the inherited key.
        previous_key = self.env["ir.config_parameter"].sudo().get_param("ai.openai_key")
        result = super().set_values()
        key = self.env["ir.config_parameter"].sudo().get_param("ai.openai_key")
        if key and key != "False" and key != previous_key:
            self.env["website"].search([]).action_b2b_ai_authorize_environment()
        return result
