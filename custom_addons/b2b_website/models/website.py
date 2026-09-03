from odoo import models
from odoo.http import request
from odoo.addons.website_sale.models.website import (
    PRICELIST_SELECTED_SESSION_CACHE_KEY,
    PRICELIST_SESSION_CACHE_KEY,
)


class Website(models.Model):
    _inherit = "website"

    def _prepare_sale_order_values(self, partner_sudo):
        values = super()._prepare_sale_order_values(partner_sudo)
        if partner_sudo:
            values["b2b_pricing_revision"] = (
                partner_sudo.commercial_partner_id.sudo().b2b_pricing_revision
            )
        return values

    def b2b_currency_pricelists(self):
        """Return one native selectable pricelist per currency in UI order."""
        self.ensure_one()
        available = self.get_pricelist_available(show_visible=True)
        current = request.pricelist if request else self.env["product.pricelist"]
        by_currency = {}
        for pricelist in available:
            code = pricelist.currency_id.name
            if code not in by_currency or pricelist == current:
                by_currency[code] = pricelist
        result = self.env["product.pricelist"]
        for code in ("USD", "EUR", "GBP", "CNY", "AED", "SGD"):
            if code in by_currency:
                result |= by_currency.pop(code)
        for code in sorted(by_currency):
            result |= by_currency[code]
        return result

    def b2b_language_label(self, language):
        labels = {
            "en_US": "English",
            "zh_CN": "中文",
            "es_ES": "Español",
            "ar_001": "العربية",
            "fr_FR": "Français",
        }
        return labels.get(language.code, language.name.split("/")[-1].strip())

    def b2b_frontend_languages(self, frontend_languages):
        order = {code: index for index, code in enumerate(
            ("en_US", "zh_CN", "es_ES", "ar_001", "fr_FR")
        )}
        return sorted(
            frontend_languages.values(),
            key=lambda language: (order.get(language.code, 99), language.name),
        )

    def _get_and_cache_current_pricelist(self):
        pricelist = super()._get_and_cache_current_pricelist()
        if not request or request.env.user._is_public() or not request.env.user.share:
            return pricelist

        company = request.env.user.partner_id.commercial_partner_id.sudo()
        selected_id = request.session.get(PRICELIST_SELECTED_SESSION_CACHE_KEY)
        selected = request.env["product.pricelist"].sudo().browse(selected_id).exists()
        if (
            pricelist.sudo().b2b_effective_partner_id
            and pricelist.sudo().b2b_effective_partner_id != company
        ):
            # Never accept another customer's generated pricelist, even if its
            # technical ID was submitted directly to the native selector.
            request.session.pop(PRICELIST_SESSION_CACHE_KEY, None)
            pricelist = company.property_product_pricelist.sudo()

        effective = (
            company._b2b_get_effective_pricelist(self, pricelist.currency_id)
            if pricelist and pricelist.currency_id else request.env["product.pricelist"]
        )
        assigned = effective or company.property_product_pricelist.sudo()
        if (
            selected
            and selected == pricelist
            and selected.selectable
            and self.is_pricelist_available(selected.id)
            and not effective
        ):
            return pricelist

        if not assigned or (
            not assigned.b2b_effective_partner_id
            and not assigned._is_available_on_website(self)
        ):
            return pricelist

        # Portal B2B accounts always follow the pricelist assigned to their
        # customer record. This also invalidates a stale website-session choice
        # after an operator changes the customer's negotiated pricelist.
        request.session[PRICELIST_SESSION_CACHE_KEY] = assigned.id
        cart = request.cart
        revision_changed = bool(
            cart
            and cart.b2b_pricing_revision != company.b2b_pricing_revision
        )
        if cart and cart.state == "draft" and (
            cart.pricelist_id != assigned or revision_changed
        ):
            cart.write({
                "pricelist_id": assigned.id,
                "b2b_pricing_revision": company.b2b_pricing_revision,
            })
            cart._recompute_prices()
        return assigned
