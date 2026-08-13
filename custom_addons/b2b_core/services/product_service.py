from odoo import api, models
from odoo.fields import Domain


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
        prices = products._get_sales_prices(website)
        return {
            product.id: {
                "state": "visible",
                "price": prices[product.id]["price_reduce"],
                "currency": website.currency_id,
            }
            for product in products
        }

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
    def allowed_documents(self, product, partner=None, website=None):
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
        return documents.filtered(
            lambda document: self.document_is_allowed(
                document, partner=partner, website=website
            )
        )
