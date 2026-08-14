from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    b2b_helpdesk_team_id = fields.Many2one(
        "helpdesk.team",
        string="Partner Hub Helpdesk Team",
        config_parameter="b2b_website.helpdesk_team_id",
    )
