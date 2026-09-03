from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class B2BCustomerType(models.Model):
    _name = "b2b.customer.type"
    _description = "B2B Customer Type"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, index="trigram")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    pricelist_mapping_ids = fields.One2many(
        "b2b.customer.type.pricelist",
        "customer_type_id",
        string="Base Pricelists",
    )
    partner_count = fields.Integer(compute="_compute_partner_count")

    _name_unique = models.Constraint(
        "UNIQUE (name)", "Customer type names must be unique."
    )

    def _compute_partner_count(self):
        grouped = self.env["res.partner"]._read_group(
            [("b2b_customer_type_id", "in", self.ids)],
            groupby=["b2b_customer_type_id"],
            aggregates=["__count"],
        )
        counts = {customer_type.id: count for customer_type, count in grouped}
        for customer_type in self:
            customer_type.partner_count = counts.get(customer_type.id, 0)

    def action_view_partners(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("base.action_partner_form")
        action["domain"] = [("b2b_customer_type_id", "=", self.id)]
        return action

    @api.ondelete(at_uninstall=False)
    def _unlink_except_configured_types(self):
        if self.pricelist_mapping_ids:
            raise ValidationError(_(
                "Archive customer types instead of deleting types that have base pricelists."
            ))


class B2BCustomerTypePricelist(models.Model):
    _name = "b2b.customer.type.pricelist"
    _description = "B2B Customer Type Base Pricelist"
    _order = "customer_type_id, website_id, currency_id, id"

    customer_type_id = fields.Many2one(
        "b2b.customer.type", required=True, ondelete="cascade", index=True
    )
    website_id = fields.Many2one(
        "website",
        required=True,
        ondelete="cascade",
        default=lambda self: self.env["website"].search([], limit=1),
    )
    pricelist_id = fields.Many2one(
        "product.pricelist", required=True, ondelete="restrict", index=True
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="pricelist_id.currency_id",
        store=True,
        readonly=True,
    )
    active = fields.Boolean(default=True)

    _type_website_currency_unique = models.Constraint(
        "UNIQUE (customer_type_id, website_id, currency_id)",
        "A customer type can have only one base pricelist per website and currency.",
    )

    @api.constrains("website_id", "pricelist_id")
    def _check_pricelist_scope(self):
        for mapping in self:
            pricelist = mapping.pricelist_id
            if pricelist.b2b_effective_partner_id:
                raise ValidationError(_(
                    "A generated customer effective pricelist cannot be used as a base pricelist."
                ))
            if pricelist.company_id and pricelist.company_id != mapping.website_id.company_id:
                raise ValidationError(_(
                    "The base pricelist and website must belong to the same company."
                ))

    def _check_no_active_override_dependency(self):
        for mapping in self:
            dependent = self.env["b2b.partner.pricelist.override"].sudo().search_count([
                ("partner_id.b2b_customer_type_id", "=", mapping.customer_type_id.id),
                ("website_id", "=", mapping.website_id.id),
                ("currency_id", "=", mapping.currency_id.id),
                ("active", "=", True),
            ], limit=1)
            if dependent:
                raise ValidationError(_(
                    "This base pricelist is required by active company overrides. Remove or deactivate those overrides first."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.customer_type_id._b2b_sync_pricing_partners()
        return records

    def write(self, vals):
        dependency_sensitive = self.filtered(
            lambda mapping: vals.get("active") is False or "website_id" in vals
        )
        if "pricelist_id" in vals:
            new_pricelist = self.env["product.pricelist"].browse(vals["pricelist_id"])
            dependency_sensitive |= self.filtered(
                lambda mapping: mapping.currency_id != new_pricelist.currency_id
            )
        dependency_sensitive._check_no_active_override_dependency()
        customer_types = self.customer_type_id
        result = super().write(vals)
        (customer_types | self.customer_type_id)._b2b_sync_pricing_partners()
        return result

    def unlink(self):
        self._check_no_active_override_dependency()
        customer_types = self.customer_type_id
        result = super().unlink()
        customer_types._b2b_sync_pricing_partners()
        return result


class B2BCustomerTypePricing(models.Model):
    _inherit = "b2b.customer.type"

    def _b2b_sync_pricing_partners(self):
        partners = self.env["res.partner"].sudo().search([
            ("b2b_customer_type_id", "in", self.ids),
        ])
        partners.filtered(
            lambda partner: partner.commercial_partner_id == partner
        )._b2b_sync_effective_pricelists()
