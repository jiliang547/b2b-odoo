"""Submitted unpaid orders remain native, editable sale.order records."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    b2b_checkout_mode = fields.Selection(
        selection_add=[('pay_later', 'Save & Pay Later')],
        ondelete={'pay_later': 'set default'},
    )
    b2b_submitted_at = fields.Datetime(string='Website Order Submitted', readonly=True, copy=False)

    def _b2b_pending_bank_evidence(self):
        self.ensure_one()
        # Returned/rejected are completed reviews; the customer submits a new
        # evidence record. Old returned evidence must not lock the order forever.
        return self.sudo().b2b_receipt_ids.filtered(lambda receipt: receipt.state == 'submitted')

    def _b2b_unresolved_online_payments(self):
        self.ensure_one()
        pending = super()._b2b_unresolved_online_payments()
        if self.b2b_checkout_mode == 'pay_later':
            # Native PayPal can have a remote checkout before it reports a
            # pending/captured status. Do not edit or start a second payment
            # while that native draft transaction can still receive a callback.
            pending |= self.sudo().transaction_ids.filtered(lambda tx: tx.state == 'draft'
                and tx.operation not in ('refund', 'validation'))
        return pending

    def _b2b_save_for_later(self):
        self.ensure_one()
        self._b2b_lock_collection()
        if not self.website_id or self.state != 'draft' or self.b2b_is_change_revision:
            raise UserError(_('Only an active website cart can be saved as an unpaid order.'))
        self._b2b_check_unresolved_online_payments()
        if self.sudo().transaction_ids.filtered(lambda tx: tx.state == 'draft'
                and tx.operation not in ('refund', 'validation')):
            raise UserError(_('Resolve the existing payment attempt before saving this order.'))
        if self._b2b_pending_bank_evidence() or self._b2b_received_amount() > 0:
            raise UserError(_('Resolve the existing payment before saving this order.'))
        for line in self.order_line.filtered(lambda line: not line.display_type and not line.is_delivery):
            self._b2b_check_product_allowed(line.product_id.id)
            self._b2b_validate_sale_quantity(line.product_id.id, line.product_uom_qty)
        self.write({'b2b_checkout_mode': 'pay_later', 'b2b_review_state': 'none',
                    'b2b_submitted_at': fields.Datetime.now()})
        self._b2b_start_collection()
        # Native sent is the submitted, editable record, not production release.
        # Do not call action_confirm, issue a PI or enqueue an ERP write here.
        self.action_quotation_sent()
        self.message_post(body=_('The customer saved this order for later payment.'))

    @api.depends('state', 'b2b_checkout_mode')
    @api.depends_context('lang')
    def _compute_type_name(self):
        super()._compute_type_name()
        for order in self.filtered(lambda order: order.b2b_checkout_mode == 'pay_later'):
            order.type_name = _('Order')

    def _has_to_be_paid(self):
        self.ensure_one()
        if self.b2b_checkout_mode == 'pay_later' and self.b2b_review_state != 'pending':
            return (self.state in ('draft', 'sent') and not self.is_expired
                    and self.currency_id.compare_amounts(self.b2b_balance, 0) > 0
                    and not self._b2b_pending_bank_evidence()
                    and not self._b2b_unresolved_online_payments())
        return super()._has_to_be_paid()

    def _has_to_be_signed(self):
        self.ensure_one()
        # The customer has already submitted a website order. Preserve native
        # quotation signatures elsewhere, but do not insert Sign & Pay here.
        if self.b2b_checkout_mode == 'pay_later':
            return False
        return super()._has_to_be_signed()

    def _b2b_customer_order_status(self):
        self.ensure_one()
        if self.b2b_checkout_mode == 'pay_later' and self.state in ('draft', 'sent'):
            if self._b2b_unresolved_online_payments():
                return _('Payment Processing')
            if self._b2b_pending_bank_evidence():
                return _('Payment Verification Pending')
            if self.b2b_net_received > 0:
                return _('Partially Paid')
            return _('Awaiting Payment')
        return super()._b2b_customer_order_status()

    def _b2b_check_commercial_edit(self):
        super()._b2b_check_commercial_edit()
        # Confirmed orders continue through the existing order-change workflow.
        # Also protect partial receipts which have not confirmed the order yet.
        for order in self.filtered(lambda order: order.b2b_checkout_mode == 'pay_later'
                                   and order.state in ('draft', 'sent')):
            if order._b2b_pending_bank_evidence():
                raise UserError(_('Finance must review the bank evidence before products, quantities or prices can be changed.'))
            if order.currency_id.compare_amounts(order._b2b_received_amount(), 0) > 0:
                raise UserError(_('This order has already received funds. Finance must resolve the receipt before an unpaid order can be edited.'))

    def action_b2b_allow_saved_order_payment(self):
        """Explicit conversion only: never silently release historical reviews."""
        if not self.env.is_superuser() and not self.env.user.has_group('b2b_core.group_b2b_manager'):
            raise AccessError(_('Only a B2B Manager can release a saved order.'))
        self.check_access('write')
        for order in self:
            order._b2b_lock_collection()
            if not order.website_id or order.state != 'sent' or order.b2b_review_state != 'pending':
                raise UserError(_('Select a website order awaiting review.'))
            order._b2b_check_unresolved_online_payments()
            if order.sudo().transaction_ids.filtered(lambda tx: tx.state == 'draft'
                    and tx.operation not in ('refund', 'validation')):
                raise UserError(_('Resolve the existing payment attempt before releasing this order.'))
            if order._b2b_pending_bank_evidence() or order._b2b_received_amount() > 0:
                raise UserError(_('Resolve existing payments and bank evidence before releasing this order.'))
            order.write({'b2b_checkout_mode': 'pay_later', 'b2b_review_state': 'none',
                         'b2b_submitted_at': order.b2b_submitted_at or fields.Datetime.now()})
            order._b2b_start_collection()
            # Historical review submissions sometimes required 100% online
            # payment. Restore native payment settings from this order's
            # frozen collection threshold, not today's customer template.
            order.write({'require_payment': order.b2b_production_percent > 0,
                         'prepayment_percent': order.b2b_production_percent / 100 or 1.0})
            order.message_post(body=_('Operations made this saved order available for later payment.'))
        return True
