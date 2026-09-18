from odoo import _
from odoo.http import route
from odoo.exceptions import AccessError, MissingError, ValidationError
from odoo.addons.sale.controllers.portal import CustomerPortal, PaymentPortal


class CollectionSalePortal(CustomerPortal):
    @route()
    def portal_order_page(self, order_id, payment_amount=None, access_token=None, **kw):
        try:
            order = self._document_check_access('sale.order', order_id, access_token=access_token)
        except (AccessError, MissingError):
            return super().portal_order_page(order_id, payment_amount=payment_amount, access_token=access_token, **kw)
        order.env["b2b.message.thread"].sudo().search([
            ("source_model", "=", "sale.order"),
            ("res_id", "=", order.id),
        ]).action_mark_read(order.env.user.partner_id)
        if order.b2b_collection_active:
            # Native route validates a requested amount against the original
            # entire deposit. Resolve remaining dues through our shared payment
            # values instead, rather than accepting an obsolete URL amount.
            # Confirmed orders rely on an explicit amount to expose the native
            # payment dialog. Only quotations need the original-deposit check
            # avoided; resolve confirmed-order dues from the live order.
            payment_amount = (order.b2b_payable_now or order.b2b_balance) if (
                payment_amount and order.state == 'sale'
                and order.b2b_review_state != 'pending' and not order.b2b_is_change_revision
            ) else None
        return super().portal_order_page(order_id, payment_amount=payment_amount, access_token=access_token, **kw)

    def _get_payment_values(self, order_sudo, is_down_payment=False, payment_amount=None, **kwargs):
        if order_sudo.b2b_collection_active:
            # Native Sales supports partial payments; ecommerce's cart route
            # deliberately accepts only the entire cart total.
            amount = min(payment_amount or order_sudo.b2b_payable_now or order_sudo.b2b_balance, order_sudo.b2b_balance)
            values = super()._get_payment_values(order_sudo, is_down_payment=amount < order_sudo.amount_total, payment_amount=amount, **kwargs)
            values['b2b_quote_token'] = order_sudo._b2b_quote_token()
            return values
        return super()._get_payment_values(order_sudo, is_down_payment=is_down_payment, payment_amount=payment_amount, **kwargs)


class CollectionPaymentPortal(PaymentPortal):
    @route()
    def portal_order_transaction(self, order_id, access_token, b2b_quote_token=None, **kwargs):
        order = self._document_check_access('sale.order', order_id, access_token=access_token)
        if order.b2b_collection_active:
            order._b2b_lock_collection()
            if not b2b_quote_token or b2b_quote_token != order._b2b_quote_token():
                raise ValidationError(_("Your order has changed. Refresh the page and review the latest quotation before paying."))
        return super().portal_order_transaction(order_id, access_token, **kwargs)
