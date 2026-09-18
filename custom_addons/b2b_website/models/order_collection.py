import base64
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .collection_policy import check_manager


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _b2b_quote_token(self):
        self.ensure_one()
        values = self.env['b2b.order.change.request']._snapshot_order(self)
        values.update(company=self.company_id.id, customer=self.partner_id.id,
                      currency_id=self.currency_id.id, terms=self.payment_term_id.id,
                      production=self.b2b_production_percent, shipment=self.b2b_shipment_percent)
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    def _b2b_unresolved_online_payments(self):
        """Return online transactions that can still capture or settle funds."""
        self.ensure_one()
        return self.sudo().transaction_ids.filtered(
            lambda tx: tx.operation not in ('refund', 'validation')
            and tx.state in ('pending', 'authorized')
        )

    def _b2b_resolve_safe_demo_payment_conflicts(self):
        """Cancel only simulated transactions when another payment path won.

        Demo transactions never move real money, so leaving one pending after a
        verified bank receipt only creates a false commercial-edit lock. Real
        providers remain fail-closed until their provider status is resolved.
        """
        for order in self:
            demo_transactions = order._b2b_unresolved_online_payments().filtered(
                lambda tx: tx.provider_code == 'demo'
            )
            if not demo_transactions:
                continue
            references = ', '.join(demo_transactions.mapped('reference'))
            demo_transactions._set_canceled(state_message=_(
                'Canceled because the order was completed through another verified payment method.'
            ))
            order.message_post(body=_(
                'Pending Demo payment %(references)s was canceled because another verified payment method was used.',
                references=references,
            ))

    def _b2b_check_unresolved_online_payments(self):
        for order in self:
            pending = order._b2b_unresolved_online_payments()
            if pending:
                raise UserError(_(
                    'Online payment %(references)s is still being processed. '
                    'Open the order payment transactions and resolve it before continuing.',
                    references=', '.join(pending.mapped('reference')),
                ))

    def _b2b_check_commercial_edit(self):
        for order in self.filtered(lambda o: o.b2b_collection_active and not o.b2b_is_change_revision):
            order._b2b_lock_collection()
            if order.currency_id.compare_amounts(order.b2b_balance, 0) <= 0:
                order._b2b_resolve_safe_demo_payment_conflicts()
            order._b2b_check_unresolved_online_payments()

    b2b_collection_active = fields.Boolean(copy=False, readonly=True)
    b2b_collection_policy_id = fields.Many2one('b2b.collection.policy', string='Production / Shipment Collection Conditions', copy=True, tracking=True)
    b2b_payment_configuration_warning = fields.Text(compute='_compute_b2b_payment_configuration_warning')
    b2b_collection_category = fields.Selection([(c, c) for c in 'ABCDE'], readonly=True, copy=True)
    b2b_production_percent = fields.Float(readonly=True, copy=True)
    b2b_shipment_percent = fields.Float(readonly=True, copy=True)

    @api.depends('b2b_collection_active', 'payment_term_id', 'b2b_collection_policy_id.payment_term_id',
                 'b2b_production_percent', 'b2b_shipment_percent', 'require_payment', 'prepayment_percent')
    def _compute_b2b_payment_configuration_warning(self):
        for order in self:
            warnings = []
            if order.b2b_collection_active:
                reference = order.b2b_collection_policy_id.payment_term_id
                if reference and order.payment_term_id != reference:
                    warnings.append(_('The invoice payment terms on this order differ from the current collection template. Review both settings; neither is automatically synchronized when you edit the order payment terms.'))
                if order.b2b_shipment_percent < 100 and not order.payment_term_id:
                    warnings.append(_('This order allows shipment before full payment but has no invoice payment terms. Configure the native invoice due dates.'))
                requires_payment = order.b2b_production_percent > 0
                if (order.require_payment != requires_payment or (requires_payment
                        and abs(order.prepayment_percent * 100 - order.b2b_production_percent) > 0.00001)):
                    warnings.append(_('The online prepayment setting differs from the production collection threshold. Review the settings before requesting payment.'))
            order.b2b_payment_configuration_warning = '\n'.join(warnings) or False
    b2b_block_overdue = fields.Boolean(readonly=True, copy=True)
    b2b_brand_id = fields.Many2one('b2b.product.brand', string='Order Brand', tracking=True, copy=True)
    b2b_receiving_journal_id = fields.Many2one('account.journal', string='Receiving Bank Journal', tracking=True, copy=True)
    b2b_bank_instructions = fields.Text(readonly=True, copy=False)
    b2b_pi_bank_instructions = fields.Text(readonly=True, copy=False)
    b2b_brand_logo = fields.Binary(readonly=True, copy=True, attachment=True)
    b2b_configuration_reason = fields.Char(string='Reason for Configuration Change', copy=False)
    b2b_receipt_ids = fields.One2many('b2b.bank.receipt', 'order_id')
    b2b_pi_ids = fields.One2many('b2b.order.pi', 'order_id')
    b2b_net_received = fields.Monetary(compute='_compute_collection_summary')
    b2b_pending_proof = fields.Monetary(compute='_compute_collection_summary')
    b2b_balance = fields.Monetary(compute='_compute_collection_summary')
    b2b_payable_now = fields.Monetary(compute='_compute_collection_summary')
    b2b_production_allowed = fields.Boolean(compute='_compute_collection_summary')
    b2b_shipment_allowed = fields.Boolean(compute='_compute_collection_summary')
    b2b_collection_status = fields.Char(compute='_compute_collection_summary')
    b2b_unresolved_payment_count = fields.Integer(compute='_compute_b2b_unresolved_payment_count')
    b2b_balance_payment_requested = fields.Boolean(readonly=True, copy=False, tracking=True)

    @api.depends('transaction_ids.state', 'transaction_ids.operation')
    def _compute_b2b_unresolved_payment_count(self):
        for order in self:
            order.b2b_unresolved_payment_count = len(order._b2b_unresolved_online_payments())

    def action_b2b_open_unresolved_payments(self):
        self.ensure_one()
        if not (self.env.is_superuser()
                or self.env.user.has_group('b2b_core.group_b2b_manager')
                or self.env.user.has_group('b2b_website.group_b2b_finance')):
            raise AccessError(_('Only an authorized manager or finance user can review payment transactions.'))
        transactions = self._b2b_unresolved_online_payments()
        action = self.env['ir.actions.actions']._for_xml_id('payment.action_payment_transaction')
        action['domain'] = [('id', 'in', transactions.ids)]
        action['context'] = {'create': False}
        if len(transactions) == 1:
            action.update(res_id=transactions.id, view_mode='form', views=[(False, 'form')])
        return action

    def _b2b_customer_terms_label(self):
        """Customer wording derived from the immutable order thresholds."""
        self.ensure_one()
        if not self.b2b_collection_active:
            return _('Pending confirmation')
        if self.b2b_collection_category == 'A':
            return _('100% advance payment')
        if self.b2b_collection_category == 'B':
            return _('%(deposit)s%% deposit, %(balance)s%% before shipment',
                     deposit='%g' % self.b2b_production_percent,
                     balance='%g' % (100 - self.b2b_production_percent))
        if self.b2b_collection_category == 'C':
            return _('100% before shipment')
        if self.b2b_collection_category == 'D':
            return self.payment_term_id.name or _('Agreed credit terms')
        return _('As agreed with our team')

    def _b2b_customer_order_status(self):
        self.ensure_one()
        if self.state == 'cancel':
            return _('Order Cancelled')
        if self.state == 'sale':
            return _('Order Confirmed')
        if self.b2b_review_state == 'pending':
            return _('Awaiting Final Quote')
        if self.b2b_review_state == 'ready':
            return _('Ready for Payment')
        return _('Quotation')

    def _b2b_portal_payment_summary(self):
        """Presentation only: use verified funds, never declared proof amounts."""
        self.ensure_one()
        paid = self.b2b_net_received
        balance = self.b2b_balance
        compare = self.currency_id.compare_amounts
        deposit = self.currency_id.round(self.amount_total * self.b2b_production_percent / 100)
        if self.state == 'cancel':
            label = _('Order Cancelled')
        elif compare(balance, 0) <= 0:
            label = _('Fully Paid') if compare(self.amount_total, 0) > 0 else _('No Payment Required')
        elif self.b2b_review_state == 'pending':
            label = _('Awaiting Final Quote')
        elif compare(paid, deposit) < 0:
            label = _('Deposit Payment Required') if self.b2b_collection_category == 'B' else _('Payment Required')
        elif self.b2b_change_payment_hold:
            label = _('Order Change Under Review')
        elif self.b2b_balance_payment_requested:
            label = _('Balance Payment Required')
        elif self.b2b_collection_category == 'B' and compare(paid, 0) > 0:
            label = _('Deposit Received · Balance Outstanding')
        elif compare(paid, 0) > 0:
            label = _('Partially Paid · Balance Outstanding')
        else:
            label = _('Balance Outstanding')
        # sudo is limited to an aggregate, after the portal authorizes the order.
        pending = bool(self.sudo().b2b_receipt_ids.filtered(lambda r: r.state == 'submitted'))
        online_pending = bool(self._b2b_unresolved_online_payments())
        return {'label': label, 'pending': pending, 'online_pending': online_pending, 'requested': (
            self.b2b_balance_payment_requested and self.state == 'sale'
            and compare(balance, 0) > 0 and self.b2b_review_state != 'pending'
            and not self.b2b_change_payment_hold)}

    def action_b2b_request_balance_payment(self):
        check_manager(self.env)
        self.check_access('write')
        for order in self:
            order._b2b_lock_collection()
            if (not order.b2b_collection_active or order.state != 'sale'
                    or order.currency_id.compare_amounts(order.b2b_balance, 0) <= 0
                    or order.b2b_review_state == 'pending' or order.b2b_change_payment_hold):
                raise UserError(_('Request a balance payment only on a confirmed order with an outstanding balance and no review hold.'))
            if order.b2b_balance_payment_requested:
                continue
            super(SaleOrder, order).write({'b2b_balance_payment_requested': True})
            order.with_context(mail_notify_force_send=False).message_post(
                body=_('Please pay the remaining balance for order %s. Open Payments, Bank Transfer & PI in your account to view the current amount and payment instructions.', order.name),
                partner_ids=order.partner_id.ids, subtype_xmlid='mail.mt_comment')
        return True

    @api.model
    def get_view(self, view_id=None, view_type='form', **options):
        if (view_type == 'form' and not self.env.is_superuser()
                and self.env.user.has_group('b2b_website.group_b2b_finance')
                and not self.env.user.has_group('sales_team.group_sale_salesman')):
            view_id = self.env.ref('b2b_website.collection_finance_order_form').id
        return super().get_view(view_id=view_id, view_type=view_type, **options)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('b2b_balance_payment_requested') and not self.env.is_superuser():
                raise AccessError(_('Use Request Balance Payment to notify the customer.'))
            if set(vals) & {'b2b_collection_policy_id', 'b2b_brand_id', 'b2b_receiving_journal_id', 'b2b_collection_active', 'b2b_production_percent', 'b2b_shipment_percent'}:
                check_manager(self.env)
                if not self.env.is_superuser() and vals.get('b2b_collection_active'):
                    raise AccessError(_('Collection activation is controlled by order submission.'))
        orders = super().create(vals_list)
        for order in orders.filtered('b2b_receiving_journal_id'):
            snapshots = {}
            if not order.b2b_bank_instructions:
                snapshots['b2b_bank_instructions'] = order._b2b_bank_text(order.b2b_receiving_journal_id)
            if not order.b2b_pi_bank_instructions:
                snapshots['b2b_pi_bank_instructions'] = order._b2b_pi_bank_text(order.b2b_receiving_journal_id)
            if snapshots:
                super(SaleOrder, order).write(snapshots)
        return orders

    def _b2b_lock_collection(self):
        if self.ids:
            # Serialize company-wide credit decisions, including simultaneous
            # submissions on different orders for the same customer.
            customers = self.sudo().partner_id.commercial_partner_id
            self.env.cr.execute('SELECT id FROM res_partner WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(customers.ids)])
            self.env.cr.execute('SELECT id FROM sale_order WHERE id IN %s ORDER BY id FOR UPDATE', [tuple(self.ids)])
            self.invalidate_recordset()

    def _b2b_collection_defaults(self):
        self.ensure_one()
        customer = self.partner_id.commercial_partner_id
        policy = self.b2b_collection_policy_id or customer.b2b_collection_policy_id or self.env.ref('b2b_website.collection_policy_a')
        brand = self.b2b_brand_id or customer.b2b_account_brand_id or self.website_id.b2b_default_account_brand_id
        candidates = brand.sudo().b2b_collection_journal_ids.filtered(lambda j: j.company_id == self.company_id and j.active and j.bank_account_id and (j.currency_id or j.company_id.currency_id) == self.currency_id)
        journal = self.b2b_receiving_journal_id or candidates.sorted('id')[:1]
        values = {
            'b2b_collection_active': True, 'b2b_collection_policy_id': policy.id,
            'b2b_collection_category': policy.category, 'b2b_production_percent': policy.production_percent,
            'b2b_shipment_percent': policy.shipment_percent, 'b2b_block_overdue': policy.block_overdue,
            'b2b_brand_id': brand.id, 'b2b_receiving_journal_id': journal.id,
            'b2b_brand_logo': brand.logo, 'b2b_bank_instructions': self._b2b_bank_text(journal),
            'b2b_pi_bank_instructions': self._b2b_pi_bank_text(journal),
            'require_payment': policy.production_percent > 0,
            'prepayment_percent': policy.production_percent / 100 if policy.production_percent else 1.0,
        }
        if policy.payment_term_id:
            values['payment_term_id'] = policy.payment_term_id.id
        return values

    def _b2b_bank_text(self, journal):
        if not journal:
            return ''
        bank = journal.bank_account_id
        return '\n'.join(filter(None, [
            _('Beneficiary: %s', bank.acc_holder_name or self.company_id.name),
            _('Bank: %s', bank.bank_id.name or ''),
            _('Account: %s', bank.acc_number or ''),
            _('SWIFT/BIC: %s', bank.bank_id.bic or ''),
            _('Currency: %s', (journal.currency_id or journal.company_id.currency_id).name),
            _('Payment reference: %s', self.name),
        ]))

    def _b2b_pi_bank_text(self, journal):
        """Snapshot complete wire details for the PI without expanding the portal card."""
        if not journal:
            return ''
        account = journal.bank_account_id
        bank = account.bank_id
        company_partner = journal.company_id.partner_id
        currency = journal.currency_id or journal.company_id.currency_id
        company_address = company_partner._display_address(without_company=True)
        bank_address = ', '.join(filter(None, [
            bank.street, bank.street2, bank.city, bank.state.name,
            bank.zip, bank.country.name,
        ])) if bank else ''
        details = [
            _('Beneficiary: %s', account.acc_holder_name or journal.company_id.name),
            _('%(currency)s Account No.: %(account)s', currency=currency.name, account=account.acc_number),
            _('SWIFT/BIC: %s', bank.bic or '') if bank else '',
            _('Beneficiary Address: %s', ', '.join(line.strip() for line in company_address.splitlines() if line.strip())) if company_address else '',
            _('Bank Name: %s', bank.name or '') if bank else '',
            _('Bank Address: %s', bank_address) if bank_address else '',
            _('Clearing Number: %s', account.clearing_number) if account.clearing_number else '',
            account.note and account.note.strip(),
            _('Currency: %s', currency.name),
            _('Payment reference: %s', self.name),
        ]
        return '\n'.join(filter(None, details))

    def _b2b_loading_native_demo(self):
        # Native load_demo uses sudo + install_demo, including force_demo on
        # an already-ready registry. Never trust a request context flag alone.
        # Already active collection orders still pass every release check.
        return bool(self.env.su and self.env.context.get('install_demo'))

    def _b2b_start_collection(self):
        if self._b2b_loading_native_demo():
            return
        for order in self.filtered(lambda o: o.website_id and o.state in ('draft', 'sent')
                                   and not o.b2b_is_change_revision and not o.b2b_sample_request_id
                                   and not o.b2b_collection_active):
            order._b2b_lock_collection()
            if not order.b2b_collection_active:
                super(SaleOrder, order).write(order._b2b_collection_defaults())

    def action_b2b_refresh_collection(self):
        check_manager(self.env)
        self.check_access('write')
        for order in self:
            order._b2b_lock_collection()
            if order.state not in ('draft', 'sent') or order.sudo().transaction_ids.filtered(lambda t: t.state in ('pending', 'authorized')):
                raise UserError(_('Change collection configuration only before confirmation and with no payment in progress.'))
            if not order.b2b_configuration_reason:
                raise UserError(_('Record the reason before applying collection configuration.'))
            super(SaleOrder, order).write(order._b2b_collection_defaults())
            order.message_post(body=_('Collection instructions changed: %s. Please download the latest PI.', order.b2b_configuration_reason), partner_ids=order.partner_id.ids)
        return True

    def write(self, vals):
        if set(vals) & {'order_line', 'currency_id', 'pricelist_id', 'partner_id', 'payment_term_id', 'fiscal_position_id'}:
            self._b2b_check_commercial_edit()
        if 'b2b_balance_payment_requested' in vals and not self.env.is_superuser():
            raise AccessError(_('Use Request Balance Payment to notify the customer.'))
        protected = {'b2b_collection_active', 'b2b_collection_category', 'b2b_production_percent', 'b2b_shipment_percent', 'b2b_block_overdue', 'b2b_brand_logo', 'b2b_bank_instructions', 'b2b_pi_bank_instructions'}
        if set(vals) & protected and not self.env.is_superuser():
            raise AccessError(_('Collection snapshots are maintained by the collection workflow.'))
        configuration = {'b2b_collection_policy_id', 'b2b_brand_id', 'b2b_receiving_journal_id'}
        if set(vals) & configuration:
            check_manager(self.env)
            self.check_access('write')
            if self.filtered(lambda o: o.state == 'cancel') or ('b2b_collection_policy_id' in vals and self.filtered(lambda o: o.state not in ('draft', 'sent'))):
                raise UserError(_('Confirmed order payment terms are frozen. Only the approved receiving account and brand may be changed with a reason.'))
        if set(vals) & {'require_payment', 'prepayment_percent'} and self.filtered('b2b_collection_active'):
            check_manager(self.env)
        if vals.get('state') == 'sale':
            for order in self.filtered(lambda o: o.website_id and not o.b2b_is_change_revision
                                       and (o.b2b_collection_active or not o._b2b_loading_native_demo())):
                order._b2b_start_collection()
                if not order._b2b_can_produce():
                    raise UserError(_('Production is blocked: review, required funds or credit checks are incomplete.'))
        configured = self.filtered('b2b_collection_active') if set(vals) & configuration else self.browse()
        for order in configured:
            order._b2b_lock_collection()
            if order.sudo().transaction_ids.filtered(lambda t: t.state in ('pending', 'authorized')) or order.b2b_receipt_ids.filtered(lambda r: r.state == 'submitted'):
                raise UserError(_('Finish pending payment and evidence reviews before changing collection instructions.'))
            if not (vals.get('b2b_configuration_reason') or order.b2b_configuration_reason):
                raise UserError(_('Record a reason before changing collection configuration.'))
        if 'b2b_brand_id' in vals and 'b2b_receiving_journal_id' not in vals:
            vals = dict(vals, b2b_receiving_journal_id=False)
        result = super().write(vals)
        for order in configured:
            snapshot = order._b2b_collection_defaults()
            if order.state not in ('draft', 'sent'):
                snapshot = {key: value for key, value in snapshot.items() if key in {'b2b_brand_id', 'b2b_receiving_journal_id', 'b2b_brand_logo', 'b2b_bank_instructions', 'b2b_pi_bank_instructions'}}
            super(SaleOrder, order).write(snapshot)
            order.message_post(body=_('Collection instructions updated: %s. Please download the latest PI.', order.b2b_configuration_reason), partner_ids=order.partner_id.ids)
        return result

    @api.constrains('b2b_receiving_journal_id', 'b2b_brand_id', 'company_id', 'currency_id')
    def _b2b_check_receiving_account(self):
        for order in self:
            journal = order.b2b_receiving_journal_id
            if journal and (journal.type != 'bank' or journal.company_id != order.company_id or not journal.bank_account_id or journal not in order.b2b_brand_id.sudo().b2b_collection_journal_ids or (journal.currency_id or journal.company_id.currency_id) != order.currency_id):
                raise ValidationError(_('Choose a bank account assigned to this brand, selling company and order currency.'))

    def _b2b_received_amount(self):
        self.ensure_one()
        # Expose only the aggregate through the already-authorized order. Bank
        # evidence and accounting records retain their separate ACLs.
        self = self.sudo()
        transactions = self.transaction_ids.filtered(lambda t: t.state == 'done' and t.operation != 'validation')
        refunds = transactions.child_transaction_ids.filtered(lambda t: t.state == 'done' and t.operation == 'refund') - transactions
        amount = sum(transactions.mapped('amount')) - sum(abs(t.amount) for t in refunds)
        for receipt in self.b2b_receipt_ids.filtered('accounting_effective'):
            # A native transaction payment is already counted above.
            if receipt.payment_id not in transactions.mapped('payment_id'):
                amount += receipt.order_amount
        for change in self.b2b_change_request_ids.filtered(lambda c: c.state == 'completed' and c.delta_amount < 0 and not c.refund_transaction_id):
            payment = change.refund_payment_id
            if (payment and payment.state in ('in_process', 'paid') and payment.move_id.state == 'posted'
                    and payment.payment_type == 'outbound' and payment.partner_type == 'customer'
                    and payment.company_id == self.company_id
                    and payment.partner_id.commercial_partner_id == self.partner_id.commercial_partner_id
                    and not payment.payment_transaction_id):
                amount -= payment.currency_id._convert(payment.amount, self.currency_id, payment.company_id, payment.date)
        return self.currency_id.round(amount)

    @api.depends('b2b_collection_active', 'transaction_ids.state', 'transaction_ids.amount', 'transaction_ids.child_transaction_ids.state', 'transaction_ids.child_transaction_ids.amount', 'b2b_receipt_ids.state', 'b2b_receipt_ids.order_amount', 'b2b_receipt_ids.payment_id.state', 'b2b_receipt_ids.payment_id.move_id.state', 'b2b_change_request_ids.state', 'b2b_change_request_ids.delta_amount', 'b2b_change_request_ids.refund_amount', 'b2b_change_request_ids.refund_transaction_id', 'b2b_change_request_ids.refund_payment_id.state')
    def _compute_amount_paid(self):
        super()._compute_amount_paid()
        for order in self.filtered('b2b_collection_active'):
            order.amount_paid = order._b2b_received_amount()

    def _b2b_credit_ok(self):
        self.ensure_one()
        if self.b2b_shipment_percent >= 100:
            return True
        customer = self.partner_id.commercial_partner_id.sudo().with_company(self.company_id)
        if self.b2b_block_overdue and self.env['account.move.line'].sudo().search_count([
            ('company_id', '=', self.company_id.id), ('partner_id', 'child_of', customer.id),
            ('account_id.account_type', '=', 'asset_receivable'), ('parent_state', '=', 'posted'),
            ('date_maturity', '<', fields.Date.today()), ('amount_residual', '>', 0),
        ], limit=1):
            return False
        if self.company_id.account_use_credit_limit:
            # Reuse native receivables + credit_to_invoice calculation. A
            # second receipt subtraction would double-count accounting credits.
            order = self.sudo().with_company(self.company_id)
            customer.invalidate_recordset(['credit', 'credit_to_invoice'])
            current_amount = order.amount_total / order.currency_rate if order.state in ('draft', 'sent') else 0
            commitments = order.search([('partner_invoice_id.commercial_partner_id', '=', customer.id),
                ('company_id', '=', order.company_id.id), ('state', '=', 'sale')])
            for commitment in commitments:
                # Native credit_to_invoice excludes undelivered quantities for
                # delivery-based invoicing. Include just that missing portion.
                gap = max(commitment.amount_total - commitment.amount_invoiced - commitment.amount_to_invoice, 0)
                current_amount += commitment.currency_id._convert(gap, order.company_id.currency_id,
                    order.company_id, fields.Date.context_today(order))
            return not self.env['account.move'].sudo().with_company(self.company_id)._build_credit_warning_message(
                order, current_amount=current_amount)
        return True

    def _b2b_can_produce(self):
        self.ensure_one()
        return self.b2b_review_state != 'pending' and not self.b2b_is_change_revision and self._b2b_credit_ok() and self.currency_id.compare_amounts(self._b2b_received_amount(), self.currency_id.round(self.amount_total * self.b2b_production_percent / 100)) >= 0

    def _b2b_can_ship(self):
        self.ensure_one()
        return self.state == 'sale' and not self.b2b_change_payment_hold and self._b2b_refunds_settled() and self._b2b_credit_ok() and self.currency_id.compare_amounts(self._b2b_received_amount(), self.currency_id.round(self.amount_total * self.b2b_shipment_percent / 100)) >= 0

    def _b2b_refunds_settled(self):
        """Fail closed for old invalid completions or subsequently reversed refunds."""
        self.ensure_one()
        for change in self.sudo().b2b_change_request_ids.filtered(lambda c: c.collection_adjustment and c.state == 'completed' and c.refund_amount > 0):
            refund = change.refund_transaction_id
            payment = change.refund_payment_id
            if refund:
                if (refund.state != 'done' or refund.operation != 'refund'
                        or self not in refund.source_transaction_id.sale_order_ids
                        or refund.currency_id != self.currency_id
                        or self.currency_id.compare_amounts(abs(refund.amount), change.refund_amount)):
                    return False
            elif (not payment or payment.state not in ('in_process', 'paid')
                    or payment.move_id.state != 'posted' or payment.payment_type != 'outbound'
                    or payment.partner_id.commercial_partner_id != self.partner_id.commercial_partner_id
                    or payment.company_id != self.company_id
                    or self.currency_id.compare_amounts(payment.currency_id._convert(payment.amount, self.currency_id, payment.company_id, payment.date), change.refund_amount)):
                return False
        return True

    @api.depends('amount_total', 'amount_paid', 'state', 'b2b_receipt_ids.state', 'b2b_receipt_ids.order_amount', 'b2b_receipt_ids.payment_id.state', 'b2b_receipt_ids.declared_amount', 'transaction_ids.state', 'b2b_production_percent', 'b2b_shipment_percent', 'b2b_change_payment_hold')
    def _compute_collection_summary(self):
        for order in self:
            paid = order._b2b_received_amount()
            order.b2b_net_received = paid
            order.b2b_pending_proof = sum(order.b2b_receipt_ids.filtered(lambda r: r.state == 'submitted').mapped('declared_amount'))
            order.b2b_balance = max(order.amount_total - paid, 0)
            # An accepted increase can make the original deposit insufficient
            # even though the native order remains confirmed. Collect the
            # missing deposit first, not the entire pre-shipment balance.
            production_due = order.currency_id.compare_amounts(
                paid, order.currency_id.round(order.amount_total * order.b2b_production_percent / 100)) < 0
            threshold = order.b2b_production_percent if order.state in ('draft', 'sent') or production_due else order.b2b_shipment_percent
            order.b2b_payable_now = max(order.currency_id.round(order.amount_total * threshold / 100) - paid, 0)
            order.b2b_production_allowed = order._b2b_can_produce()
            order.b2b_shipment_allowed = order._b2b_can_ship()
            order.b2b_collection_status = _('Paid in full') if order.b2b_balance == 0 else (_('Partially received') if paid > 0 else _('Not received'))

    def _is_confirmation_amount_reached(self):
        self.ensure_one()
        if self.b2b_collection_active:
            return self._b2b_can_produce()
        return super()._is_confirmation_amount_reached()

    def action_confirm(self):
        self._b2b_lock_collection()
        self._b2b_start_collection()
        for order in self.filtered('b2b_collection_active'):
            if not order._b2b_can_produce():
                raise UserError(_('Required prepayment or credit approval is missing. Confirm actual receipts before production.'))
        return super().action_confirm()

    def action_b2b_mark_review_ready(self):
        result = super().action_b2b_mark_review_ready()
        self._b2b_start_collection()
        for order in self:
            super(SaleOrder, order).write({'require_payment': order.b2b_production_percent > 0, 'prepayment_percent': order.b2b_production_percent / 100 or 1.0})
        return result

    def _b2b_after_receipt(self):
        for order in self:
            order.invalidate_recordset()
            if order.state in ('draft', 'sent') and order._b2b_can_produce():
                order.action_confirm()
            order.b2b_change_request_ids._on_order_payment_updated()

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        if self.b2b_collection_active:
            bank = self.b2b_receiving_journal_id.bank_account_id
            if not bank:
                raise UserError(_('Configure the order receiving bank account before invoicing.'))
            # Use the native invoice bank field, not a parallel report-only value.
            values['partner_bank_id'] = bank.id
        return values

    def _get_invoice_grouping_keys(self):
        keys = super()._get_invoice_grouping_keys()
        if self.filtered('b2b_collection_active'):
            # Each collection order has its own payment instructions and PI.
            # Do not merge those instructions into a different order's invoice.
            keys = list(dict.fromkeys([*keys, 'invoice_origin']))
        return keys

    def _b2b_issue_pi(self):
        self.ensure_one()
        self._b2b_lock_collection()
        self._b2b_start_collection()
        if self.b2b_review_state == 'pending' or self.state == 'cancel' or self.b2b_is_change_revision:
            raise UserError(_('The order must be released before a payment PI can be issued.'))
        if not self.b2b_brand_id or not self.b2b_receiving_journal_id:
            raise UserError(_('Our team must configure the order brand and receiving bank account first.'))
        payload = json.dumps(['pi-layout-v4', self._get_lang(), self.currency_id.name,
            self.company_id.partner_id._display_address(), self.partner_id._display_address(),
            self.partner_invoice_id._display_address(), self.partner_shipping_id._display_address(),
            self.client_order_ref, str(self.date_order), str(self.validity_date), self.payment_term_id.name,
            self.amount_total, self.b2b_net_received, self.b2b_payable_now,
            self.b2b_bank_instructions, self.b2b_pi_bank_instructions,
            self.b2b_collection_category, self.b2b_collection_policy_id.name, self.b2b_production_percent,
            self.b2b_shipment_percent, self.b2b_brand_logo.decode() if self.b2b_brand_logo else '',
            self.partner_id.display_name, [(l.name, l.product_uom_qty, l.product_uom_id.name,
                l.price_unit, l.discount, l.price_subtotal, l.price_tax) for l in self.order_line]], ensure_ascii=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        previous = self.b2b_pi_ids.filtered(lambda p: p.digest == digest)[:1]
        if previous:
            return previous
        pdf, _fmt = self.env['ir.actions.report']._render_qweb_pdf('b2b_website.action_report_collection_pi', res_ids=self.ids)
        return self.env['b2b.order.pi'].create({'order_id': self.id, 'revision': len(self.b2b_pi_ids) + 1, 'digest': digest, 'pdf': base64.b64encode(pdf)})

    def action_b2b_download_pi(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': '/my/orders/%s/collection/pi' % self.id, 'target': 'new'}


class OrderPI(models.Model):
    _name = 'b2b.order.pi'
    _description = 'Issued Order PI'
    _order = 'id desc'
    order_id = fields.Many2one('sale.order', required=True, ondelete='restrict')
    revision = fields.Integer(required=True)
    digest = fields.Char(required=True)
    pdf = fields.Binary(attachment=True, required=True)
    _unique_revision = models.Constraint('UNIQUE(order_id, revision)', 'PI revision already exists.')

    def write(self, vals):
        raise UserError(_('Issued PI files are immutable. Issue a new version instead.'))

    def unlink(self):
        raise UserError(_('Issued PI files must be retained.'))


class Picking(models.Model):
    _inherit = 'stock.picking'

    def _b2b_check_collection_release(self):
        for picking in self.filtered(lambda p: p.picking_type_id.code == 'outgoing' and p.sale_id.b2b_collection_active):
            picking.sale_id._b2b_lock_collection()
            if not picking.sale_id._b2b_can_ship():
                raise UserError(_('Shipment blocked: the required balance, credit checks or change review is not complete.'))

    def button_validate(self):
        self._b2b_check_collection_release()
        return super().button_validate()

    def _action_done(self):
        self._b2b_check_collection_release()
        result = super()._action_done()
        for order in self.filtered(lambda p: p.picking_type_id.code == 'outgoing' and p.state == 'done').sale_id.filtered(lambda o: o.b2b_collection_active and o.b2b_shipment_percent < 100):
            # Delivered-quantity invoicing remains native; notify accounting.
            invoices = order.sudo().with_context(raise_if_nothing_to_invoice=False)._create_invoices(final=True)
            invoices.action_post()
            for invoice in invoices:
                invoice.activity_schedule('mail.mail_activity_data_todo', summary=_('Review credit-customer receivable and due date'), user_id=invoice.invoice_user_id.id or self.env.uid)
        return result
