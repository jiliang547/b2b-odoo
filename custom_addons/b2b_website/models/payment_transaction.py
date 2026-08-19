from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

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
