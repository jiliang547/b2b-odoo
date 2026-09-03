from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartnerPricing(models.Model):
    _inherit = "res.partner"

    @api.model
    def _b2b_enable_native_pricelist_feature(self):
        """Enable Odoo's native pricelist feature on install and upgrade."""
        feature = self.env.ref("product.group_product_pricelist")
        self.env.ref("base.group_user")._apply_group(feature)
        root = self.env.ref("base.user_root")
        if feature not in root.group_ids:
            root.write({"group_ids": [Command.link(feature.id)]})
        return True

    b2b_customer_type_id = fields.Many2one(
        "b2b.customer.type",
        string="Customer Type",
        tracking=True,
        ondelete="restrict",
        groups="b2b_core.group_b2b_operator",
    )
    b2b_pricelist_override_ids = fields.One2many(
        "b2b.partner.pricelist.override",
        "partner_id",
        string="Company Price Overrides",
        groups="b2b_core.group_b2b_operator",
    )
    b2b_pricing_revision = fields.Integer(
        default=0,
        readonly=True,
        copy=False,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_effective_customer_type_id = fields.Many2one(
        "b2b.customer.type",
        string="Effective Customer Type",
        related="commercial_partner_id.b2b_customer_type_id",
        readonly=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_base_pricelist_ids = fields.Many2many(
        "product.pricelist",
        string="Customer Type Base Pricelists",
        compute="_compute_b2b_pricing_summary",
        groups="b2b_core.group_b2b_operator",
    )
    b2b_effective_pricelist_ids = fields.Many2many(
        "product.pricelist",
        string="Effective Pricelists",
        compute="_compute_b2b_pricing_summary",
        groups="b2b_core.group_b2b_operator",
    )

    @api.depends(
        "commercial_partner_id",
        "commercial_partner_id.b2b_customer_type_id",
        "commercial_partner_id.b2b_customer_type_id.pricelist_mapping_ids",
        "commercial_partner_id.b2b_pricing_revision",
    )
    def _compute_b2b_pricing_summary(self):
        Mapping = self.env["b2b.customer.type.pricelist"].sudo()
        Pricelist = self.env["product.pricelist"].sudo()
        for partner in self:
            company = partner.commercial_partner_id.sudo()
            partner.b2b_base_pricelist_ids = Mapping.search([
                ("customer_type_id", "=", company.b2b_customer_type_id.id),
                ("active", "=", True),
            ]).pricelist_id
            partner.b2b_effective_pricelist_ids = Pricelist.with_context(
                active_test=False
            ).search([
                ("b2b_effective_partner_id", "=", company.id),
                ("active", "=", True),
            ])

    @api.constrains("b2b_customer_type_id")
    def _check_customer_type_covers_active_overrides(self):
        Mapping = self.env["b2b.customer.type.pricelist"].sudo()
        for partner in self.filtered(
            lambda item: item.commercial_partner_id == item
        ):
            for override in partner.b2b_pricelist_override_ids.filtered("active"):
                if not Mapping.search_count([
                    ("customer_type_id", "=", partner.b2b_customer_type_id.id),
                    ("website_id", "=", override.website_id.id),
                    ("currency_id", "=", override.currency_id.id),
                    ("active", "=", True),
                    ("pricelist_id.active", "=", True),
                ], limit=1):
                    raise ValidationError(_(
                        "The selected customer type has no active base pricelist for an existing company override."
                    ))

    def _b2b_bump_pricing_revision(self):
        for partner in self.sudo().filtered(
            lambda item: item.commercial_partner_id == item
        ):
            partner.with_context(b2b_skip_pricing_sync=True).write({
                "b2b_pricing_revision": partner.b2b_pricing_revision + 1,
            })

    def _b2b_pricing_configurations(self):
        """Return configured (website, currency) pairs for one company."""
        self.ensure_one()
        company = self.sudo().commercial_partner_id
        mappings = self.env["b2b.customer.type.pricelist"].sudo().search([
            ("customer_type_id", "=", company.b2b_customer_type_id.id),
            ("active", "=", True),
            ("pricelist_id.active", "=", True),
        ])
        overrides = self.env["b2b.partner.pricelist.override"].sudo().search([
            ("partner_id", "=", company.id),
            ("active", "=", True),
            ("pricelist_id.active", "=", True),
        ])
        return sorted({
            (record.website_id.id, record.currency_id.id)
            for records in (mappings, overrides)
            for record in records
        })

    def _b2b_sync_effective_pricelists(self):
        """Keep one native order-compatible aggregate pricelist per scope."""
        Pricelist = self.env["product.pricelist"].sudo().with_context(active_test=False)
        for company in self.sudo().mapped("commercial_partner_id").filtered(
            lambda partner: partner.commercial_partner_id == partner
        ):
            configurations = company._b2b_pricing_configurations()
            effective = Pricelist.search([
                ("b2b_effective_partner_id", "=", company.id),
            ])
            by_scope = {
                (pricelist.website_id.id, pricelist.currency_id.id): pricelist
                for pricelist in effective
            }
            configured_scopes = set(configurations)
            for website_id, currency_id in configurations:
                website = self.env["website"].sudo().browse(website_id)
                currency = self.env["res.currency"].sudo().browse(currency_id)
                values = {
                    "name": _(
                        "[B2B Effective] %(customer)s / %(currency)s",
                        customer=company.name,
                        currency=currency.name,
                    ),
                    "company_id": website.company_id.id,
                    "website_id": website.id,
                    "currency_id": currency.id,
                    "selectable": False,
                    "code": False,
                    "active": True,
                    "b2b_effective_partner_id": company.id,
                }
                if by_scope.get((website_id, currency_id)):
                    by_scope[(website_id, currency_id)].with_context(
                        b2b_system_pricing=True
                    ).write(values)
                else:
                    by_scope[(website_id, currency_id)] = Pricelist.with_context(
                        b2b_system_pricing=True
                    ).create(values)

            obsolete = effective.filtered(
                lambda pricelist: (
                    pricelist.website_id.id,
                    pricelist.currency_id.id,
                ) not in configured_scopes
            )
            if obsolete:
                obsolete.with_context(b2b_system_pricing=True).write({"active": False})

            current = company.property_product_pricelist.sudo()
            candidates = Pricelist.search([
                ("b2b_effective_partner_id", "=", company.id),
                ("active", "=", True),
            ])
            selected = candidates.filtered(
                lambda pricelist: pricelist.currency_id == current.currency_id
            )[:1] or candidates[:1]
            if selected and current != selected:
                company.with_context(
                    b2b_skip_pricing_sync=True,
                    b2b_system_pricing=True,
                ).write({"property_product_pricelist": selected.id})
            elif not selected and current.b2b_effective_partner_id == company:
                company.with_context(
                    b2b_skip_pricing_sync=True,
                    b2b_system_pricing=True,
                ).write({"property_product_pricelist": False})
            company._b2b_bump_pricing_revision()
            company.invalidate_recordset([
                "b2b_base_pricelist_ids",
                "b2b_effective_pricelist_ids",
            ])

    def _b2b_get_effective_pricelist(self, website, currency):
        self.ensure_one()
        company = self.sudo().commercial_partner_id
        return self.env["product.pricelist"].sudo().search([
            ("b2b_effective_partner_id", "=", company.id),
            ("website_id", "=", website.id),
            ("currency_id", "=", currency.id),
            ("active", "=", True),
        ], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners.filtered("b2b_customer_type_id")._b2b_sync_effective_pricelists()
        return partners

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("b2b_skip_pricing_sync") and (
            "b2b_customer_type_id" in vals or "name" in vals
        ):
            self._b2b_sync_effective_pricelists()
        return result


class B2BPartnerPricelistOverride(models.Model):
    _name = "b2b.partner.pricelist.override"
    _description = "B2B Company Pricelist Override"
    _order = "priority, id"

    partner_id = fields.Many2one(
        "res.partner", required=True, ondelete="cascade", index=True
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
    priority = fields.Integer(
        default=10,
        help="Lower values are evaluated first. The first matching explicit rule wins.",
    )
    active = fields.Boolean(default=True)

    _partner_pricelist_unique = models.Constraint(
        "UNIQUE (partner_id, website_id, pricelist_id)",
        "The same override pricelist cannot be assigned twice to a company website.",
    )
    _priority_positive = models.Constraint(
        "CHECK (priority >= 0)", "Pricelist priority must be zero or greater."
    )

    @api.constrains("partner_id", "website_id", "pricelist_id")
    def _check_override_scope(self):
        for override in self:
            if override.partner_id.commercial_partner_id != override.partner_id:
                raise ValidationError(_(
                    "Company price overrides must be assigned to the commercial account."
                ))
            pricelist = override.pricelist_id
            if pricelist.b2b_effective_partner_id:
                raise ValidationError(_(
                    "A generated customer effective pricelist cannot be used as an override."
                ))
            if pricelist.company_id and pricelist.company_id != override.website_id.company_id:
                raise ValidationError(_(
                    "The override pricelist and website must belong to the same company."
                ))
            base_mapping = self.env["b2b.customer.type.pricelist"].sudo().search([
                ("customer_type_id", "=", override.partner_id.b2b_customer_type_id.id),
                ("website_id", "=", override.website_id.id),
                ("currency_id", "=", override.currency_id.id),
                ("active", "=", True),
            ], limit=1)
            if not base_mapping:
                raise ValidationError(_(
                    "Configure a base pricelist for this customer type, website, and currency before adding a company override."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records.partner_id._b2b_sync_effective_pricelists()
        return records

    def write(self, vals):
        partners = self.partner_id
        result = super().write(vals)
        (partners | self.partner_id)._b2b_sync_effective_pricelists()
        return result

    def unlink(self):
        partners = self.partner_id
        result = super().unlink()
        partners._b2b_sync_effective_pricelists()
        return result


class ProductPricelist(models.Model):
    _inherit = "product.pricelist"

    b2b_effective_partner_id = fields.Many2one(
        "res.partner",
        string="Effective Pricelist Customer",
        readonly=True,
        copy=False,
        index=True,
        ondelete="cascade",
        groups="b2b_core.group_b2b_operator",
    )

    _effective_partner_website_currency_unique = models.Constraint(
        "UNIQUE (b2b_effective_partner_id, website_id, currency_id)",
        "Only one effective pricelist can exist per customer, website, and currency.",
    )

    def _b2b_effective_layers(self):
        """Return ordered native source pricelists for one generated pricelist."""
        self.ensure_one()
        effective = self.sudo()
        partner = effective.b2b_effective_partner_id.commercial_partner_id
        if not partner:
            return []

        layers = []
        overrides = self.env["b2b.partner.pricelist.override"].sudo().search([
            ("partner_id", "=", partner.id),
            ("website_id", "=", effective.website_id.id),
            ("currency_id", "=", effective.currency_id.id),
            ("active", "=", True),
            ("pricelist_id.active", "=", True),
        ], order="priority, id")
        layers.extend((override.pricelist_id.sudo(), True) for override in overrides)

        base = self.env["b2b.customer.type.pricelist"].sudo().search([
            ("customer_type_id", "=", partner.b2b_customer_type_id.id),
            ("website_id", "=", effective.website_id.id),
            ("currency_id", "=", effective.currency_id.id),
            ("active", "=", True),
            ("pricelist_id.active", "=", True),
        ], limit=1)
        if base:
            layers.append((base.pricelist_id.sudo(), False))
        return layers

    def _compute_price_rule(
        self, products, quantity, *, currency=None, uom=None, date=False,
        compute_price=True, **kwargs
    ):
        self and self.ensure_one()
        if not self or not self.sudo().b2b_effective_partner_id:
            return super()._compute_price_rule(
                products,
                quantity,
                currency=currency,
                uom=uom,
                date=date,
                compute_price=compute_price,
                **kwargs,
            )

        results = {}
        remaining = products
        for source, is_override in self._b2b_effective_layers():
            if not remaining:
                break
            layer_results = source._compute_price_rule(
                remaining,
                quantity,
                currency=currency or self.currency_id,
                uom=uom,
                date=date,
                compute_price=compute_price,
                **kwargs,
            )
            accepted_ids = []
            for product in remaining:
                price, rule_id = layer_results[product.id]
                if is_override:
                    rule = self.env["product.pricelist.item"].sudo().browse(rule_id)
                    # A company override is deliberately sparse. Global rules
                    # remain useful when the same source pricelist is used in a
                    # normal Odoo flow, but cannot shadow the customer-type base.
                    if not rule or rule.applied_on == "3_global":
                        continue
                results[product.id] = (price, rule_id)
                accepted_ids.append(product.id)
            if accepted_ids:
                remaining = remaining.filtered(lambda product: product.id not in accepted_ids)

        if remaining:
            fallback = super()._compute_price_rule(
                remaining,
                quantity,
                currency=currency or self.currency_id,
                uom=uom,
                date=date,
                compute_price=compute_price,
                **kwargs,
            )
            results.update(fallback)
        return results

    def b2b_procurement_rules(self, product, date):
        """Return rules from the same winning layer used for price and MOQ."""
        self.ensure_one()
        if not self.sudo().b2b_effective_partner_id:
            return self._get_applicable_rules(product, date)
        for source, is_override in self._b2b_effective_layers():
            rules = source._get_applicable_rules(product, date)
            if is_override:
                rules = rules.filtered(lambda rule: rule.applied_on != "3_global")
                if not rules:
                    continue
            return rules
        return self.env["product.pricelist.item"]

    def _b2b_pricing_partners(self):
        source_ids = self.filtered(lambda pricelist: not pricelist.b2b_effective_partner_id).ids
        if not source_ids:
            return self.env["res.partner"]
        override_partners = self.env["b2b.partner.pricelist.override"].sudo().search([
            ("pricelist_id", "in", source_ids),
        ]).partner_id
        type_ids = self.env["b2b.customer.type.pricelist"].sudo().search([
            ("pricelist_id", "in", source_ids),
        ]).customer_type_id.ids
        type_partners = self.env["res.partner"].sudo().search([
            ("b2b_customer_type_id", "in", type_ids),
        ]) if type_ids else self.env["res.partner"]
        return (override_partners | type_partners).filtered(
            lambda partner: partner.commercial_partner_id == partner
        )

    def _b2b_touch_pricing_partners(self, sync=False):
        partners = self._b2b_pricing_partners()
        if sync:
            partners._b2b_sync_effective_pricelists()
        else:
            partners._b2b_bump_pricing_revision()
