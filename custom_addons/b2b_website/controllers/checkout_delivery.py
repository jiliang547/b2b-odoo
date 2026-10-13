from odoo.http import request, route
from odoo.addons.website_sale.controllers.delivery import Delivery


class PartnerCheckoutDelivery(Delivery):
    @route()
    def shop_set_delivery_method(self, dm_id=None, **kwargs):
        if request.cart and request.cart._b2b_uses_manual_freight():
            return self._order_summary_values(request.cart, **kwargs)
        return super().shop_set_delivery_method(dm_id=dm_id, **kwargs)

    def _order_summary_values(self, order, **kwargs):
        values = super()._order_summary_values(order, **kwargs)
        if order.website_id:
            values["b2b_delivery_terms"] = order._b2b_checkout_delivery_terms()
        return values

    @route()
    def shop_get_delivery_rate(self, dm_id):
        if request.cart and request.cart._b2b_uses_manual_freight():
            return self._order_summary_values(request.cart)
        # Keep native cart ownership, carrier compatibility and actual fee
        # calculation. Only add copy for the checkout's delivery price badge.
        values = super().shop_get_delivery_rate(dm_id)
        if values.get("success") and request.cart.website_id:
            values["b2b_delivery_terms"] = request.cart._b2b_checkout_delivery_terms()
        return values
