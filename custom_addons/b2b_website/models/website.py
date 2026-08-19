from odoo import models
from odoo.http import request
from odoo.addons.website_sale.models.website import PRICELIST_SESSION_CACHE_KEY


class Website(models.Model):
    _inherit = "website"

    def _get_and_cache_current_pricelist(self):
        pricelist = super()._get_and_cache_current_pricelist()
        if not request or request.env.user._is_public() or not request.env.user.share:
            return pricelist

        assigned = request.env.user.partner_id.property_product_pricelist.sudo()
        if not assigned or not assigned._is_available_on_website(self):
            return pricelist
        if assigned == pricelist:
            return pricelist

        # Portal B2B accounts always follow the pricelist assigned to their
        # customer record. This also invalidates a stale website-session choice
        # after an operator changes the customer's negotiated pricelist.
        request.session[PRICELIST_SESSION_CACHE_KEY] = assigned.id
        cart = request.cart
        if cart and cart.state == "draft" and cart.pricelist_id != assigned:
            cart.pricelist_id = assigned
            cart._recompute_prices()
        return assigned
