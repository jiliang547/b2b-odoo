from werkzeug.exceptions import NotFound
from werkzeug.urls import urlencode

from odoo.http import request, route
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.cart import Cart


def _can_view_cart_prices():
    return request.env["b2b.product.service"].can_view_price(website=request.website)


def _can_checkout():
    company = request.env.user.partner_id.commercial_partner_id
    return (
        _can_view_cart_prices()
        and (
            not request.website.b2b_require_approved_checkout
            or company.b2b_approved
            or request.env.user._is_internal()
        )
    )


class PartnerHubWebsiteSale(WebsiteSale):
    @route()
    def shop(self, page=0, category=None, search="", **post):
        query = {}
        if search:
            query["search"] = search
        if category and getattr(category, "id", False):
            query["category"] = category.id
        query_string = urlencode(query)
        return request.redirect("/products%s" % (("?" + query_string) if query_string else ""))

    @route()
    def product(self, product, category=None, pricelist=None, **kwargs):
        if not request.env["b2b.product.service"].is_visible(product):
            raise NotFound()
        slug = request.env["ir.http"]._slug(product)
        return request.redirect("/products/%s" % slug, code=301)

    @route()
    def shop_checkout(self, try_skip_step=None, **query_params):
        if not _can_checkout():
            return request.render("b2b_website.ordering_unavailable", {"page_name": "ordering_unavailable"})
        return super().shop_checkout(try_skip_step=try_skip_step, **query_params)

    @route()
    def shop_payment(self, **post):
        if not _can_checkout():
            return request.render("b2b_website.ordering_unavailable", {"page_name": "ordering_unavailable"})
        return super().shop_payment(**post)


class PartnerHubCart(Cart):
    @route()
    def cart(self, id=None, access_token=None, revive_method="", **post):
        if not _can_view_cart_prices():
            return request.render("b2b_website.ordering_unavailable", {"page_name": "ordering_unavailable"})
        return super().cart(
            id=id, access_token=access_token, revive_method=revive_method, **post
        )
