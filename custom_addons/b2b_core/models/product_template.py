from odoo import api, fields, models
from odoo.http import request


class ProductTemplate(models.Model):
    _inherit = "product.template"

    b2b_visibility_mode = fields.Selection(
        [
            ("all", "All Website Visitors"),
            ("approved", "Approved B2B Customers"),
            ("segments", "Selected B2B Segments"),
            ("hidden", "Hidden from Partner Hub"),
        ],
        required=True,
        default="approved",
        index=True,
        tracking=True,
    )
    b2b_visible_segment_ids = fields.Many2many(
        "b2b.customer.segment",
        "b2b_product_segment_rel",
        "product_tmpl_id",
        "segment_id",
        string="Visible B2B Segments",
    )
    b2b_brand_id = fields.Many2one(
        "b2b.product.brand",
        string="Brand",
        ondelete="restrict",
        index=True,
    )
    b2b_application_ids = fields.Many2many(
        "b2b.product.application",
        "b2b_product_application_rel",
        "product_tmpl_id",
        "application_id",
        string="Applications",
    )
    b2b_model_number = fields.Char(string="Model Number", index="trigram")
    b2b_specifications = fields.Html(string="Technical Specifications", sanitize=True)

    @api.model_create_multi
    def create(self, vals_list):
        if any({"list_price", "compare_list_price"}.intersection(vals) for vals in vals_list):
            self.env["b2b.price.write.mixin"]._b2b_check_price_write()
        return super().create(vals_list)

    def write(self, vals):
        if {"list_price", "compare_list_price"}.intersection(vals):
            self.env["b2b.price.write.mixin"]._b2b_check_price_write()
        return super().write(vals)

    def _get_sales_prices(self, website):
        """Use each card's effective MOQ when explicitly requested by B2B catalog code.

        Native website_sale intentionally prices shop cards at quantity one. The
        Partner Hub cannot sell below its customer-specific MOQ, so a quantity-one
        card price can point to a different pricelist tier than the detail page.
        Keep Odoo's native result unchanged unless the B2B service supplies an
        explicit quantity map, then recompute only the affected products with the
        native pricelist, tax and comparison-price helpers.
        """
        prices = super()._get_sales_prices(website)
        quantities = self.env.context.get("b2b_sale_quantities") or {}
        if not quantities:
            return prices

        pricelist = request.pricelist
        currency = website.currency_id
        fiscal_position_sudo = request.fiscal_position
        date = fields.Date.context_today(self)
        comparison_prices_enabled = self.env["res.groups"]._is_feature_enabled(
            "website_sale.group_product_price_comparison"
        )

        grouped = {}
        for template in self:
            quantity = float(quantities.get(template.id) or 1.0)
            if quantity == 1.0:
                continue
            grouped.setdefault(quantity, self.browse())
            grouped[quantity] |= template

        computed = {}
        for quantity, templates in grouped.items():
            for template_id, result in pricelist._compute_price_rule(
                templates, quantity
            ).items():
                computed[template_id] = (quantity, result)

        for template in self.filtered(lambda item: item.id in computed):
            quantity, (pricelist_price, pricelist_rule_id) = computed[template.id]
            product_taxes = template.sudo().taxes_id._filter_taxes_by_company(
                self.env.company
            )
            taxes = fiscal_position_sudo.map_tax(product_taxes)
            values = prices[template.id]
            values["price_reduce"] = self._apply_taxes_to_price(
                pricelist_price,
                currency,
                product_taxes,
                taxes,
                template,
                website=website,
            )
            values.pop("base_price", None)

            base_price = None
            pricelist_item = template.env["product.pricelist.item"].browse(
                pricelist_rule_id
            )
            if pricelist_item._show_discount_on_shop():
                before_discount = pricelist_item._compute_price_before_discount(
                    product=template,
                    quantity=quantity,
                    date=date,
                    uom=template.uom_id,
                    currency=currency,
                )
                if currency.compare_amounts(before_discount, pricelist_price) == 1:
                    base_price = before_discount
                    values["base_price"] = self._apply_taxes_to_price(
                        before_discount,
                        currency,
                        product_taxes,
                        taxes,
                        template,
                        website=website,
                    )

            if not base_price and comparison_prices_enabled and template.compare_list_price:
                values["base_price"] = template.currency_id._convert(
                    template.compare_list_price,
                    currency,
                    self.env.company,
                    date,
                    round=False,
                )
        return prices
