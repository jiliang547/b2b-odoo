from odoo import _, Command, api, fields, models
from odoo.exceptions import AccessError


_B2B_APPROVAL_WRITE_TOKEN = object()


class ResPartner(models.Model):
    _inherit = "res.partner"

    _B2B_APPROVAL_FIELDS = frozenset({
        "b2b_approved",
        "b2b_approval_date",
        "b2b_approved_by_id",
    })
    _B2B_MANAGER_FIELDS = frozenset({
        "b2b_segment_ids",
        "b2b_erp_customer_id",
        "b2b_customer_type_id",
    })
    _B2B_COMMERCIAL_ONLY_FIELDS = _B2B_APPROVAL_FIELDS | _B2B_MANAGER_FIELDS

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
    b2b_product_interest_id = fields.Many2one(
        "res.partner.category",
        string="Products of Interest",
        tracking=True,
        groups="b2b_core.group_b2b_operator",
        help="Primary product family selected during Partner Hub registration.",
    )
    b2b_mobile_whatsapp = fields.Char(
        string="Mobile / WhatsApp",
        tracking=True,
        groups="b2b_core.group_b2b_operator",
        help="Direct mobile or WhatsApp number supplied by the Partner Hub contact.",
    )
    b2b_is_commercial_entity = fields.Boolean(
        string="Is Partner Hub Commercial Entity",
        compute="_compute_b2b_is_commercial_entity",
    )
    b2b_effective_approved = fields.Boolean(
        string="Effective Partner Hub Approved",
        related="commercial_partner_id.b2b_approved",
        readonly=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_effective_segment_ids = fields.Many2many(
        string="Effective B2B Segments",
        related="commercial_partner_id.b2b_segment_ids",
        readonly=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_effective_erp_customer_id = fields.Char(
        string="Effective ERP Customer ID",
        related="commercial_partner_id.b2b_erp_customer_id",
        readonly=True,
        groups="b2b_core.group_b2b_manager",
    )
    b2b_effective_approval_date = fields.Datetime(
        string="Approval Date",
        related="commercial_partner_id.b2b_approval_date",
        readonly=True,
        groups="b2b_core.group_b2b_manager",
    )
    b2b_effective_approved_by_id = fields.Many2one(
        "res.users",
        string="Approved By",
        related="commercial_partner_id.b2b_approved_by_id",
        readonly=True,
        groups="b2b_core.group_b2b_manager",
    )

    @api.depends("commercial_partner_id")
    def _compute_b2b_is_commercial_entity(self):
        for partner in self:
            partner.b2b_is_commercial_entity = (
                partner.commercial_partner_id == partner
            )

    @api.model
    def _b2b_check_sensitive_partner_values(self, vals, *, creating=False):
        """Keep B2B authorization valid outside the form view as well."""
        if self.env.su:
            return

        keys = set(vals)
        commercial_only_fields = keys & self._B2B_COMMERCIAL_ONLY_FIELDS
        if commercial_only_fields:
            if creating:
                parent = self.env["res.partner"].browse(vals.get("parent_id")).exists()
                is_child = bool(parent and parent.commercial_partner_id)
            else:
                is_child = any(
                    partner.commercial_partner_id != partner for partner in self
                )
            if is_child:
                raise AccessError(_(
                    "Partner Hub approval, customer type, segments, and ERP customer data must "
                    "be maintained on the commercial company record."
                ))

        approval_fields = keys & self._B2B_APPROVAL_FIELDS
        approval_write = (
            self.env.context.get("_b2b_approval_write_token")
            is _B2B_APPROVAL_WRITE_TOKEN
        )
        if approval_fields and not approval_write:
            # Explicit false defaults are harmless when a contact is created.
            if not creating or any(vals.get(field_name) for field_name in approval_fields):
                raise AccessError(_(
                    "Partner Hub approval must be changed with the Approve or Revoke action."
                ))

        is_manager = self.env.user.has_group("b2b_core.group_b2b_manager")
        if keys & self._B2B_MANAGER_FIELDS and not is_manager:
            raise AccessError(_(
                "Only a B2B Manager can maintain customer type, segments, and ERP customer data."
            ))

        if "property_product_pricelist" in keys and not (
            is_manager
            or self.env.user.has_group("b2b_core.group_b2b_special_price_manager")
            or self.env.user.has_group("base.group_system")
        ):
            raise AccessError(_(
                "Only a B2B Manager or B2B Special Price Manager can assign customer pricelists."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._b2b_check_sensitive_partner_values(vals, creating=True)
        return super().create(vals_list)

    def write(self, vals):
        self._b2b_check_sensitive_partner_values(vals)
        result = super().write(vals)
        if vals.get("parent_id"):
            # A contact that joins a company immediately adopts that company's
            # commercial policy. Remove dormant contact-level values so they
            # cannot unexpectedly become active if the contact is detached.
            linked_contacts = self.filtered(
                lambda partner: partner.commercial_partner_id != partner
            )
            if linked_contacts:
                linked_contacts.sudo().with_context(
                    _b2b_approval_write_token=_B2B_APPROVAL_WRITE_TOKEN
                ).write({
                    "b2b_approved": False,
                    "b2b_approval_date": False,
                    "b2b_approved_by_id": False,
                    "b2b_segment_ids": [Command.clear()],
                    "b2b_erp_customer_id": False,
                    "b2b_customer_type_id": False,
                })
                linked_contacts.mapped("b2b_pricelist_override_ids").sudo().unlink()
        return result

    def action_b2b_approve(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can approve Partner Hub customers."))
        companies = self.mapped("commercial_partner_id")
        companies.with_context(
            _b2b_approval_write_token=_B2B_APPROVAL_WRITE_TOKEN
        ).write({
            "b2b_approved": True,
            "b2b_approval_date": fields.Datetime.now(),
            "b2b_approved_by_id": self.env.user.id,
        })
        return True

    def action_b2b_revoke(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can revoke Partner Hub access."))
        self.mapped("commercial_partner_id").with_context(
            _b2b_approval_write_token=_B2B_APPROVAL_WRITE_TOKEN
        ).write({
            "b2b_approved": False,
            "b2b_approval_date": False,
            "b2b_approved_by_id": False,
        })
        return True
