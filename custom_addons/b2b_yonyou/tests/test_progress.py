from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from odoo import Command, fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.addons.website_sale.tests.common import MockRequest
from werkzeug.exceptions import NotFound
from ..controllers.progress import OrderProgress
from ..models.config import WRITE_TOKEN
from ..models.client import REPORT_QUERY, ORDER_CREATE, ERPTemporaryError
from ..models.progress import REPORT_FIELDS, decode_report, identifier


@tagged('post_install', '-at_install')
class TestYonyouProgress(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env.ref('b2b_yonyou.connection')
        cls.config.write({'enabled': True, 'order_sync': False})
        cls.product = cls.env['product.product'].create({'name': 'Progress Speaker', 'type': 'consu'})
        cls.customer = cls.env['res.partner'].create({'name': 'Progress Company', 'is_company': True})
        cls.portal = mail_new_test_user(cls.env, login='progress-customer', password='Portal-Test-2026!', groups='base.group_portal')
        cls.portal.partner_id.parent_id = cls.customer
        cls.order = cls.env['sale.order'].create({'partner_id': cls.customer.id,
            'order_line': [Command.create({'product_id': cls.product.id, 'product_uom_qty': 100, 'price_unit': 2})]})
        cls.order.with_context(_yonyou_write=WRITE_TOKEN).write({
            'yonyou_id': '2609180994360574002', 'yonyou_code': 'PROGRESS-TEST',
            'yonyou_progress_bindings': {str(cls.order.order_line.id): {'id': '2609180994360574003', 'code': 'M001'}},
            'yonyou_source': {'connection_revision': cls.config.revision}})

    def _rows(self):
        return [{'源头单据主表id': 2609180994360574002, '源头单据子表id': 2609180994360574003,
            '源头单据号': 'PROGRESS-TEST', '销售订单行号': 10, '客户编码': 'C001', '物料编码': 'M001',
            '单据id': 2609984084511817735, '编码': 'SUPPLY001', '供应行号': 10,
            '供应订单下单日期': '2026-08-18', '最终约定完工日期': '2026-09-15 00:00:00.000',
            '入库日期': '2026-09-23', '销售出库日期': '2026-09-24',
            '下单数量': 100, '销售出库数量': 52, '销售未发数量': 48}]

    def _report(self, rows=None, names=None):
        rows = self._rows() if rows is None else rows
        names = names or REPORT_FIELDS
        return {'status': 1, 'data': {'meta': [{'code': n} for n in names],
            'result': [[r[n] for n in names] for r in rows],
            'pager': {'recordCount': len(rows), 'pageCount': 1}}}

    def _refresh(self, report=None):
        def read(path, body):
            self.assertEqual(path, REPORT_QUERY)
            self.assertEqual(body['entity'], 'xinquanliucbiao')
            self.assertEqual(body['conditions'][0]['items'][0]['v1'], self.order.yonyou_code)
            return report or self._report()
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=read):
            self.order._yonyou_refresh_progress()

    def test_report_metadata_not_position(self):
        rows = decode_report(self._report(names=list(reversed(REPORT_FIELDS))))
        self.assertEqual(identifier(rows[0]['源头单据子表id']), '2609180994360574003')
        with self.assertRaises(ValueError):
            identifier(float(2609180994360574003))

    def test_partial_shipment_and_dates(self):
        self._refresh()
        public = self.order._yonyou_public_progress()
        self.assertEqual(self.order.yonyou_progress_state, 'ready')
        item = public['items'][0]
        self.assertEqual((item['shipped'], item['remaining'], item['state']), (52, 48, 'partial'))
        self.assertEqual(item['dates']['expected_date'], ['2026-09-15'])
        self.assertNotIn('erp_line_id', str(public))
        self.assertNotIn('2609180994360574003', str(public))

    def test_page_only_queues_never_calls_erp(self):
        with patch.object(type(self.env['b2b.yonyou.client']), '_http', side_effect=AssertionError('No ERP in HTML request')):
            status = self.env['b2b.erp.service'].get_order_status(self.order,
                {'commercial_partner_id': self.customer.id})
            self.assertTrue(status['pending'])
        self.assertFalse(self.order._yonyou_request_progress())

    def test_unauthorized_service_context(self):
        with self.assertRaises(AccessError):
            self.env['b2b.erp.service'].get_order_status(self.order, {'commercial_partner_id': 0})

    def test_recent_cache_no_query(self):
        self._refresh()
        self.assertFalse(self.order._yonyou_request_progress())
        self.order._progress_write({'yonyou_progress_next_at': fields.Datetime.now() - timedelta(seconds=1)})
        self.assertTrue(self.order._yonyou_request_progress())

    def test_timeout_keeps_good_snapshot_and_cooldown(self):
        self._refresh()
        old = deepcopy(self.order.yonyou_progress_snapshot)
        old_date = self.order.yonyou_progress_updated_at
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=ERPTemporaryError('timeout')):
            self.order._yonyou_refresh_progress()
        self.assertEqual(self.order.yonyou_progress_snapshot, old)
        self.assertEqual(self.order.yonyou_progress_updated_at, old_date)
        self.assertEqual(self.order.yonyou_progress_state, 'delayed')
        self.assertFalse(self.order._yonyou_request_progress())

    def test_inconsistent_quantities_do_not_replace_snapshot(self):
        self._refresh()
        previous = deepcopy(self.order.yonyou_progress_snapshot)
        rows = self._rows()
        rows[0]['销售出库数量'] = 200
        self._refresh(self._report(rows))
        self.assertEqual(self.order.yonyou_progress_snapshot, previous)
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')

    def test_multiple_supplies_no_sum_or_max(self):
        rows = self._rows()
        other = deepcopy(rows[0])
        other.update({'编码': 'SUPPLY002', '最终约定完工日期': '2026-09-20'})
        rows.append(other)
        self._refresh(self._report(rows))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertIsNone(item['shipped'])
        self.assertEqual(item['state'], 'unverified')
        self.assertEqual(len(item['supplies']), 2)
        self.assertIn('multiple report rows', self.order.yonyou_progress_notes)

    def test_missing_shipment_quantity_keeps_dates_without_inventing_zero(self):
        rows = self._rows()
        rows[0]['销售出库数量'] = None
        rows[0]['销售未发数量'] = None
        self._refresh(self._report(rows))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertEqual(self.order.yonyou_progress_state, 'ready')
        self.assertEqual(item['state'], 'waiting')
        self.assertIsNone(item['shipped'])
        self.assertEqual(item['dates']['supply_date'], ['2026-08-18'])
        self.assertIn('have not been provided', self.order.yonyou_progress_notes)
        html = self.env['ir.ui.view']._render_template('b2b_yonyou.progress_panel',
            {'order': self.order, 'status': self.order._yonyou_public_progress()})
        self.assertIn('Awaiting shipment updates', html)
        self.assertNotIn('requires verification', html)
        self.assertNotIn(self.order.yonyou_progress_notes, str(self.order._yonyou_public_progress()))

    def test_unique_unshipped_row_derives_zero_from_valid_remaining_quantity(self):
        rows = self._rows()
        rows[0].update({'销售出库数量': None, '销售未发数量': 100, '销售出库日期': None})
        self._refresh(self._report(rows))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertEqual((item['shipped'], item['remaining'], item['state']), (0, 100, 'not_shipped'))

    def test_partial_field_remains_visible_without_assuming_missing_shipped_quantity(self):
        rows = self._rows()
        rows[0]['销售出库数量'] = None
        self._refresh(self._report(rows))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertIsNone(item['shipped'])
        self.assertEqual(item['remaining'], 48)
        self.assertEqual(item['state'], 'waiting')

    def test_zero_shipment_with_erp_dispatch_date_keeps_the_raw_date(self):
        rows = self._rows()
        rows[0].update({'销售出库数量': 0, '销售未发数量': 100})
        self._refresh(self._report(rows))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertEqual(item['state'], 'not_shipped')
        self.assertEqual(item['dates']['dispatch_date'], ['2026-09-24'])

    def test_invalid_provided_remaining_is_not_hidden_by_missing_shipped(self):
        rows = self._rows()
        rows[0].update({'销售出库数量': None, '销售未发数量': 101})
        self._refresh(self._report(rows))
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')

    def test_temporary_read_failure_has_two_bounded_native_cron_retries(self):
        self._refresh()
        old = deepcopy(self.order.yonyou_progress_snapshot)
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=ERPTemporaryError('HTTP 504')):
            for attempt, minutes in ((1, 5), (2, 15), (3, 5)):
                before = fields.Datetime.now()
                self.order._yonyou_refresh_progress()
                self.assertEqual(self.order.yonyou_progress_attempts, attempt)
                self.assertAlmostEqual((self.order.yonyou_progress_next_at - before).total_seconds(), minutes * 60, delta=5)
                self.assertEqual(self.order.yonyou_progress_snapshot, old)
                self.assertEqual(self.order._yonyou_public_progress()['retry_scheduled'], attempt < 3)
        self.order._progress_write({'yonyou_progress_next_at': fields.Datetime.now() - timedelta(seconds=1)})
        self.assertFalse(self.order._yonyou_request_progress())
        self._old_attempt()
        self.assertTrue(self.order._yonyou_request_progress(manual=True))
        self.assertEqual(self.order.yonyou_progress_attempts, 0)

    def test_cron_only_retries_due_requested_read_cycles(self):
        self.order._progress_write({'yonyou_progress_state': 'delayed', 'yonyou_progress_attempts': 1,
            'yonyou_progress_next_at': fields.Datetime.now() - timedelta(seconds=1)})
        touched = []
        def refresh(record):
            touched.append(record.id)
            record._progress_write({'yonyou_progress_state': 'ready'})
        with patch.object(type(self.order), '_yonyou_refresh_progress', refresh), \
                patch.object(type(self.env['ir.cron']), '_commit_progress', return_value=10):
            self.order._cron_yonyou_progress()
            self.assertEqual(touched, [self.order.id])
            for attempts, next_at in ((0, fields.Datetime.now()), (3, fields.Datetime.now()),
                    (1, fields.Datetime.now() + timedelta(minutes=1))):
                self.order._progress_write({'yonyou_progress_state': 'delayed',
                    'yonyou_progress_attempts': attempts, 'yonyou_progress_next_at': next_at})
                self.order._cron_yonyou_progress()
            self.assertEqual(touched, [self.order.id])

    def test_retry_stops_when_cancelled_and_never_creates_an_order(self):
        self.order._progress_write({'yonyou_progress_state': 'delayed', 'yonyou_progress_attempts': 1,
            'state': 'cancel', 'yonyou_progress_next_at': fields.Datetime.now() - timedelta(seconds=1)})
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=AssertionError('No ERP call')):
            self.order._yonyou_refresh_progress()
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')
        self.assertFalse(self.order._yonyou_public_progress()['retry_scheduled'])

    def test_wrong_erp_order_id_rejected_even_when_number_matches(self):
        rows = self._rows()
        rows[0]['源头单据主表id'] = 2609180994360574999
        self._refresh(self._report(rows))
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')
        self.assertFalse(self.order.yonyou_progress_snapshot)

    def test_empty_first_query_is_waiting_not_zero(self):
        self._refresh(self._report([]))
        item = self.order._yonyou_public_progress()['items'][0]
        self.assertIsNone(item['shipped'])
        self.assertEqual(item['state'], 'waiting')
        self.assertEqual(self.order.yonyou_progress_state, 'ready')

    def test_missing_previous_line_retains_old_data(self):
        self._refresh()
        self._refresh(self._report([]))
        self.assertEqual(self.order._yonyou_public_progress()['items'][0]['shipped'], 52)
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')

    def test_order_change_never_queries_or_reuses_old_progress(self):
        self._refresh()
        self.order._progress_write({'yonyou_manual_review': True})
        self.assertFalse(self.order._yonyou_request_progress())
        status = self.order._yonyou_public_progress()
        self.assertTrue(status['changed'])
        self.assertIsNone(status['items'][0]['shipped'])

    def test_cancelled_no_query(self):
        self.order.with_context(_yonyou_write=WRITE_TOKEN).write({'state': 'cancel'})
        self.assertFalse(self.order._yonyou_request_progress())

    def test_wrong_order_response_rejected(self):
        rows = self._rows()
        rows[0]['源头单据号'] = 'ANOTHER-CUSTOMER-ORDER'
        self._refresh(self._report(rows))
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')
        self.assertFalse(self.order.yonyou_progress_snapshot)

    def test_incomplete_paging_rejected(self):
        report = self._report()
        report['data']['pager']['recordCount'] = 501
        report['data']['pager']['pageCount'] = 2
        self._refresh(report)
        self.assertEqual(self.order.yonyou_progress_state, 'blocked')

    def test_service_line_no_shipping_required(self):
        self.product.type = 'service'
        self.assertEqual(self.order._yonyou_public_progress()['items'][0]['state'], 'service')

    def test_portal_cannot_write_or_manually_refresh(self):
        with self.assertRaises(AccessError):
            self.order.with_user(self.portal).write({'yonyou_progress_state': 'ready'})
        with self.assertRaises(AccessError):
            self.order.with_user(self.portal).action_yonyou_refresh_progress()

    def test_worker_only_requested_orders_and_never_pushes(self):
        self.order._progress_write({'yonyou_progress_state': 'queued'})
        touched = []
        def refresh(record):
            touched.append(record.id)
            record._progress_write({'yonyou_progress_state': 'ready'})
        with patch.object(type(self.order), '_yonyou_refresh_progress', refresh), \
             patch.object(type(self.env['ir.cron']), '_commit_progress', return_value=10), \
             patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=AssertionError('No push')):
            self.order._cron_yonyou_progress()
        self.assertEqual(touched, [self.order.id])

    def test_template_renders_dates_and_missing_values(self):
        self._refresh()
        html = self.env['ir.ui.view']._render_template('b2b_yonyou.progress_panel',
            {'order': self.order, 'status': self.order._yonyou_public_progress()})
        self.assertIn('2026-09-24', html)
        self.assertIn('Partially shipped', html)

    def test_poll_endpoint_only_reads_owned_cache(self):
        self._refresh()
        portal_env = self.env(user=self.portal)
        website = self.env['website'].search([], limit=1).with_env(portal_env)
        with MockRequest(portal_env, website=website), \
             patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=AssertionError('Polling never calls ERP')):
            result = OrderProgress().check_progress(self.order.id)
        self.assertFalse(result['pending'])
        self.assertIn('Partially shipped', result['html'])
        self.assertNotIn(self.order.yonyou_id, result['html'])
        self.assertEqual(self.order.yonyou_progress_state, 'ready')

    def test_poll_endpoint_rejects_other_company_and_missing_id(self):
        other = self.env['sale.order'].create({'partner_id': self.portal.partner_id.copy({'parent_id': False}).id})
        portal_env = self.env(user=self.portal)
        website = self.env['website'].search([], limit=1).with_env(portal_env)
        with MockRequest(portal_env, website=website):
            for order_id in (other.id, 0):
                with self.assertRaises(NotFound):
                    OrderProgress().check_progress(order_id)

    def test_page_service_failure_renders_custom_notice(self):
        website_env = self.env(context=dict(self.env.context, lang='en_US'))
        website = website_env['website'].search([], limit=1)
        with MockRequest(website_env, website=website, url_root='http://localhost:18072/') as request:
            request.is_frontend_multilang = False
            html = website_env['ir.ui.view']._render_template('b2b_website.order_erp_status', {
                'order': self.order, 'status': False, 'error': 'Internal error',
                'page_name': 'erp_status', 'main_object': website})
        self.assertIn('Order progress is temporarily unavailable', html)
        self.assertNotIn('Internal error', html)

    def _old_attempt(self):
        self.order._progress_write({'yonyou_progress_attempt_at': fields.Datetime.now() - timedelta(seconds=61),
            'yonyou_progress_requested_at': fields.Datetime.now() - timedelta(seconds=61)})

    def test_manual_bypasses_only_successful_30_minute_cache(self):
        self._refresh()
        self._old_attempt()
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=AssertionError('No ERP in enqueue')):
            self.assertFalse(self.order._yonyou_request_progress())
            self.assertTrue(self.order._yonyou_request_progress(manual=True))
        self.assertEqual(self.order.yonyou_progress_state, 'queued')

    def test_manual_60_second_limit_does_not_extend_on_rejected_click(self):
        self._refresh()
        before = self.order.yonyou_progress_attempt_at
        next_at = self.order.yonyou_progress_next_at
        self.assertFalse(self.order._yonyou_request_progress(manual=True))
        self.assertGreater(self.order._yonyou_manual_refresh_info()['retry_after'], 0)
        self.assertEqual(self.order.yonyou_progress_attempt_at, before)
        self.assertEqual(self.order.yonyou_progress_next_at, next_at)

    def test_manual_pending_requests_join_without_new_trigger(self):
        with patch.object(type(self.env['ir.cron']), '_trigger') as trigger:
            self.assertTrue(self.order._yonyou_request_progress(manual=True))
            requested_at = self.order.yonyou_progress_requested_at
            self.assertFalse(self.order._yonyou_request_progress(manual=True))
        self.assertEqual(trigger.call_count, 1)
        self.assertEqual(self.order.yonyou_progress_requested_at, requested_at)

    def test_manual_preserves_failure_backoff_and_previous_snapshot(self):
        self._refresh()
        old = deepcopy(self.order.yonyou_progress_snapshot)
        self._old_attempt()
        self.order._progress_write({'yonyou_progress_state': 'delayed',
            'yonyou_progress_next_at': fields.Datetime.now() + timedelta(minutes=5)})
        self.assertFalse(self.order._yonyou_request_progress(manual=True))
        self.assertGreater(self.order._yonyou_manual_refresh_info()['retry_after'], 290)
        self.assertEqual(self.order.yonyou_progress_snapshot, old)

    def test_manual_cannot_bypass_review_or_connection_identity(self):
        for values in ({'yonyou_manual_review': True}, {'state': 'cancel'},
                       {'yonyou_source': {'connection_revision': -1}}):
            with self.subTest(values=values), self.env.cr.savepoint():
                previous = {key: self.order[key] for key in values}
                self.order._progress_write(values)
                self.assertFalse(self.order._yonyou_request_progress(manual=True))
                self.assertFalse(self.order._yonyou_manual_refresh_info()['supported'])
                self.order._progress_write(previous)

    def test_manual_portal_endpoint_only_queues_owned_order(self):
        self._refresh()
        self._old_attempt()
        portal_env = self.env(user=self.portal)
        website = self.env['website'].search([], limit=1).with_env(portal_env)
        with MockRequest(portal_env, website=website), \
             patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=AssertionError('No HTTP in customer click')):
            result = OrderProgress().refresh_progress(self.order.id)
        self.assertTrue(result['pending'])
        self.assertNotIn(self.order.yonyou_id, result['html'])
        self.assertEqual(self.order.yonyou_progress_state, 'queued')

    def test_manual_endpoint_rejects_other_company_and_missing_id(self):
        other = self.env['sale.order'].create({'partner_id': self.portal.partner_id.copy({'parent_id': False}).id})
        portal_env = self.env(user=self.portal)
        website = self.env['website'].search([], limit=1).with_env(portal_env)
        with MockRequest(portal_env, website=website):
            for order_id in (other.id, 0):
                with self.assertRaises(NotFound):
                    OrderProgress().refresh_progress(order_id)

    def test_manual_limit_is_shared_by_customer_contacts(self):
        self.order._yonyou_request_progress(manual=True)
        portal_env = self.env(user=self.portal)
        website = self.env['website'].search([], limit=1).with_env(portal_env)
        requested_at = self.order.yonyou_progress_requested_at
        with MockRequest(portal_env, website=website):
            result = OrderProgress().refresh_progress(self.order.id)
        self.assertTrue(result['pending'])
        self.assertEqual(self.order.yonyou_progress_requested_at, requested_at)

    def test_content_key_ignores_successful_check_timestamp(self):
        self._refresh()
        key = self.order._yonyou_public_progress()['content_key']
        self.order._progress_write({'yonyou_progress_updated_at': fields.Datetime.now() + timedelta(minutes=2)})
        self.assertEqual(self.order._yonyou_public_progress()['content_key'], key)
        rows = self._rows()
        rows[0].update({'销售出库数量': 100, '销售未发数量': 0})
        self._refresh(self._report(rows))
        self.assertNotEqual(self.order._yonyou_public_progress()['content_key'], key)
        self.assertFalse(self.order.yonyou_progress_notes)
