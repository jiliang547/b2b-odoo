from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    b2b_website_logo = fields.Binary(
        string="Partner Hub Logo",
        related="website_id.logo",
        readonly=False,
    )
    b2b_social_tiktok = fields.Char(
        string="TikTok URL",
        related="website_id.social_tiktok",
        readonly=False,
    )
    b2b_social_facebook = fields.Char(
        string="Facebook URL",
        related="website_id.social_facebook",
        readonly=False,
    )
    b2b_social_linkedin = fields.Char(
        string="LinkedIn URL",
        related="website_id.social_linkedin",
        readonly=False,
    )

    b2b_helpdesk_team_id = fields.Many2one(
        "helpdesk.team",
        string="Partner Hub Helpdesk Team",
        config_parameter="b2b_website.helpdesk_team_id",
    )
