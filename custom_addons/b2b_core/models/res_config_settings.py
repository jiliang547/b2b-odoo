from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    b2b_price_display_mode = fields.Selection(
        related="website_id.b2b_price_display_mode", readonly=False
    )
    b2b_guest_price_state = fields.Selection(
        related="website_id.b2b_guest_price_state", readonly=False
    )
    b2b_no_price_state = fields.Selection(
        related="website_id.b2b_no_price_state", readonly=False
    )
    b2b_require_approved_checkout = fields.Boolean(
        related="website_id.b2b_require_approved_checkout", readonly=False
    )
    b2b_require_approved_sample = fields.Boolean(
        related="website_id.b2b_require_approved_sample", readonly=False
    )
