from odoo.addons.sale.controllers.portal import CustomerPortal


class CollectionSalePortal(CustomerPortal):
    def _get_payment_values(self, order_sudo, is_down_payment=False, payment_amount=None, **kwargs):
        if order_sudo.b2b_collection_active:
            # Native Sales supports partial payments; ecommerce's cart route
            # deliberately accepts only the entire cart total.
            amount = min(payment_amount or order_sudo.b2b_payable_now or order_sudo.b2b_balance, order_sudo.b2b_balance)
            return super()._get_payment_values(order_sudo, is_down_payment=amount < order_sudo.amount_total, payment_amount=amount, **kwargs)
        return super()._get_payment_values(order_sudo, is_down_payment=is_down_payment, payment_amount=payment_amount, **kwargs)
