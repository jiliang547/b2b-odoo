"""Demand-driven, query-only fulfilment snapshots. Never dispatch a sale job."""
from collections import defaultdict
from datetime import datetime, timedelta
from hashlib import sha256
import json
import math

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from .client import ORDER_DETAIL, REPORT_QUERY, ERPTemporaryError
from .config import WRITE_TOKEN

STAFF = 'b2b_core.group_b2b_operator'
CACHE_MINUTES = 30
FAILURE_MINUTES = 5
MANUAL_SECONDS = 60
REPORT_FIELDS = [
    '源头单据主表id', '源头单据子表id', '源头单据号', '销售订单行号',
    '客户编码', '物料编码', '单据id', '编码', '供应行号',
    '供应订单下单日期', '最终约定完工日期', '入库日期', '销售出库日期',
    '销售出库数量', '下单数量', '销售未发数量',
]
DATE_FIELDS = {
    'supply_date': '供应订单下单日期', 'expected_date': '最终约定完工日期',
    'receipt_date': '入库日期', 'dispatch_date': '销售出库日期',
}


def identifier(value):
    # The API uses 19-digit integers: never round them through a JS/ORM float.
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('Invalid ERP identifier')
    result = str(value)
    if not result.isdigit():
        raise ValueError('Invalid ERP identifier')
    return result


def quantity(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('Missing ERP quantity')
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('Invalid ERP quantity') from None
    if not math.isfinite(result) or result < 0:
        raise ValueError('Invalid ERP quantity')
    return result


def date_value(value):
    if value in (None, ''):
        return False
    if not isinstance(value, str):
        raise ValueError('Invalid ERP date')
    try:
        datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('Invalid ERP date') from None
    return value[:10]


def decode_report(result):
    """Reject incomplete pages; an empty successful report is not an error."""
    if not isinstance(result, dict) or result.get('status') != 1:
        raise ValueError('Report query was unsuccessful')
    data = result.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('result'), list):
        raise ValueError('Invalid report result')
    meta = data.get('meta')
    if not isinstance(meta, list) or any(not isinstance(m, dict) for m in meta):
        raise ValueError('Invalid report metadata')
    names = [m.get('code') for m in meta]
    if len(names) != len(set(names)) or set(names) != set(REPORT_FIELDS):
        raise ValueError('Report fields changed')
    pager = data.get('pager')
    if (not isinstance(pager, dict) or not isinstance(pager.get('recordCount'), int)
            or pager['recordCount'] != len(data['result']) or pager.get('pageCount', 0) > 1):
        raise ValueError('Report exceeds one safe page')
    rows = []
    for values in data['result']:
        if not isinstance(values, list) or len(values) != len(names):
            raise ValueError('Invalid report row')
        rows.append(dict(zip(names, values)))
    return rows


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    yonyou_progress_bindings = fields.Json(copy=False, readonly=True, groups=STAFF)
    yonyou_progress_snapshot = fields.Json(copy=False, readonly=True, groups=STAFF)
    yonyou_progress_state = fields.Selection([
        ('none', 'Not Requested'), ('queued', 'Update Requested'), ('ready', 'Updated'),
        ('delayed', 'Update Delayed'), ('blocked', 'Configuration Review Required'),
    ], string='Order Progress Update', default='none', copy=False, readonly=True, index=True, groups=STAFF)
    yonyou_progress_requested_at = fields.Datetime(copy=False, readonly=True, groups=STAFF)
    yonyou_progress_attempt_at = fields.Datetime(string='Last Progress Attempt', copy=False, readonly=True, groups=STAFF)
    yonyou_progress_updated_at = fields.Datetime(string='Last Successful Progress Update', copy=False, readonly=True, groups=STAFF)
    yonyou_progress_next_at = fields.Datetime(copy=False, readonly=True, groups=STAFF)
    yonyou_progress_error = fields.Text(string='Progress Update Error', copy=False, readonly=True, groups=STAFF)
    yonyou_progress_notes = fields.Text(string='Progress Data Notes', copy=False, readonly=True, groups=STAFF)

    def _progress_write(self, values):
        return self.sudo().with_context(_yonyou_write=WRITE_TOKEN).write(values)

    def _yonyou_store_progress_bindings(self, detail):
        """Bind unique verified native lines; identical duplicate lines fail closed.

        Old readback fixtures/API variants may lack IDs. This must not change
        the established order submission outcome; tracking reports the gap.
        """
        self.ensure_one()
        job = self.env['b2b.integration.job'].sudo().search([
            ('reference_model', '=', 'sale.order'), ('reference_id', '=', self.id),
            ('yonyou_order', '=', True)], limit=1)
        payload = (job.yonyou_payload or {}).get('data', {})
        expected = payload.get('orderDetails', [])
        sources = [r for r in (self.yonyou_source or {}).get('lines', []) if r['qty'] > 0]
        remote = detail.get('orderDetails', []) if isinstance(detail, dict) else []
        if len(expected) != len(sources) or len(remote) != len(expected):
            return
        matches = defaultdict(list)
        try:
            for row in remote:
                key = (row.get('productCode'), round(float(row['qty']), 8), round(float(row['oriSum']), 2))
                matches[key].append(identifier(row['id']))
        except (KeyError, ValueError, TypeError):
            return
        bindings = {}
        seen = set()
        for source, row in zip(sources, expected):
            key = (row.get('productId'), round(float(row['qty']), 8), round(float(row['oriSum']), 2))
            candidates = matches.get(key, [])
            if len(candidates) == 1 and candidates[0] not in seen:
                bindings[str(source['id'])] = {'id': candidates[0], 'code': row['productId']}
                seen.add(candidates[0])
        if bindings:
            self._progress_write({'yonyou_progress_bindings': bindings})

    def _yonyou_manual_refresh_info(self):
        """Read-only availability, shared by all contacts and staff on an order."""
        self.ensure_one()
        config = self.env.ref('b2b_yonyou.connection').sudo()
        supported = bool(self.yonyou_id and config.enabled and not self.yonyou_manual_review
            and self.state != 'cancel'
            and (self.yonyou_source or {}).get('connection_revision') in (None, config.revision)
            and (self.yonyou_progress_snapshot or {}).get('connection_revision') in (None, config.revision))
        if not supported or self.yonyou_progress_state == 'queued':
            return {'supported': supported, 'retry_after': 0}
        now = fields.Datetime.now()
        deadlines = [value + timedelta(seconds=MANUAL_SECONDS) for value in
                     (self.yonyou_progress_requested_at, self.yonyou_progress_attempt_at) if value]
        # A manual request bypasses only a successful cache, not an outage or
        # configuration/data-error backoff. Never reset these timers on a click.
        if self.yonyou_progress_state in ('delayed', 'blocked') and self.yonyou_progress_next_at:
            deadlines.append(self.yonyou_progress_next_at)
        seconds = max([0] + [(deadline - now).total_seconds() for deadline in deadlines])
        return {'supported': True, 'retry_after': math.ceil(seconds)}

    def _yonyou_request_progress(self, manual=False):
        self.ensure_one()
        config = self.env.ref('b2b_yonyou.connection').sudo()
        if not self.yonyou_id or not config.enabled or self.yonyou_manual_review or self.state == 'cancel':
            return False
        # SKIP LOCKED keeps both another visitor and an active ERP query from
        # blocking the website. Re-read the cache after acquiring the lock.
        locked = self.sudo().try_lock_for_update()
        if not locked:
            return False
        locked.invalidate_recordset()
        now = fields.Datetime.now()
        if locked.yonyou_progress_state == 'queued':
            return False
        info = locked._yonyou_manual_refresh_info()
        if manual and (not info['supported'] or info['retry_after']):
            return False
        if not manual and locked.yonyou_progress_next_at and locked.yonyou_progress_next_at > now:
            return False
        if (locked.yonyou_progress_snapshot or {}).get('connection_revision') not in (None, config.revision):
            locked._progress_write({'yonyou_progress_state': 'blocked',
                'yonyou_progress_error': 'ERP connection changed; review this order before querying.',
                'yonyou_progress_next_at': now + timedelta(minutes=CACHE_MINUTES)})
            return False
        locked._progress_write({'yonyou_progress_state': 'queued', 'yonyou_progress_requested_at': now})
        self.env.ref('b2b_yonyou.ir_cron_order_progress').sudo()._trigger()
        return True

    def action_yonyou_refresh_progress(self):
        self.ensure_one()
        if not self.env.user.has_group('b2b_erp_connector.group_b2b_integration_manager'):
            raise AccessError(_('Only integration managers can request an order progress update.'))
        self.check_access('write')
        order = self.sudo()
        requested = order._yonyou_request_progress(manual=True)
        info = order._yonyou_manual_refresh_info()
        if requested:
            message = _('An order progress update has been requested.')
        elif order.yonyou_progress_state == 'queued':
            message = _('An update is already being processed. No duplicate request was created.')
        elif not info['supported']:
            message = _('Order progress cannot be refreshed until the ERP order link or configuration is reviewed.')
        elif info['retry_after']:
            message = _('Please wait %(seconds)s seconds before requesting another update.', seconds=info['retry_after'])
        else:
            message = _('Another update is being started. Please try again shortly.')
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
            'title': _('Order Progress'), 'message': message,
            'type': 'info', 'sticky': False,
        }}

    def _yonyou_refresh_progress(self):
        self.ensure_one()
        now = fields.Datetime.now()
        self._progress_write({'yonyou_progress_attempt_at': now})
        try:
            config = self.env.ref('b2b_yonyou.connection').sudo()
            if not config.enabled or self.yonyou_manual_review or self.state == 'cancel' or not self.yonyou_id:
                raise UserError(_('Order progress requires review of the ERP order link.'))
            if (self.yonyou_source or {}).get('connection_revision') not in (None, config.revision):
                raise UserError(_('ERP connection identity changed. Review the original order.'))
            client = self.env['b2b.yonyou.client']
            if not self.yonyou_progress_bindings:
                detail = client._call(ORDER_DETAIL, {'id': self.yonyou_id})
                if identifier(detail['id']) != self.yonyou_id or detail.get('code') != self.yonyou_code:
                    raise ValueError('ERP order identity changed')
                self._yonyou_store_progress_bindings(detail)
            result = client._call(REPORT_QUERY, {
                'entity': 'xinquanliucbiao', 'pager': {'pageIndex': 1, 'pageSize': 500},
                'fields': [{'name': n, 'aggr': ''} for n in REPORT_FIELDS],
                'conditions': [{'op': 'AND', 'items': [
                    {'op': 'eq', 'name': '源头单据号', 'v1': self.yonyou_code, 'v2': '', 'values': []},
                ]}],
            })
            rows = decode_report(result)
            snapshot = self._yonyou_normalize_progress(rows)
            snapshot['connection_revision'] = config.revision
            # No partial replacement or wiping a successful snapshot on errors.
            # A missing previously seen report line is not proof of zero shipment.
            previous = self.yonyou_progress_snapshot or {}
            old_ids = {r['erp_line_id'] for r in previous.get('rows', [])}
            new_ids = {r['erp_line_id'] for r in snapshot['rows']}
            if old_ids - new_ids:
                raise ValueError('Previously reported lines disappeared; review required')
            notes = []
            for row in snapshot['rows']:
                if row['quantity_issue'] == 'missing':
                    notes.append('ERP line %s / material %s: shipment quantities have not been provided.' % (row['erp_line_id'], row['code']))
                elif row['quantity_issue'] == 'ambiguous':
                    notes.append('ERP line %s / material %s: multiple report rows; confirm the cumulative shipment quantity contract.' % (row['erp_line_id'], row['code']))
            completed = fields.Datetime.now()
            self._progress_write({'yonyou_progress_snapshot': snapshot,
                'yonyou_progress_state': 'ready', 'yonyou_progress_updated_at': completed,
                'yonyou_progress_next_at': completed + timedelta(minutes=CACHE_MINUTES),
                'yonyou_progress_notes': '\n'.join(notes) or False,
                'yonyou_progress_error': False})
        except Exception as exc:
            temporary = isinstance(exc, ERPTemporaryError)
            error = str(exc)[:1000] if isinstance(exc, (UserError, ValueError)) else \
                'Progress data could not be validated. Review ERP fields, quantities and line mappings.'
            if temporary:
                error = error.replace('Retry will check the existing record first.',
                    'Only the progress report will be queried again; no sales order is resubmitted.')
            self._progress_write({'yonyou_progress_state': 'delayed' if temporary else 'blocked',
                'yonyou_progress_next_at': fields.Datetime.now() + timedelta(minutes=FAILURE_MINUTES if temporary else CACHE_MINUTES),
                'yonyou_progress_error': error})

    def _yonyou_normalize_progress(self, rows):
        self.ensure_one()
        grouped = defaultdict(list)
        for row in rows:
            if identifier(row['源头单据主表id']) != self.yonyou_id or row['源头单据号'] != self.yonyou_code:
                raise ValueError('Unexpected ERP order')
            line_id = identifier(row['源头单据子表id'])
            grouped[line_id].append(row)
        output = []
        for line_id, group in grouped.items():
            codes = {r['物料编码'] for r in group}
            if len(codes) != 1:
                raise ValueError('Inconsistent material on an ERP order line')
            dates = {key: sorted({date_value(r[field]) for r in group if r[field]})
                     for key, field in DATE_FIELDS.items()}
            # Pending supply records may have no shipment quantities yet. Keep
            # their dates without turning an unknown quantity into a false zero.
            metrics = {(quantity(r['下单数量']), quantity(r['销售出库数量']), quantity(r['销售未发数量']))
                       for r in group if all(r[k] not in (None, '')
                           for k in ('下单数量', '销售出库数量', '销售未发数量'))}
            for ordered, shipped, remaining in metrics:
                if shipped > ordered + 0.000001 or abs(ordered - shipped - remaining) > 0.000001:
                    raise ValueError('Inconsistent shipment quantities')
            # One source line may join several supply lines. Until the report's
            # aggregation contract is verified, never sum/max these quantities.
            quantity_verified = len(group) == 1 and len(metrics) == 1
            issue = False if quantity_verified else 'ambiguous' if len(group) > 1 else 'missing'
            ordered, shipped, remaining = next(iter(metrics), (None, None, None))
            supplies = []
            for row in group:
                supply = {key: date_value(row[field]) for key, field in DATE_FIELDS.items()}
                if supply not in supplies:
                    supplies.append(supply)
            output.append({'erp_line_id': line_id, 'code': next(iter(codes)),
                'dates': dates, 'supplies': supplies, 'quantity_verified': quantity_verified, 'quantity_issue': issue,
                'ordered': ordered if quantity_verified else None,
                'shipped': shipped if quantity_verified else None,
                'remaining': remaining if quantity_verified else None})
        return {'rows': output}

    @api.model
    def _cron_yonyou_progress(self, limit=2):
        # Only visitors' requests; no periodic scanning of all confirmed orders.
        domain = [('yonyou_progress_state', '=', 'queued')]
        candidates = self.sudo().search(domain, order='yonyou_progress_requested_at, id', limit=limit)
        cron = self.env['ir.cron']
        cron._commit_progress(remaining=self.sudo().search_count(domain))
        for candidate in candidates:
            locked = candidate.try_lock_for_update().filtered_domain(domain)
            if not locked:
                continue
            locked._yonyou_refresh_progress()
            if not cron._commit_progress(1):
                break

    def _yonyou_public_progress(self):
        """Whitelisted presentation only; never expose ERP ids/payload/error."""
        self.ensure_one()
        snapshot = self.yonyou_progress_snapshot or {}
        bindings = self.yonyou_progress_bindings or {}
        rows = {r['erp_line_id']: r for r in snapshot.get('rows', [])}
        items = []
        changed = bool(self.yonyou_manual_review)
        for line in self.order_line.filtered(lambda l: not l.display_type and not l.is_downpayment and l.product_uom_qty > 0):
            binding = bindings.get(str(line.id), {})
            row = rows.get(binding.get('id')) if not changed else None
            if row and row['code'] != binding.get('code'):
                row = None
            no_shipment = bool(line.is_delivery or line.product_id.type == 'service')
            state = 'waiting'
            if no_shipment:
                state = 'service'
            elif row:
                state = (('unverified' if row.get('quantity_issue') == 'ambiguous' else 'waiting') if not row['quantity_verified'] else
                         'shipped' if row['remaining'] == 0 else
                         'partial' if row['shipped'] else 'not_shipped')
            items.append({'name': line.name, 'sku': line.product_id.default_code or '',
                'ordered': line.product_uom_qty, 'unit': line.product_uom_id.name,
                'shipped': row['shipped'] if row and row['quantity_verified'] and not no_shipment else None,
                'remaining': row['remaining'] if row and row['quantity_verified'] and not no_shipment else None,
                'quantity_unit': line.product_id.uom_id.name,
                'state': state, 'dates': row['dates'] if row and not no_shipment else {},
                'supplies': row['supplies'] if row and not no_shipment else []})
        return {'items': items, 'pending': self.yonyou_progress_state == 'queued' and not changed,
            'refresh': self._yonyou_manual_refresh_info(),
            'content_key': sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'updated_at': fields.Datetime.to_string(self.yonyou_progress_updated_at) if self.yonyou_progress_updated_at else False,
            'delayed': self.yonyou_progress_state in ('delayed', 'blocked'),
            'changed': changed, 'linked': bool(self.yonyou_id),
            'enabled': self.env.ref('b2b_yonyou.connection').sudo().enabled,
            'cancelled': self.state == 'cancel'}


class ERPService(models.AbstractModel):
    _inherit = 'b2b.erp.service'

    @api.model
    def get_order_status(self, order, customer_context):
        if order.partner_id.commercial_partner_id.id != customer_context.get('commercial_partner_id'):
            raise AccessError(_('You cannot view this order.'))
        order = order.sudo()
        order._yonyou_request_progress()
        return order._yonyou_public_progress()
