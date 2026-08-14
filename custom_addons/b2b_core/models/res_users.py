from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    b2b_partner_approved = fields.Boolean(
        related="partner_id.commercial_partner_id.b2b_approved",
        string="Partner Hub Company Approved",
        readonly=True,
    )
    b2b_partner_segment_ids = fields.Many2many(
        related="partner_id.commercial_partner_id.b2b_segment_ids",
        string="Partner Hub Company Segments",
        readonly=True,
    )
