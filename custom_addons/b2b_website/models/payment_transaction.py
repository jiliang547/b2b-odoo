from odoo import _, api, models
from odoo.exceptions import ValidationError


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        # Check resolved native M2M links before any provider request is sent.
        # This also covers stale payment dialogs and direct transaction URLs.
        if transactions.sale_order_ids.filtered(
            lambda order: order.b2b_review_state == "pending" or order.b2b_is_change_revision
        ):
            raise ValidationError(_("This order is not ready for payment. Please wait for our team to release the final order."))
        return transactions

    def _check_amount_and_confirm_order(self):
        """Identify the trusted transaction while Sales confirms its linked order.

        Payment status polling is an anonymous route and Odoo deliberately sudoes
        the monitored transaction.  The request user nevertheless remains the
        public user, so the B2B policy must use the customer from the transaction's
        linked order instead of the request user's partner.
        """
        return super(
            PaymentTransaction,
            self.with_context(b2b_payment_transaction_ids=self.ids),
        )._check_amount_and_confirm_order()

    def _post_process(self):
        result = super()._post_process()
        completed_transactions = self.filtered(
            lambda transaction: transaction.state in ("authorized", "done")
        )
        completed_orders = completed_transactions.mapped("sale_order_ids")
        # Website Sale can confirm a paid quotation without going back through
        # sale.order.action_confirm().  Close the B2B review state from the
        # payment post-processing hook as well so the portal cannot remain in
        # "Ready for payment" after a successful transaction.
        completed_orders.filtered(
            lambda order: order.state in ("sale", "done")
            and order.b2b_checkout_mode == "review"
            and order.b2b_review_state in ("pending", "ready")
        ).write({"b2b_review_state": "confirmed"})
        completed_orders.mapped("b2b_change_request_ids")._on_order_payment_updated()
        return result
