import math

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain
from odoo.http import request


class B2BProductService(models.AbstractModel):
    _name = "b2b.product.service"
    _description = "B2B Product Authorization and Pricing Service"

    @api.model
    def commercial_partner(self, partner=None):
        current = self.env.user.partner_id.commercial_partner_id
        candidate = (partner or current).commercial_partner_id
        if not self.env.user._is_internal() and candidate.id != current.id:
            candidate = current
        # Policy attributes are intentionally hidden from generic partner reads.
        # Elevation is limited to the authenticated user's commercial company.
        return candidate.sudo()

    @api.model
    def visible_domain(self, partner=None, website=None, include_unpublished=False):
        partner = self.commercial_partner(partner)
        website = website or self.env["website"].get_current_website()
        domain = (
            list(website.with_context(b2b_skip_visibility=True).sale_product_domain())
            if website
            else [("sale_ok", "=", True)]
        )
        if include_unpublished:
            domain = [term for term in domain if term != ("is_published", "=", True)]

        return Domain.AND([domain, self.visibility_policy_domain(partner=partner)])

    @api.model
    def visibility_policy_domain(self, partner=None):
        """Return only the Partner Hub policy part of the product domain.

        Keeping this separate lets ``website.sale_product_domain`` protect native
        shop/search routes without creating a recursive domain call.
        """
        partner = self.commercial_partner(partner)

        if self.env.user._is_internal():
            return []

        allowed = [("b2b_visibility_mode", "=", "all")]
        if partner.b2b_approved:
            allowed = Domain.OR([
                allowed,
                [("b2b_visibility_mode", "=", "approved")],
                [
                    ("b2b_visibility_mode", "=", "segments"),
                    ("b2b_visible_segment_ids", "in", partner.b2b_segment_ids.ids),
                ],
            ])
        return allowed

    @api.model
    def is_visible(self, product, partner=None, website=None):
        if not product or not product.exists():
            return False
        domain = Domain.AND([
            [("id", "=", product.id)],
            self.visible_domain(partner=partner, website=website),
        ])
        return bool(self.env["product.template"].search_count(domain, limit=1))

    @api.model
    def can_view_price(self, partner=None, website=None):
        website = website or self.env["website"].get_current_website()
        partner = self.commercial_partner(partner)
        # Website administrators need to preview and validate the effective
        # website pricelist even when their own contact is not a B2B customer.
        # Keep the exception narrow: ordinary internal users still follow the
        # configured customer approval policy.
        if self.env.user.has_group("base.group_system"):
            return True
        mode = website.b2b_price_display_mode
        if mode == "always":
            return True
        if mode == "never":
            return False
        if self.env.user._is_public():
            return False
        if mode == "authenticated":
            return True
        return bool(partner.b2b_approved)

    @api.model
    def price_state(self, partner=None, website=None):
        website = website or self.env["website"].get_current_website()
        if self.can_view_price(partner=partner, website=website):
            return "visible"
        if self.env.user._is_public():
            return website.b2b_guest_price_state
        return website.b2b_no_price_state

    @api.model
    def price_payload(self, products, partner=None, website=None):
        website = website or self.env["website"].get_current_website()
        state = self.price_state(partner=partner, website=website)
        if state != "visible":
            return {product.id: {"state": state} for product in products}
        pricelist = request.pricelist
        quantities = {
            product.id: self.procurement_info(
                product,
                pricelist=pricelist,
                website=website,
            )["minimum_quantity"]
            for product in products
        }
        prices = products.with_context(
            b2b_sale_quantities=quantities
        )._get_sales_prices(website)
        return {
            product.id: {
                "state": "visible",
                "price": prices[product.id]["price_reduce"],
                "base_price": prices[product.id].get("base_price"),
                "currency": website.currency_id,
            }
            for product in products
        }

    @api.model
    def procurement_info(self, product, pricelist=None, website=None, combination_info=None):
        """Return website purchasing facts backed by native Odoo fields.

        The product's ``b2b_default_moq`` is the maintain-once fallback and an
        applicable native ``product.pricelist.item.min_quantity`` overrides it
        for customer-specific terms. The product UoM supplies the display unit,
        while installed stock modules supply website-warehouse availability and
        sales lead time. The method deliberately degrades to neutral availability
        when Inventory is not installed so the website module remains portable to
        Odoo.sh.
        """
        variant = product
        if product and product._name == "product.template":
            variant = product.product_variant_id
        if not variant:
            return {}

        website = website or self.env["website"].get_current_website()
        pricelist = pricelist or (
            website
            and "pricelist_id" in website._fields
            and website.pricelist_id
        )
        minimum_quantity = max(
            variant.uom_id.rounding,
            variant.product_tmpl_id.b2b_default_moq,
            1.0,
        )

        if pricelist:
            rules = pricelist.sudo().b2b_procurement_rules(
                variant, fields.Datetime.now()
            )
            quantity_rules = rules.filtered(lambda rule: rule.min_quantity > 0)
            if quantity_rules:
                specificity = {
                    "0_product_variant": 4,
                    "1_product": 3,
                    "2_product_category": 2,
                    "3_global": 1,
                }
                best_rank = max(specificity.get(rule.applied_on, 0) for rule in quantity_rules)
                best_rules = quantity_rules.filtered(
                    lambda rule: specificity.get(rule.applied_on, 0) == best_rank
                )
                minimum_quantity = max(
                    variant.uom_id.rounding,
                    min(best_rules.mapped("min_quantity")),
                )

        stock = combination_info or {}
        is_storable = bool(stock.get("is_storable"))
        free_quantity = stock.get("free_qty")
        allow_out_of_stock = bool(stock.get("allow_out_of_stock_order"))
        if free_quantity is None and "free_qty" in variant._fields:
            is_storable = bool(getattr(variant, "is_storable", False))
            if website and hasattr(website, "_get_product_available_qty"):
                free_quantity = website._get_product_available_qty(variant.sudo())
            else:
                free_quantity = variant.sudo().free_qty
            allow_out_of_stock = bool(getattr(variant, "allow_out_of_stock_order", False))

        if is_storable and (free_quantity or 0) > 0:
            stock_state = "in_stock"
            stock_label = "In Stock"
        elif is_storable and not allow_out_of_stock:
            stock_state = "out_of_stock"
            stock_label = "Out of Stock"
        elif is_storable:
            stock_state = "available_order"
            stock_label = "Available to Order"
        else:
            stock_state = "available"
            stock_label = "Available"

        show_stock_quantity = bool(
            is_storable
            and free_quantity is not None
            and stock.get("show_availability", getattr(variant, "show_availability", False))
        )
        lead_time_days = (
            max(0, int(round(variant.sale_delay)))
            if "sale_delay" in variant._fields
            else None
        )
        return {
            "minimum_quantity": minimum_quantity,
            # Odoo's uom.rounding is a calculation precision (0.01 with the
            # usual Product Unit precision), not a website purchase increment.
            # Match the native website_sale behaviour and sell one selected UoM
            # at a time. Product packaging can be exposed explicitly in a future
            # selector without changing this default contract.
            "quantity_step": 1.0,
            "uom_name": variant.uom_id.name,
            "stock_state": stock_state,
            "stock_label": stock_label,
            "stock_quantity": max(0, free_quantity or 0),
            "show_stock_quantity": show_stock_quantity,
            "lead_time_days": lead_time_days,
        }

    @api.model
    def validate_sale_quantity(self, product, quantity, pricelist=None, website=None):
        """Validate website quantities against the same MOQ/step shown in the UI."""
        try:
            quantity = float(quantity)
        except (TypeError, ValueError):
            raise ValidationError(_("Please enter a valid quantity.")) from None
        if not math.isfinite(quantity):
            raise ValidationError(_("Please enter a valid quantity."))

        procurement = self.procurement_info(
            product, pricelist=pricelist, website=website
        )
        minimum = float(procurement.get("minimum_quantity") or 1.0)
        step = float(procurement.get("quantity_step") or 1.0)
        tolerance = max(1e-9, step * 1e-9)
        if quantity < minimum - tolerance:
            raise ValidationError(
                _("The minimum order quantity for this product is %(minimum)g.", minimum=minimum)
            )

        increments = (quantity - minimum) / step
        if not math.isclose(increments, round(increments), abs_tol=tolerance):
            raise ValidationError(
                _(
                    "Quantity must start at %(minimum)g and increase in steps of %(step)g.",
                    minimum=minimum,
                    step=step,
                )
            )
        return quantity

    @api.model
    def product_from_document(self, document):
        if document.res_model == "product.template":
            return self.env["product.template"].browse(document.res_id).exists()
        if document.res_model == "product.product":
            return self.env["product.product"].browse(document.res_id).exists().product_tmpl_id
        return self.env["product.template"]

    @api.model
    def document_is_allowed(self, document, partner=None, website=None):
        product = self.product_from_document(document)
        if not document.active or not self.is_visible(product, partner=partner, website=website):
            return False
        if (
            not self.env.user._is_internal()
            and not document.shown_on_product_page
            and not (
                document.res_model == "product.product"
                and document.b2b_publish_in_partner_hub
            )
        ):
            return False
        if self.env.user._is_internal():
            return True
        partner = self.commercial_partner(partner)
        mode = document.b2b_visibility_mode
        if mode == "internal":
            return False
        if mode == "product":
            return True
        if not partner.b2b_approved:
            return False
        if mode == "approved":
            return True
        return bool(document.b2b_visible_segment_ids & partner.b2b_segment_ids)

    @api.model
    def allowed_documents(self, product, partner=None, website=None, variant=None):
        if not self.is_visible(product, partner=partner, website=website):
            return self.env["product.document"]
        # Portal users do not have generic attachment read access. Elevation is
        # limited to documents already linked to an authorized product, and
        # every result is filtered again by the B2B policy below.
        document_domain = Domain.AND([
            product._get_product_document_domain(),
            [("active", "=", True), ("shown_on_product_page", "=", True)],
        ])
        documents = self.env["product.document"].sudo().search(
            document_domain,
            order="sequence, name, id",
        )
        template = product if product._name == "product.template" else product.product_tmpl_id
        variants = variant or (
            product if product._name == "product.product" else template.product_variant_ids
        )
        variant_documents = self.env["product.document"].sudo().search([
            ("active", "=", True),
            ("res_model", "=", "product.product"),
            ("res_id", "in", variants.ids),
            ("b2b_publish_in_partner_hub", "=", True),
        ], order="sequence, name, id")
        documents |= variant_documents
        return documents.filtered(
            lambda document: self.document_is_allowed(
                document, partner=partner, website=website
            )
        )
