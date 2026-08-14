from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    b2b_erp_enabled = fields.Boolean(config_parameter="b2b_erp.enabled")
    b2b_erp_adapter = fields.Selection(
        [("mock", "Mock Adapter")],
        default="mock",
        required=True,
        config_parameter="b2b_erp.adapter",
    )
    b2b_erp_base_url = fields.Char(config_parameter="b2b_erp.base_url")
    b2b_erp_api_version = fields.Char(config_parameter="b2b_erp.api_version")
    b2b_erp_timeout = fields.Integer(default=15, config_parameter="b2b_erp.timeout")
    b2b_erp_retry_count = fields.Integer(default=5, config_parameter="b2b_erp.retry_count")
    b2b_erp_api_token = fields.Char(
        config_parameter="b2b_erp.api_token",
        groups="b2b_erp_connector.group_b2b_integration_manager",
    )
