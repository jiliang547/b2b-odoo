from werkzeug.exceptions import NotFound
from werkzeug.urls import urlencode

from odoo.http import request, route
from odoo.addons.payment.controllers.post_processing import PaymentPostProcessing
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.addons.website_sale.controllers.cart import Cart
from odoo.addons.website_sale.controllers.variant import WebsiteSaleVariantController


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
    def _b2b_checkout_order(self, sale_order_id=None):
        if sale_order_id:
            order = request.env["sale.order"].sudo().browse(int(sale_order_id)).exists()
            if order.id != request.session.get("sale_last_order_id"):
                return request.env["sale.order"]
            return order
        order = request.cart
        if not order and request.session.get("sale_last_order_id"):
            order = request.env["sale.order"].sudo().browse(
                request.session["sale_last_order_id"]
            ).exists()
        return order

    def _b2b_payment_redirect(self, order):
        """Return a safe redirect while paid orders are being finalized."""
        if not order:
            return False
        transaction = order.get_portal_last_transaction()
        if not transaction:
            return False
        if transaction.state in ("authorized", "done"):
            if not transaction.is_post_processed or order.state not in ("sale", "done"):
                PaymentPostProcessing.monitor_transaction(transaction)
                return request.redirect("/payment/status")
            return False
        if transaction.state in ("cancel", "error"):
            return request.redirect("/shop/payment")
        return False

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

    @route()
    def shop_payment_validate(self, sale_order_id=None, **post):
        order = self._b2b_checkout_order(sale_order_id)
        if redirect := self._b2b_payment_redirect(order):
            return redirect
        return super().shop_payment_validate(sale_order_id=sale_order_id, **post)

    @route()
    def shop_payment_confirmation(self, **post):
        order = self._b2b_checkout_order()
        if redirect := self._b2b_payment_redirect(order):
            return redirect
        if order and order.state not in ("sale", "done"):
            return request.redirect("/shop/payment")
        return super().shop_payment_confirmation(**post)


class PartnerHubCart(Cart):
    @route()
    def cart(self, id=None, access_token=None, revive_method="", **post):
        if not _can_view_cart_prices():
            return request.render("b2b_website.ordering_unavailable", {"page_name": "ordering_unavailable"})
        return super().cart(
            id=id, access_token=access_token, revive_method=revive_method, **post
        )


class PartnerHubVariantController(WebsiteSaleVariantController):
    @route()
    def get_combination_info_website(
        self, product_template_id, product_id, combination, add_qty, uom_id=None, **kwargs
    ):
        product = request.env["product.template"].browse(int(product_template_id or 0))
        service = request.env["b2b.product.service"]
        if not product or not service.is_visible(product, website=request.website):
            raise NotFound()
        if product_id and int(product_id) not in product.product_variant_ids.ids:
            raise NotFound()
        info = super().get_combination_info_website(
            product_template_id,
            product_id,
            combination,
            add_qty,
            uom_id=uom_id,
            **kwargs,
        )
        variant = request.env["product.product"].browse(info.get("product_id")).exists()
        procurement = service.procurement_info(
            variant,
            pricelist=request.pricelist,
            website=request.website,
            combination_info=info,
        ) if variant else {}
        resources = service.allowed_documents(
            product, website=request.website, variant=variant
        ) if variant else request.env["product.document"]
        info.update({
            "b2b_can_view_price": service.can_view_price(website=request.website),
            "b2b_price_state": service.price_state(website=request.website),
            "b2b_sku": variant.default_code if variant else "",
            "b2b_uom_id": variant.uom_id.id if variant else False,
            "b2b_currency_code": request.pricelist.currency_id.name,
            "b2b_sample_url": "/sample/request?product_id=%s" % variant.id if variant else "",
            "b2b_minimum_quantity": procurement.get("minimum_quantity"),
            "b2b_quantity_step": procurement.get("quantity_step"),
            "b2b_uom_name": procurement.get("uom_name"),
            "b2b_stock_state": procurement.get("stock_state"),
            "b2b_stock_label": procurement.get("stock_label"),
            "b2b_stock_quantity": procurement.get("stock_quantity"),
            "b2b_show_stock_quantity": procurement.get("show_stock_quantity"),
            "b2b_lead_time_days": procurement.get("lead_time_days"),
            "b2b_resources": [{
                "id": document.id,
                "name": document.name,
                "version": document.b2b_version or "",
                "language": document.b2b_language or "",
                "format": (document.mimetype or "File").split("/")[-1].upper(),
                "size_mb": round(document.file_size / 1048576.0, 1) if document.file_size else False,
                "url": "/products/resource/%s" % document.id,
            } for document in resources],
        })
        if not info["b2b_can_view_price"]:
            for key in (
                "price", "list_price", "compare_list_price", "base_unit_price",
                "price_extra",
            ):
                info.pop(key, None)
        return info
