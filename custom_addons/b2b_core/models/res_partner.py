from odoo import _, fields, models
from odoo.exceptions import AccessError


class ResPartner(models.Model):
    _inherit = "res.partner"

    b2b_segment_ids = fields.Many2many(
        "b2b.customer.segment",
        "b2b_segment_partner_rel",
        "partner_id",
        "segment_id",
        string="B2B Segments",
        tracking=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_approved = fields.Boolean(
        string="Partner Hub Approved",
        tracking=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_approval_date = fields.Datetime(
        readonly=True,
        copy=False,
        groups="b2b_core.group_b2b_manager",
    )
    b2b_approved_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        groups="b2b_core.group_b2b_manager",
    )
    b2b_erp_customer_id = fields.Char(
        string="ERP Customer ID",
        copy=False,
        index=True,
        groups="b2b_core.group_b2b_manager",
    )

    def action_b2b_approve(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can approve Partner Hub customers."))
        companies = self.mapped("commercial_partner_id")
        companies.write({
            "b2b_approved": True,
            "b2b_approval_date": fields.Datetime.now(),
            "b2b_approved_by_id": self.env.user.id,
        })
        return True

    def action_b2b_revoke(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can revoke Partner Hub access."))
        self.mapped("commercial_partner_id").write({
            "b2b_approved": False,
            "b2b_approval_date": False,
            "b2b_approved_by_id": False,
        })
        return True
