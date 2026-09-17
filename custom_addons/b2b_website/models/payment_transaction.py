from odoo import _, api, models
from odoo.exceptions import ValidationError


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        transactions.sale_order_ids._b2b_start_collection()
        for tx in transactions.filtered(lambda t: t.operation not in ('refund', 'validation') and t.state not in ('done', 'authorized')):
            for order in tx.sale_order_ids.filtered('b2b_collection_active'):
                order._b2b_lock_collection()
                if tx.currency_id != order.currency_id or tx.amount <= 0 or order.currency_id.compare_amounts(tx.amount, order.b2b_balance) > 0:
                    raise ValidationError(_('The payment exceeds the current outstanding balance. Please refresh the order.'))
                if (order.transaction_ids - tx).filtered(lambda t: t.state in ('pending', 'authorized')):
                    raise ValidationError(_('Another payment is being processed. Please wait for its result.'))
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
        # Apply business consequences before native processing can commit while
        # rendering reports. A persisted native completion flag must not hide a
        # still-pending order change from subsequent polling/cron retries.
        self.filtered(lambda tx: tx.state == 'done').sale_order_ids.b2b_change_request_ids._on_order_payment_updated()
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

    def _cron_post_process(self):
        result = super()._cron_post_process()
        # Reuse the native payment recovery job, including older transactions
        # whose native flag was committed before a failed business hook.
        changes = self.env['b2b.order.change.request'].search([
            ('state', '=', 'balance_due'), ('order_id.state', '=', 'sale'),
        ])
        changes._on_order_payment_updated()
        return result


class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    @api.model
    def _get_compatible_providers(self, company_id, partner_id, amount, currency_id=None,
                                  force_tokenization=False, is_express_checkout=False,
                                  is_validation=False, report=None, **kwargs):
        providers = super()._get_compatible_providers(company_id, partner_id, amount,
            currency_id=currency_id, force_tokenization=force_tokenization,
            is_express_checkout=is_express_checkout, is_validation=is_validation,
            report=report, **kwargs)
        order = self.env['sale.order'].sudo().browse(kwargs.get('sale_order_id')).exists()
        if order.b2b_collection_active:
            # Use the order-specific bank/PI flow, not the provider's global bank message.
            providers = providers.filtered(lambda p: p.code != 'custom')
        return providers
