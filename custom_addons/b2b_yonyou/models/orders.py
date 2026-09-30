"""Confirmed-order outbox using the existing job worker and native sale/taxes.

Prepare and send are separate committed worker runs. An HTTP write is never
performed until its immutable payload and idempotency key are in the database.
"""
import hashlib
import json
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from odoo import _, api, fields, models, SUPERUSER_ID
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.b2b_erp_connector.services.erp_service import B2BERPError
from .client import ORDER_CREATE, ORDER_LIST, ORDER_DETAIL, ERPTemporaryError
from .config import WRITE_TOKEN, MANAGER, notification

STAFF = 'b2b_core.group_b2b_operator'
INTEGRATOR = 'b2b_erp_connector.group_b2b_integration_manager'


def money(value, places=2):
    return float(Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    yonyou_key = fields.Char(copy=False, readonly=True, groups=INTEGRATOR)
    yonyou_code = fields.Char(string='ERP Order Number', copy=False, readonly=True, groups=STAFF)
    yonyou_confirmed_at = fields.Datetime(copy=False, readonly=True, groups=STAFF)
    yonyou_id = fields.Char(string='ERP Order ID', copy=False, readonly=True, groups=STAFF)
    yonyou_source = fields.Json(copy=False, readonly=True, groups=INTEGRATOR)
    yonyou_manual_review = fields.Boolean(string='ERP Change / Cancellation Requires Review',
                                         copy=False, readonly=True, groups=STAFF)
    yonyou_sync_status = fields.Selection([
        ('none', 'Not Queued'), ('pending', 'Pending'), ('processing', 'Processing'),
        ('success', 'Created in ERP'), ('failed', 'Retry / Verification Required'),
        ('verifying', 'Submitted / Outcome Pending Verification'),
        ('dead', 'Action Required'), ('changed', 'ERP Change Requires Manual Review')],
        compute='_compute_yonyou_sync_status', string='ERP Submission', groups=STAFF)

    def _compute_yonyou_sync_status(self):
        for order in self:
            if not order._origin.id:
                order.yonyou_sync_status = 'none'
                continue
            job = self.env['b2b.integration.job'].sudo().search([
                ('reference_model', '=', 'sale.order'), ('reference_id', '=', order._origin.id),
                ('yonyou_order', '=', True)], limit=1)
            order.yonyou_sync_status = ('changed' if order.yonyou_manual_review else job.state if job else 'none')
            if (job and job.state in ('pending', 'processing', 'failed')
                    and job.yonyou_verification_only and not order.yonyou_manual_review):
                order.yonyou_sync_status = 'verifying'

    def _yonyou_enabled(self):
        self.ensure_one()
        return (self.env.ref('b2b_yonyou.connection').sudo().order_sync
                and not self.b2b_is_change_revision
                and bool(self.website_id or self.partner_id.commercial_partner_id.b2b_approved))

    @api.model_create_multi
    def create(self, vals_list):
        if any(any(k.startswith('yonyou_') for k in vals) for vals in vals_list):
            raise AccessError(_('ERP submission fields cannot be supplied when creating an order.'))
        return super().create(vals_list)

    def _yonyou_check_checkout(self, refresh=False, force=False):
        for order in self.sudo().filtered(lambda o: o.state in ('draft', 'sent') and (force or o._yonyou_enabled())):
            customer = order.partner_id.commercial_partner_id
            error = _('Your order configuration needs review before payment. Please contact our team. No payment has been taken.')
            if refresh:
                try:
                    customer._erp_verify()
                except UserError:
                    raise ValidationError(error) from None
            snapshot = customer.yonyou_snapshot or {}
            if (customer.yonyou_status != 'verified' or not snapshot.get('currency')
                    or snapshot['currency'] != order.currency_id.name
                    or snapshot.get('currency') not in ('USD', 'CNY')
                    or not snapshot.get('country')):
                raise ValidationError(error)
            rate = 13 if snapshot['country'] == 'CN' else 0
            for line in order.order_line.filtered(lambda l: not l.display_type and l.product_uom_qty):
                tax_ok = ((not line.tax_ids and rate == 0) or (len(line.tax_ids) == 1
                    and line.tax_ids.amount_type == 'percent' and not line.tax_ids.price_include
                    and line.tax_ids.amount == rate and line.tax_ids.company_id == order.company_id))
                if line.product_id.yonyou_status != 'verified' or not tax_ok:
                    raise ValidationError(error)

    def action_quotation_sent(self):
        self._yonyou_check_checkout(refresh=True)
        return super().action_quotation_sent()

    def action_yonyou_check_order(self):
        self.ensure_one()
        if not self.env.user.has_group(MANAGER):
            raise AccessError(_('Only a B2B Manager can check an ERP order.'))
        self.check_access('write')
        self.partner_id.commercial_partner_id._erp_verify()
        self._yonyou_check_checkout(force=True)
        return notification(_('Customer currency and native line taxes are consistent. ERP submission starts only after order confirmation.'))

    def _yonyou_financial_snapshot(self):
        self.ensure_one()
        # No API calls during confirmation, including payment callbacks.
        return {
            'partner': self.partner_id.commercial_partner_id.id, 'company': self.company_id.id,
            'currency': self.currency_id.name, 'rounding': self.currency_id.rounding,
            'total': self.amount_total, 'net': self.amount_untaxed, 'tax': self.amount_tax,
            'lines': [{
                'id': l.id, 'product': l.product_id.id, 'uom': l.product_uom_id.id,
                'qty': l.product_uom_qty, 'price': l.price_unit, 'discount': l.discount,
                'net': l.price_subtotal, 'tax': l.price_tax, 'total': l.price_total,
                'taxes': [{'amount': t.amount, 'type': t.amount_type,
                           'included': t.price_include, 'company': t.company_id.id}
                          for t in l.tax_ids],
                'downpayment': l.is_downpayment,
            } for l in self.order_line.filtered(lambda l: not l.display_type)],
        }

    def action_confirm(self):
        candidates = self.filtered(lambda o: o.state in ('draft', 'sent') and o._yonyou_enabled())
        result = super().action_confirm()
        # The base connector's hook runs inside super; our enqueue below also
        # covers module inheritance order without depending on it.
        for order in candidates.filtered(lambda o: o.state == 'sale'):
            order._b2b_enqueue_erp_sync()
        return result

    def _b2b_enqueue_erp_sync(self):
        self.ensure_one()
        if not self._yonyou_enabled():
            return super()._b2b_enqueue_erp_sync()
        order = self.sudo()
        if order.state != 'sale':
            return self.env['b2b.integration.job']
        # Reconfirmation never creates a second outbox entry.
        if not order.yonyou_key:
            config = self.env.ref('b2b_yonyou.connection').sudo()
            key = uuid.uuid4().hex
            source = order._yonyou_financial_snapshot()
            source.update(org=config.sales_org, rate=config.usd_rate,
                          confirmed_at=fields.Datetime.to_string(order.date_order),
                          connection_revision=config.revision)
            sequence = self.env['ir.sequence'].sudo().next_by_code('b2b.yonyou.order')
            order.with_context(_yonyou_write=WRITE_TOKEN).write({
                'yonyou_key': key, 'yonyou_code': 'PH-T-%s-%s' % (sequence, key[:8]),
                'yonyou_confirmed_at': order.date_order, 'yonyou_source': source})
        # Payment callbacks are sudoed but retain the portal uid. Enqueue is a
        # private, confirmed-order workflow: use the system identity locally,
        # never grant the customer an internal group or public job access.
        job = self.env['b2b.integration.job'].with_user(SUPERUSER_ID).enqueue(
            'sales_order', order, 'yonyou_order:' + order.yonyou_key,
            request_summary={'order': order.name, 'erp_order': order.yonyou_code})
        job.with_context(_yonyou_write=WRITE_TOKEN).write({'yonyou_order': True, 'yonyou_company_id': order.company_id.id})
        self.env.ref('b2b_erp_connector.ir_cron_b2b_process_erp_jobs').sudo()._trigger()
        return job

    def _yonyou_payload(self):
        self.ensure_one()
        source = self.yonyou_source
        if not source or self.state != 'sale' or self.b2b_is_change_revision:
            raise UserError(_('Only a newly confirmed original order can be submitted to ERP.'))
        if any(source[k] != self._yonyou_financial_snapshot()[k]
               for k in ('partner', 'company', 'currency', 'total', 'net', 'tax', 'lines')):
            raise UserError(_('This order changed after confirmation. Review its ERP submission manually.'))
        customer = self.partner_id.commercial_partner_id
        if (customer.yonyou_status != 'verified' or not customer.yonyou_bound_id
                or customer.b2b_selling_company_id != self.company_id):
            raise UserError(_('Verify the customer ERP mapping for this selling company first.'))
        client = self.env['b2b.yonyou.client']
        defaults = client._customer(customer.yonyou_code, source['org'])
        if defaults['id'] != customer.yonyou_bound_id:
            raise UserError(_('ERP customer identity changed. Verify its binding again.'))
        if not defaults.get('department') or not defaults.get('salesperson'):
            raise UserError(_('Configure one default salesperson and department for this customer in the ERP sales organization, then retry.'))
        if not defaults.get('invoice_customer'):
            raise UserError(_('Resolve the default ERP invoice customer before submitting this order.'))
        if defaults.get('currency') not in ('USD', 'CNY') or defaults['currency'] != source['currency']:
            raise UserError(_('ERP customer currency (%(erp)s) must match the confirmed order currency (%(order)s). Do not relabel or convert a paid order.', erp=defaults.get('currency'), order=source['currency']))
        if not defaults.get('country'):
            raise UserError(_('Maintain the ERP customer country before submitting the order.'))
        tax_rate = 13 if defaults['country'] == 'CN' else 0
        rate = source['rate'] if source['currency'] == 'USD' else 1
        date = fields.Datetime.context_timestamp(self.with_context(tz='Asia/Shanghai'),
            fields.Datetime.to_datetime(source['confirmed_at'])).date()
        header = {
            '_status': 'Insert', 'resubmitCheckKey': self.yonyou_key, 'code': self.yonyou_code,
            'salesOrgId': source['org'], 'settlementOrgId': source['org'],
            'transactionTypeId': 'KC', 'vouchdate': '%s 00:00:00' % date,
            'exchRateDate': '%s 00:00:00' % date,
            'agentId': defaults['code'], 'invoiceAgentId': defaults['invoice_customer'],
            'saleDepartmentId': defaults['department'], 'corpContact': defaults['salesperson'],
            'orderPrices!currency': source['currency'], 'orderPrices!natCurrency': 'CNY',
            'orderPrices!exchRate': rate, 'orderPrices!exchangeRateType': '03',
            'orderPrices!taxInclusive': False,
            'orderDefineCharacter!DYCT': '00', 'orderDefineCharacter!GZDY': '00',
            'orderDefineCharacter!SFDT': True,
            'memo': 'Partner Hub %s | Seller %s | Test order; review before fulfilment' % (self.name, self.company_id.id),
            'payMoney': source['total'], 'orderDetails': [],
        }
        products = {}
        for row in source['lines']:
            if row['qty'] == 0 and row['total'] == 0:
                continue
            if row['qty'] <= 0 or row['net'] < 0 or row['downpayment']:
                raise UserError(_('Negative quantities, negative charges and down-payment invoice lines require manual ERP review.'))
            taxes = row['taxes']
            tax_ok = ((not taxes and tax_rate == 0) or (len(taxes) == 1
                and taxes[0]['type'] == 'percent' and not taxes[0]['included']
                and taxes[0]['amount'] == tax_rate and taxes[0]['company'] == source['company']))
            if not tax_ok:
                raise UserError(_('Configure the native customer fiscal position and product taxes: this ERP customer requires tax-exclusive %(rate)s%% sales tax. Zero-tax customers may also use no tax.', rate=tax_rate))
            product = self.env['product.product'].browse(row['product']).exists()
            if not product or product.yonyou_status != 'verified':
                raise UserError(_('Verify the ERP material mapping for every product, including freight.'))
            if product.id not in products:
                products[product.id] = client._product(product.yonyou_code, source['org'])
            material = products[product.id]
            if material['id'] != product.yonyou_snapshot.get('id'):
                raise UserError(_('ERP material identity changed. Verify the product again.'))
            if product.yonyou_snapshot.get('odoo_uom') != product.uom_id.id:
                raise UserError(_('Verify the material again and confirm that one Odoo base unit equals one ERP unit.'))
            qty = self.env['uom.uom'].browse(row['uom'])._compute_quantity(row['qty'], product.uom_id, round=False)
            # Monetary ORM floats can contain e.g. 23.400000000000006. C4
            # checks decimal equality; never serialize these binary artifacts.
            net, tax, total = (money(row[k], self.currency_id.decimal_places) for k in ('net', 'tax', 'total'))
            if money(net + tax, self.currency_id.decimal_places) != total:
                raise UserError(_('The native order line tax breakdown is inconsistent. Review rounding before submitting.'))
            price = money(Decimal(str(net)) / Decimal(str(qty)), 8)
            tax_price = money(Decimal(str(total)) / Decimal(str(qty)), 8)
            nat_net = money(Decimal(str(net)) * Decimal(str(rate)))
            nat_tax = money(Decimal(str(tax)) * Decimal(str(rate)))
            header['orderDetails'].append({
                '_status': 'Insert', 'productId': material['code'], 'skuId': material['sku_id'],
                'masterUnitId': material['unit_code'], 'iProductAuxUnitId': material['unit_code'],
                'iProductUnitId': material['unit_code'],
                'invExchRate': 1, 'invPriceExchRate': 1, 'unitExchangeType': 0, 'unitExchangeTypePrice': 0,
                'qty': qty, 'priceQty': qty, 'subQty': qty,
                'stockOrgId': source['org'], 'settlementOrgId': source['org'],
                'orderProductType': 'SALE', 'orderDetailDefineCharacter!XSLX': '1',
                'consignTime': '%s 00:00:00' % (date + timedelta(days=90)), 'taxId': '%s%%' % tax_rate,
                'oriTaxUnitPrice': tax_price, 'oriSum': total,
                'orderDetailPrices!oriUnitPrice': price, 'orderDetailPrices!oriMoney': net,
                'orderDetailPrices!oriTax': tax,
                'orderDetailPrices!natUnitPrice': money(Decimal(str(price)) * Decimal(str(rate)), 8),
                'orderDetailPrices!natTaxUnitPrice': money(Decimal(str(tax_price)) * Decimal(str(rate)), 8),
                'orderDetailPrices!natMoney': nat_net, 'orderDetailPrices!natTax': nat_tax,
                'orderDetailPrices!natSum': money(nat_net + nat_tax),
            })
        if not header['orderDetails'] or self.currency_id.compare_amounts(
                sum(l['oriSum'] for l in header['orderDetails']), source['total']):
            raise UserError(_('ERP line totals do not match the confirmed order total. Review rounding and charge lines.'))
        return {'data': header}

    def _yonyou_changed(self):
        for order in self.sudo().filtered(lambda o: o.yonyou_source and not o.yonyou_manual_review):
            source = order.yonyou_source
            current = order._yonyou_financial_snapshot()
            if order.state != 'sale' or any(source[k] != current[k] for k in current):
                order.with_context(_yonyou_write=WRITE_TOKEN).write({'yonyou_manual_review': True})
                order.activity_schedule('mail.mail_activity_data_todo',
                    summary=_('Review ERP order change / cancellation'),
                    note=_('The website order changed. ERP was not modified. Review the existing ERP order; do not create another order.'),
                    user_id=order.user_id.id or self.env.ref('base.user_admin').id)

    def write(self, vals):
        if any(k.startswith('yonyou_') for k in vals) and self.env.context.get('_yonyou_write') is not WRITE_TOKEN:
            raise AccessError(_('ERP order snapshots and submission results are system-managed.'))
        result = super().write(vals)
        if {'state', 'partner_id', 'company_id', 'currency_id', 'pricelist_id', 'order_line', 'b2b_change_revision'} & vals.keys():
            self._yonyou_changed()
        return result


class SaleLine(models.Model):
    _inherit = 'sale.order.line'

    def write(self, vals):
        result = super().write(vals)
        if {'product_id', 'product_uom_qty', 'product_uom_id', 'price_unit', 'discount', 'tax_ids'} & vals.keys():
            self.order_id._yonyou_changed()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.order_id._yonyou_changed()
        return lines

    def unlink(self):
        orders = self.order_id
        result = super().unlink()
        orders._yonyou_changed()
        return result


class IntegrationJob(models.Model):
    _inherit = 'b2b.integration.job'

    yonyou_order = fields.Boolean(copy=False, readonly=True, index=True)
    yonyou_company_id = fields.Many2one('res.company', copy=False, readonly=True, index=True)
    yonyou_payload = fields.Json(copy=False, readonly=True, groups=INTEGRATOR)
    yonyou_verification_only = fields.Boolean(compute='_compute_yonyou_verification_only',
        string='Verification Only — Do Not Recreate')

    def _compute_yonyou_verification_only(self):
        ledger = self.env['b2b.yonyou.order.dispatch']
        for job in self:
            order = job._reference() if job.yonyou_order else False
            job.yonyou_verification_only = bool(order and order.yonyou_key
                and ledger._lookup(order.yonyou_key)[0])

    def init(self):
        # Upgrade existing outbox entries before the company record rule applies.
        self.env.cr.execute("""
            UPDATE b2b_integration_job j SET yonyou_company_id = s.company_id
              FROM sale_order s
             WHERE j.yonyou_order AND j.yonyou_company_id IS NULL
               AND j.reference_model = 'sale.order' AND j.reference_id = s.id
        """)

    @api.model_create_multi
    def create(self, vals_list):
        if any({'yonyou_order', 'yonyou_payload', 'yonyou_company_id'} & vals.keys() for vals in vals_list):
            raise AccessError(_('ERP payloads cannot be supplied manually.'))
        return super().create(vals_list)

    def write(self, vals):
        if {'yonyou_order', 'yonyou_payload', 'yonyou_company_id'} & vals.keys() and self.env.context.get('_yonyou_write') is not WRITE_TOKEN:
            raise AccessError(_('ERP payloads are system-managed.'))
        return super().write(vals)

    def _process_locked(self):
        self.ensure_one()
        if not self.yonyou_order:
            return super()._process_locked()
        config = self.env.ref('b2b_yonyou.connection').sudo()
        if not config.order_sync:
            return False
        if self.state not in ('pending', 'failed'):
            return False
        order = self._reference()
        if not order or not order.try_lock_for_update():
            return False
        if not self.yonyou_payload:
            self._system_write({'attempt_count': self.attempt_count + 1, 'last_error': False})
            try:
                payload = order._yonyou_payload()
                self.with_context(_yonyou_write=WRITE_TOKEN).write({'yonyou_payload': payload})
                self._system_write({'state': 'pending', 'next_retry_at': fields.Datetime.now(),
                    'safe_request_summary': {'order': order.name, 'erp_order': order.yonyou_code,
                                             'payload_sha256': digest(payload), 'phase': 'prepared'}})
                self.env.ref('b2b_erp_connector.ir_cron_b2b_process_erp_jobs').sudo()._trigger()
            except UserError as exc:
                self._mark_failure(_('Preparing ERP order: %s', str(exc)),
                    retryable=isinstance(exc, ERPTemporaryError))
            return False  # Commit the frozen payload before any remote write.
        return super()._process_locked()


class ERPService(models.AbstractModel):
    _inherit = 'b2b.erp.service'

    @api.model
    def is_enabled(self):
        return super().is_enabled() or self.env.ref('b2b_yonyou.connection').sudo().order_sync

    @api.model
    def dispatch_job(self, job, reference):
        if not job.yonyou_order:
            return super().dispatch_job(job, reference)
        try:
            return self._yonyou_dispatch_order(job, reference)
        except UserError as exc:
            raise B2BERPError('erp_request_failed', _('Submitting/verifying ERP order: %s', str(exc)),
                retryable=isinstance(exc, ERPTemporaryError)) from None

    @api.model
    def _yonyou_dispatch_order(self, job, reference):
        config = self.env.ref('b2b_yonyou.connection').sudo()
        if not config.order_sync:
            raise B2BERPError('disabled', _('ERP submission is disabled.'), retryable=False)
        if reference.yonyou_source.get('connection_revision') != config.revision:
            raise B2BERPError('connection_changed', _('ERP connection identity changed. Review the queued order before retrying.'), retryable=False)
        if reference.state != 'sale' or reference.yonyou_manual_review:
            raise B2BERPError('order_changed', _('Order changed or was cancelled. Review ERP manually; no new order was sent.'), retryable=False)
        client = self.env['b2b.yonyou.client']
        payload = job.yonyou_payload
        if not payload:
            raise B2BERPError('not_prepared', _('Prepare the ERP payload before sending.'), retryable=False)
        header = payload['data']
        ledger = self.env['b2b.yonyou.order.dispatch']
        attempted, remembered_id = ledger._lookup(reference.yonyou_key)
        # Lookup before *every* send, including retries after a lost response.
        erp_id = remembered_id or client._order_by_code(header['code'])
        if not erp_id:
            if attempted or not ledger._claim(reference.yonyou_key):
                raise B2BERPError('verification_pending', _('A submission was already attempted. ERP has not returned the order yet. Verification will retry; no second creation is allowed. If this persists, check ERP manually.'))
            result = client._call(ORDER_CREATE, payload)
            # Only accept an explicit document ID, never an arbitrary scalar.
            if isinstance(result, dict) and str(result.get('id', '')).isdigit():
                erp_id = str(result['id'])
                ledger._remember(reference.yonyou_key, erp_id)
        if not erp_id:
            erp_id = client._order_by_code(header['code'])
        if not erp_id:
            raise B2BERPError('result_unknown', _('ERP creation result is not yet verified. The same order number and key will be checked on retry.'))
        # Once existence is known, even a later detail timeout or mismatch
        # must never reopen permission to create a second document.
        ledger._claim(reference.yonyou_key)
        detail = client._call(ORDER_DETAIL, {'id': erp_id})
        self._yonyou_validate_readback(header, detail, reference.currency_id)
        # Existing orders found before any send must also stay query-only.
        ledger._remember(reference.yonyou_key, erp_id)
        reference.with_context(_yonyou_write=WRITE_TOKEN).write({'yonyou_id': erp_id})
        return {'success': True, 'reference': header['code']}

    @api.model
    def _yonyou_validate_readback(self, expected, actual, currency):
        def mismatch():
            raise B2BERPError('readback_mismatch', self.env._('An ERP order exists but its customer, organization, salesperson, department, lines or amounts differ. Do not resubmit; review the existing ERP order.'), retryable=False)
        if not isinstance(actual, dict):
            mismatch()
        prices = actual.get('orderPrices') or {}
        if (actual.get('code') != expected['code']
                or actual.get('salesOrgId_code') != expected['salesOrgId']
                or actual.get('agentId_code') != expected['agentId']
                or actual.get('corpContact_code') != expected['corpContact']
                or actual.get('saleDepartmentId_code') != expected['saleDepartmentId']
                or prices.get('originalCode') != expected['orderPrices!currency']
                or currency.compare_amounts(actual.get('payMoney', -1), expected['payMoney'])):
            mismatch()
        lines = actual.get('orderDetails') or []
        if len(lines) != len(expected['orderDetails']):
            mismatch()
        def signature(line, remote):
            p = line.get('orderDetailPrices') or {} if remote else {}
            return (str(line.get('productCode' if remote else 'productId')),
                    round(float(line.get('qty', -1)), 8),
                    money(line.get('oriSum', -1)),
                    money(p.get('oriMoney', -1) if remote else line['orderDetailPrices!oriMoney']),
                    money(p.get('oriTax', -1) if remote else line['orderDetailPrices!oriTax']))
        if sorted(signature(l, True) for l in lines) != sorted(signature(l, False) for l in expected['orderDetails']):
            mismatch()


class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    @api.model_create_multi
    def create(self, vals_list):
        transactions = super().create(vals_list)
        transactions.filtered(lambda t: t.operation not in ('refund', 'validation')
                              and t.state not in ('done', 'authorized')).sale_order_ids._yonyou_check_checkout(refresh=True)
        return transactions
