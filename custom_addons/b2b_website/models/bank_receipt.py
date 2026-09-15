import math

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


def check_finance(env):
    if not (env.is_superuser() or env.user.has_group('b2b_website.group_b2b_finance')):
        raise AccessError(env._('Only B2B Finance can confirm bank receipts.'))


class BankReceipt(models.Model):
    _name = 'b2b.bank.receipt'
    _description = 'Bank Transfer Evidence and Allocation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(default=lambda self: _('New'), readonly=True)
    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True)
    partner_id = fields.Many2one(related='order_id.partner_id', store=True)
    commercial_partner_id = fields.Many2one(related='order_id.partner_id.commercial_partner_id', store=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)
    state = fields.Selection([('submitted', 'Awaiting Finance'), ('returned', 'More Information Required'), ('rejected', 'Rejected'), ('confirmed', 'Receipt Confirmed')], default='submitted', required=True, readonly=True, tracking=True)
    declared_amount = fields.Monetary(required=True, string='Customer Declared Amount')
    transfer_date = fields.Date(required=True, default=fields.Date.context_today)
    transfer_reference = fields.Char(required=True)
    customer_note = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', string='Evidence')
    review_note = fields.Text(tracking=True)
    payment_id = fields.Many2one('account.payment', string='Native Bank Receipt', domain="[('payment_type','=','inbound'),('partner_type','=','customer'),('company_id','=',company_id)]", tracking=True)
    allocated_amount = fields.Float(string='Allocated Amount (Receipt Currency)', digits=(16, 2))
    payment_currency_id = fields.Many2one(related='payment_id.currency_id', string='Receipt Currency')
    order_amount = fields.Monetary(string='Confirmed Credit to Order', readonly=True)
    reviewed_by_id = fields.Many2one('res.users', readonly=True)
    reviewed_at = fields.Datetime(readonly=True)
    submission_key = fields.Char(copy=False, index=True)
    _submission_unique = models.Constraint('UNIQUE(order_id, submission_key)', 'This payment evidence has already been submitted.')

    @api.constrains('declared_amount', 'allocated_amount')
    def _check_amounts(self):
        for receipt in self:
            if not math.isfinite(receipt.declared_amount) or receipt.declared_amount <= 0 or not math.isfinite(receipt.allocated_amount) or receipt.allocated_amount < 0:
                raise ValidationError(_('Enter a valid positive transfer amount.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('state', 'submitted') != 'submitted' or set(vals) & {'order_amount', 'reviewed_at', 'reviewed_by_id'}:
                raise AccessError(_('Receipts must enter the finance review workflow.'))
            vals['name'] = self.env['ir.sequence'].next_by_code('b2b.bank.receipt') or _('Bank Receipt')
        records = super().create(vals_list)
        finance = self.env['res.users'].sudo().search([('active', '=', True), ('share', '=', False), ('all_group_ids', 'in', self.env.ref('b2b_website.group_b2b_finance').ids)], limit=1)
        if finance:
            for receipt in records:
                receipt.activity_schedule('mail.mail_activity_data_todo', user_id=finance.id, summary=_('Verify bank transfer %s', receipt.name))
        return records

    def write(self, vals):
        business = set(vals) - {'message_follower_ids', 'message_ids', 'activity_ids'}
        if business:
            check_finance(self.env)
            if business & {'state', 'order_amount', 'reviewed_at', 'reviewed_by_id', 'order_id'}:
                raise AccessError(_('Use the receipt review actions; workflow values cannot be edited directly.'))
            if self.filtered(lambda r: r.state == 'confirmed'):
                raise UserError(_('Confirmed allocations are immutable. Reverse the native payment through Finance if necessary.'))
        return super().write(vals)

    def unlink(self):
        raise UserError(_('Keep payment evidence for audit; reject incorrect submissions instead.'))

    def action_open_payment(self):
        check_finance(self.env)
        self.ensure_one()
        if self.payment_id:
            return {'type': 'ir.actions.act_window', 'res_model': 'account.payment', 'res_id': self.payment_id.id, 'view_mode': 'form', 'target': 'current'}
        return {'type': 'ir.actions.act_window', 'res_model': 'account.payment', 'view_mode': 'form', 'target': 'new', 'context': {
            'default_payment_type': 'inbound', 'default_partner_type': 'customer',
            'default_partner_id': self.commercial_partner_id.id,
            'default_company_id': self.company_id.id, 'default_currency_id': self.currency_id.id,
            'default_journal_id': self.order_id.b2b_receiving_journal_id.id,
            'default_amount': self.declared_amount, 'default_memo': '%s / %s' % (self.order_id.name, self.transfer_reference),
            'default_b2b_evidence_id': self.id,
        }}

    def action_confirm_receipt(self):
        check_finance(self.env)
        for receipt in self:
            receipt.order_id._b2b_lock_collection()
            self.env.cr.execute('SELECT id FROM b2b_bank_receipt WHERE id=%s FOR UPDATE', [receipt.id])
            receipt.invalidate_recordset()
            if receipt.state == 'confirmed':
                continue
            if receipt.state != 'submitted':
                raise UserError(_('Only awaiting-finance receipts can be confirmed.'))
            payment = receipt.payment_id
            if not payment:
                raise UserError(_('Select the actual native bank receipt first. Create it with Register / Open Receipt if needed.'))
            self.env.cr.execute('SELECT id FROM account_payment WHERE id=%s FOR UPDATE', [payment.id])
            if payment.state not in ('in_process', 'paid') or not payment.move_id or payment.move_id.state != 'posted':
                raise UserError(_('Post the native bank receipt with a configured outstanding-receipts account first.'))
            if payment.payment_type != 'inbound' or payment.partner_type != 'customer' or payment.company_id != receipt.company_id or payment.partner_id.commercial_partner_id != receipt.commercial_partner_id or payment.journal_id.type != 'bank':
                raise ValidationError(_('The receipt must belong to this customer and selling company and be an inbound bank payment.'))
            if self.env['payment.transaction'].sudo().search_count([('payment_id', '=', payment.id)], limit=1):
                raise ValidationError(_('This payment belongs to an online transaction and must not be counted again as a bank transfer.'))
            if payment.journal_id != receipt.order_id.b2b_receiving_journal_id and not receipt.review_note:
                raise ValidationError(_('Explain why the funds arrived in a different bank account.'))
            amount = receipt.allocated_amount
            other = self.sudo().search([('payment_id', '=', payment.id), ('state', '=', 'confirmed'), ('id', '!=', receipt.id)])
            if amount <= 0 or payment.currency_id.compare_amounts(sum(other.mapped('allocated_amount')) + amount, payment.amount) > 0:
                raise ValidationError(_('Allocate a positive amount without exceeding the actual bank receipt.'))
            credit = payment.currency_id._convert(amount, receipt.currency_id, receipt.company_id, payment.date)
            if receipt.currency_id.compare_amounts(credit, receipt.order_id.b2b_balance) > 0:
                raise ValidationError(_('Allocate only the outstanding order amount. Leave excess funds as an unallocated customer credit.'))
            super(BankReceipt, receipt).write({'state': 'confirmed', 'order_amount': credit, 'reviewed_by_id': self.env.uid, 'reviewed_at': fields.Datetime.now()})
            receipt.activity_ids.action_feedback(feedback=_('Bank receipt verified.'))
            receipt.order_id.message_post(body=_('Bank receipt %(receipt)s confirmed: %(amount)s %(currency)s.', receipt=receipt.name, amount=credit, currency=receipt.currency_id.name), partner_ids=receipt.partner_id.ids)
            receipt.order_id.sudo()._b2b_after_receipt()
        return True

    def _review_result(self, state):
        check_finance(self.env)
        for receipt in self:
            receipt.order_id._b2b_lock_collection()
            if receipt.state != 'submitted' or not receipt.review_note:
                raise UserError(_('Select an awaiting-finance submission and explain the review result.'))
            super(BankReceipt, receipt).write({'state': state, 'reviewed_by_id': self.env.uid, 'reviewed_at': fields.Datetime.now()})
            receipt.activity_ids.action_feedback(feedback=receipt.review_note)
            receipt.order_id.message_post(body=_('Payment evidence %(name)s: %(note)s', name=receipt.name, note=receipt.review_note), partner_ids=receipt.partner_id.ids)
        return True

    def action_return(self):
        return self._review_result('returned')

    def action_reject(self):
        return self._review_result('rejected')


class Payment(models.Model):
    _inherit = 'account.payment'

    b2b_evidence_id = fields.Many2one('b2b.bank.receipt', copy=False, readonly=True, ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        payments = super().create(vals_list)
        for payment in payments.filtered('b2b_evidence_id'):
            check_finance(self.env)
            receipt = payment.b2b_evidence_id
            if receipt.state != 'submitted' or receipt.payment_id or receipt.company_id != payment.company_id or receipt.commercial_partner_id != payment.partner_id.commercial_partner_id:
                raise ValidationError(_('This receipt cannot be linked to that evidence submission.'))
            receipt.write({'payment_id': payment.id, 'allocated_amount': payment.amount})
        return payments

    def write(self, vals):
        receipts = self.env['b2b.bank.receipt'].sudo().search([('payment_id', 'in', self.ids), ('state', '=', 'confirmed')])
        refunds = self.env['b2b.order.change.request'].sudo().search([('refund_payment_id', 'in', self.ids), ('state', '=', 'completed')])
        if refunds and set(vals) & {'amount', 'currency_id', 'partner_id', 'journal_id', 'date', 'payment_type', 'company_id'}:
            raise UserError(_('This refund is part of a completed adjustment; its accounting identity cannot be changed.'))
        if receipts and 'state' in vals:
            receipts.order_id._b2b_lock_collection()
        if refunds and 'state' in vals:
            refunds.order_id._b2b_lock_collection()
        if receipts and set(vals) & {'amount', 'currency_id', 'partner_id', 'journal_id', 'date', 'payment_type', 'company_id'}:
            raise UserError(_('This payment funds verified order allocations. Reverse it instead of changing its accounting identity.'))
        result = super().write(vals)
        if receipts and 'state' in vals:
            receipts.order_id.invalidate_recordset()
        if refunds and 'state' in vals:
            refunds.order_id.invalidate_recordset()
        return result
