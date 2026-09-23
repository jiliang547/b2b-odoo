from copy import deepcopy
from unittest.mock import patch

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger
from .test_mapping import TestYonyouMapping
from ..models.client import CUSTOMER_DETAIL, ORDER_CREATE, ORDER_LIST, ORDER_DETAIL


@tagged('post_install', '-at_install')
class TestYonyouOrders(TestYonyouMapping):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.tax = cls.env['account.tax'].create({'name': 'ERP 0% exclusive', 'amount': 0,
            'amount_type': 'percent', 'type_tax_use': 'sale', 'company_id': cls.env.company.id,
            'price_include_override': 'tax_excluded'})
        cls.product.write({'taxes_id': [Command.set(cls.tax.ids)], 'type': 'service'})
        cls.pricelist = cls.env['product.pricelist'].create({'name': 'ERP USD tests',
            'currency_id': cls.env.ref('base.USD').id})
        cls.customer.write({'b2b_approved': True})

    def _fake(self, path, payload):
        if path == CUSTOMER_DETAIL:
            result = super()._fake(path, payload)
            result[0].update(country___code='RO',
                merchantApplyRanges=[{'id': 'range999', 'orgId___code': '999'}],
                principals=[{'id': 'principal999', 'merchantApplyRangeId': 'range999',
                    'isDefault': True, 'professSalesman___code': 'LQS0008', 'specialManagementDep___code': '05'}])
            return result
        return super()._fake(path, payload)

    def _order(self):
        self.config.write({'order_sync': True})
        with self._mock():
            self.customer._erp_verify()
            self.product._erp_verify()
        order = self.env['sale.order'].create({'partner_id': self.customer.id,
            'pricelist_id': self.pricelist.id,
            'order_line': [Command.create({'product_id': self.product.id,
                'product_uom_qty': 2, 'price_unit': 100, 'discount': 10,
                'tax_ids': [Command.set(self.tax.ids)]})]})
        return order

    def _confirm(self):
        order = self._order()
        order.action_confirm()
        job = self.env['b2b.integration.job'].search([('reference_model', '=', 'sale.order'),
            ('reference_id', '=', order.id), ('yonyou_order', '=', True)])
        self.assertEqual(len(job), 1)
        return order, job

    def _remote(self, header):
        return {'id': '9876543210123456789', 'code': header['code'],
            'salesOrgId_code': header['salesOrgId'], 'agentId_code': header['agentId'],
            'corpContact_code': header['corpContact'], 'saleDepartmentId_code': header['saleDepartmentId'],
            'payMoney': header['payMoney'], 'orderPrices': {'originalCode': header['orderPrices!currency']},
            'orderDetails': [{'productCode': l['productId'], 'qty': l['qty'], 'oriSum': l['oriSum'],
                'orderDetailPrices': {'oriMoney': l['orderDetailPrices!oriMoney'],
                                      'oriTax': l['orderDetailPrices!oriTax']}} for l in header['orderDetails']]}

    def test_order_confirmation_is_local_and_idempotent(self):
        order = self._order()
        with patch.object(type(self.env['b2b.yonyou.client']), '_http', side_effect=AssertionError('No network in confirmation')):
            order.action_confirm()
            order._b2b_enqueue_erp_sync()
        self.assertEqual(len(order.b2b_erp_job_ids), 1)
        self.assertEqual(len(order.yonyou_key), 32)
        self.assertEqual(order.yonyou_source['org'], '999')

    def test_payload_defaults_discount_units_dates(self):
        order, job = self._confirm()
        with self._mock():
            self.assertFalse(job._process_locked())
        self.assertEqual(job.state, 'pending')
        data = job.yonyou_payload['data']
        self.assertEqual(data['payMoney'], 180)
        self.assertEqual(data['orderDetails'][0]['orderDetailPrices!oriUnitPrice'], 90)
        self.assertEqual(data['corpContact'], 'LQS0008')
        self.assertEqual(data['orderPrices!currency'], 'USD')
        self.assertFalse(data['orderPrices!taxInclusive'])
        self.assertTrue(data['orderDefineCharacter!SFDT'])
        self.assertEqual(data['orderDetails'][0]['stockOrgId'], data['salesOrgId'])
        self.assertEqual(data['orderPrices!exchRate'], 6.3)

    def test_portal_payment_callback_can_enqueue_without_internal_role(self):
        order = self._order()
        self.assertFalse(self.portal._is_internal())
        order.with_user(self.portal).sudo().action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(len(order.b2b_erp_job_ids), 1)
        self.assertTrue(order.b2b_erp_job_ids.yonyou_order)
        self.assertFalse(self.portal._is_internal())

    def test_rate_change_does_not_reprice_queued_order(self):
        order, job = self._confirm()
        self.config.usd_rate = 7.1
        with self._mock():
            job._process_locked()
        self.assertEqual(job.yonyou_payload['data']['orderPrices!exchRate'], 6.3)

    def test_customer_currency_and_country_contract(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantAppliedDetail'].update(transactionCurrencyId='cny', transactionCurrencyId___code='CNY')
            return data
        with self._mock(fake):
            result = self.env['b2b.yonyou.client']._customer('C001', '999')
        self.assertEqual(result['currency'], 'CNY')
        self.assertFalse(result['currency_defaulted'])

    def test_unknown_currency_id_is_not_usd(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantAppliedDetail']['transactionCurrencyId'] = 'unknown'
            return data
        with self._mock(fake), self.assertRaises(UserError):
            self.env['b2b.yonyou.client']._customer('C001', '999')

    def test_other_organization_principal_is_not_used(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['principals'][0]['merchantApplyRangeId'] = 'other'
            return data
        with self._mock(fake):
            result = self.env['b2b.yonyou.client']._customer('C001', '999')
        self.assertFalse(result['salesperson'])

    def _scoped_customer_fake(self, path, payload):
        data = self._fake(path, payload)
        if path == CUSTOMER_DETAIL:
            self.assertEqual(payload[0]['belongOrgCode'], '999')
            customer = data[0]
            customer.pop('merchantApplyRanges')
            customer['createOrg___code'] = 'global00'
            customer['principals'][0].update(
                merchantId=customer['id'], merchantId___code=customer['code'],
                professSalesman___code='LQSTEST', specialManagementDep___code='cs')
        return data

    def test_scoped_customer_without_range_table_prepares_actual_principal(self):
        order, job = self._confirm()
        with self._mock(self._scoped_customer_fake):
            job._process_locked()
        self.assertEqual(job.state, 'pending')
        self.assertEqual(job.yonyou_payload['data']['corpContact'], 'LQSTEST')
        self.assertEqual(job.yonyou_payload['data']['saleDepartmentId'], 'cs')

    def test_scoped_customer_empty_range_table_supported(self):
        for value in (None, []):
            with self.subTest(ranges=value):
                def fake(path, payload):
                    data = self._scoped_customer_fake(path, payload)
                    if path == CUSTOMER_DETAIL:
                        data[0]['merchantApplyRanges'] = value
                    return data
                with self._mock(fake):
                    result = self.env['b2b.yonyou.client']._customer('C001', '999')
                self.assertEqual(result['salesperson'], 'LQSTEST')

    def test_scoped_customer_wrong_applied_organization_rejected(self):
        def fake(path, payload):
            data = self._scoped_customer_fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantAppliedDetail']['belongOrgId___code'] = 'other'
            return data
        with self._mock(fake), self.assertRaises(UserError):
            self.env['b2b.yonyou.client']._customer('C001', '999')

    def test_scoped_customer_contradictory_principal_not_used(self):
        for field, value in [('merchantId', 'other'), ('merchantId___code', 'OTHER'),
                             ('belongOrgId___code', 'other'), ('orgId___code', 'other')]:
            with self.subTest(field=field):
                def fake(path, payload):
                    data = self._scoped_customer_fake(path, payload)
                    if path == CUSTOMER_DETAIL:
                        data[0]['principals'][0][field] = value
                    return data
                with self._mock(fake):
                    result = self.env['b2b.yonyou.client']._customer('C001', '999')
                self.assertFalse(result['salesperson'])

    def test_range_table_for_other_org_does_not_enable_fallback(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantApplyRanges'][0]['orgId___code'] = 'other'
            return data
        with self._mock(fake):
            result = self.env['b2b.yonyou.client']._customer('C001', '999')
        self.assertFalse(result['salesperson'])

    def test_scoped_customer_ambiguous_defaults_not_guessed(self):
        for variant in ('no_default', 'two_defaults', 'mixed_ranges'):
            with self.subTest(variant=variant):
                def fake(path, payload):
                    data = self._scoped_customer_fake(path, payload)
                    if path == CUSTOMER_DETAIL:
                        principals = data[0]['principals']
                        if variant == 'no_default':
                            principals[0]['isDefault'] = False
                        else:
                            other = dict(principals[0], id='another', professSalesman___code='OTHER')
                            if variant == 'mixed_ranges':
                                other.update(merchantApplyRangeId='other', isDefault=False)
                            principals.append(other)
                    return data
                with self._mock(fake):
                    result = self.env['b2b.yonyou.client']._customer('C001', '999')
                self.assertFalse(result['salesperson'])

    def test_nested_and_top_level_principal_deduplicated(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantApplyRanges'][0]['principals'] = deepcopy(data[0]['principals'])
            return data
        with self._mock(fake):
            result = self.env['b2b.yonyou.client']._customer('C001', '999')
        self.assertEqual(result['salesperson'], 'LQS0008')

    @mute_logger('odoo.addons.b2b_erp_connector.models.integration_job')
    def test_readback_wrong_salesperson_or_department_not_success(self):
        order, job = self._confirm()
        with self._mock():
            job._process_locked()
        for field in ('corpContact_code', 'saleDepartmentId_code'):
            with self.subTest(field=field):
                remote = self._remote(job.yonyou_payload['data'])
                remote[field] = 'WRONG'
                def fake(path, payload):
                    if path == ORDER_LIST:
                        return {'pageCount': 1, 'recordList': [{'id': remote['id'], 'code': remote['code']}]}
                    if path == ORDER_DETAIL:
                        return remote
                    raise AssertionError('Must not create another order')
                with self.env.cr.savepoint(), self._mock(fake):
                    self.assertFalse(job._process_locked())
                    self.assertEqual(job.state, 'dead')
                    self.assertFalse(order.yonyou_id)
                    job._system_write({'state': 'pending'})

    @mute_logger('odoo.addons.b2b_erp_connector.models.integration_job')
    def test_mismatch_does_not_change_paid_order(self):
        order, job = self._confirm()
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['merchantAppliedDetail']['transactionCurrencyId___code'] = 'CNY'
            return data
        with self._mock(fake):
            job._process_locked()
        self.assertEqual(job.state, 'dead')
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.amount_total, 180)
        self.assertFalse(job.yonyou_payload)

    def test_checkout_currency_mismatch_blocked_before_payment(self):
        order = self._order()
        cny = self.env['product.pricelist'].create({'name': 'CNY checkout', 'currency_id': self.env.ref('base.CNY').id})
        order.pricelist_id = cny
        with self.assertRaises(ValidationError):
            order._yonyou_check_checkout()

    def test_native_thirteen_percent_tax_is_not_added_twice(self):
        order = self._order()
        self.tax.amount = 13
        order.order_line._compute_tax_ids()
        order.action_confirm()
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL:
                data[0]['country___code'] = 'CN'
            return data
        with self._mock(fake):
            payload = order._yonyou_payload()['data']
        self.assertAlmostEqual(payload['payMoney'], 203.4)
        self.assertEqual(payload['orderDetails'][0]['orderDetailPrices!oriMoney'], 180)
        self.assertEqual(payload['orderDetails'][0]['orderDetailPrices!oriTax'], 23.4)

    def test_changes_are_manual_not_second_orders(self):
        order, job = self._confirm()
        order.order_line.price_unit = 120
        self.assertTrue(order.yonyou_manual_review)
        self.assertEqual(len(order.b2b_erp_job_ids), 1)
        with self._mock(), self.assertRaises(UserError):
            order._yonyou_payload()

    def test_successful_readback_and_retry_does_not_create(self):
        order, job = self._confirm()
        with self._mock():
            job._process_locked()
        remote = self._remote(job.yonyou_payload['data'])
        calls = []
        def fake(path, payload):
            calls.append(path)
            if path == ORDER_LIST:
                return {'pageCount': 1, 'recordList': [{'id': remote['id'], 'code': remote['code']}]}
            if path == ORDER_DETAIL:
                return remote
            raise AssertionError(path)
        with self._mock(fake):
            self.assertTrue(job._process_locked())
        self.assertEqual(job.state, 'success')
        self.assertNotIn(ORDER_CREATE, calls)
        self.assertEqual(order.yonyou_id, remote['id'])

    @mute_logger('odoo.addons.b2b_erp_connector.models.integration_job')
    def test_readback_mismatch_never_resubmits(self):
        order, job = self._confirm()
        with self._mock():
            job._process_locked()
        remote = self._remote(job.yonyou_payload['data'])
        remote['payMoney'] += 1
        def fake(path, payload):
            if path == ORDER_LIST:
                return {'pageCount': 1, 'recordList': [{'id': remote['id'], 'code': remote['code']}]}
            if path == ORDER_DETAIL:
                return remote
            raise AssertionError('Must not create an existing order')
        with self._mock(fake):
            self.assertFalse(job._process_locked())
        self.assertEqual(job.state, 'dead')

    def test_no_portal_snapshot_forgery(self):
        order = self._order()
        with self.assertRaises(AccessError):
            order.with_user(self.portal).write({'yonyou_id': 'forged'})

    def test_live_organization_is_blocked(self):
        with self.assertRaises(ValidationError):
            self.config.write({'order_sync': True, 'sales_org': '1'})

    def test_multiline_order_lookup_deduplicates_headers_across_pages(self):
        def fake(path, payload):
            self.assertEqual(path, ORDER_LIST)
            return {'pageCount': 2, 'recordList': [
                {'id': 9876543210123456789, 'code': 'PH-T-UAT', 'orderDetailId': payload['pageIndex']}]}
        with self._mock(fake):
            self.assertEqual(self.env['b2b.yonyou.client']._order_by_code('PH-T-UAT'), '9876543210123456789')

    def test_duplicate_document_number_blocks_creation(self):
        with self._mock(lambda path, payload: {'pageCount': 1, 'recordList': [
                {'id': '1', 'code': 'same'}, {'id': '2', 'code': 'same'}]}), self.assertRaises(UserError):
            self.env['b2b.yonyou.client']._order_by_code('same')

    def test_native_company_fiscal_position_is_used_for_contact(self):
        self.tax.amount = 13
        rule = self.env['account.fiscal.position'].create({'name': 'ERP export native test',
            'company_id': self.env.company.id})
        mapped = self.env['account.tax'].create({'name': 'ERP export replacement', 'amount': 0,
            'amount_type': 'percent', 'type_tax_use': 'sale', 'company_id': self.env.company.id,
            'price_include_override': 'tax_excluded', 'fiscal_position_ids': [Command.set(rule.ids)],
            'original_tax_ids': [Command.set(self.tax.ids)]})
        self.customer.yonyou_fiscal_position_id = rule
        contact = self.env['res.partner'].create({'name': 'ERP buyer contact', 'parent_id': self.customer.id})
        order = self.env['sale.order'].create({'partner_id': contact.id, 'pricelist_id': self.pricelist.id,
            'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': 100})]})
        self.assertEqual(order.fiscal_position_id, rule)
        self.assertEqual(order.order_line.tax_ids, mapped)
        self.assertEqual(order.amount_total, 100)

    def test_no_tax_is_native_zero_tax(self):
        order = self._order()
        order.order_line.tax_ids = False
        order._yonyou_check_checkout()
        order.action_confirm()
        with self._mock():
            self.assertEqual(order._yonyou_payload()['data']['orderDetails'][0]['taxId'], '0%')

    def test_freight_service_is_a_regular_mapped_line(self):
        order = self._order()
        freight = self.env['product.product'].create({'name': 'Test Freight', 'type': 'service', 'yonyou_code': '000020'})
        with self._mock():
            freight._erp_verify()
        order.write({'order_line': [Command.create({'product_id': freight.id,
            'product_uom_qty': 1, 'price_unit': 25, 'tax_ids': [Command.set(self.tax.ids)]})]})
        order.action_confirm()
        with self._mock():
            data = order._yonyou_payload()['data']
        self.assertEqual(data['payMoney'], 205)
        self.assertEqual(len(data['orderDetails']), 2)
        self.assertNotIn('freight', data)

    def test_job_company_access_is_enforced(self):
        from odoo.addons.mail.tests.common import mail_new_test_user
        order, job = self._confirm()
        other = self.env['res.company'].create({'name': 'ERP Other Seller'})
        user = mail_new_test_user(self.env, login='erp-other-company-integrator',
            groups='b2b_erp_connector.group_b2b_integration_manager',
            company_id=other.id, company_ids=[Command.set(other.ids)])
        self.assertEqual(job.yonyou_company_id, order.company_id)
        with self.assertRaises(AccessError):
            job.with_user(user).with_context(allowed_company_ids=other.ids).read(['name'])

    @mute_logger('odoo.addons.b2b_erp_connector.models.integration_job')
    def test_lost_create_response_recovers_without_duplicate(self):
        order, job = self._confirm()
        with self._mock():
            job._process_locked()
        remote = self._remote(job.yonyou_payload['data'])
        created = []
        def fake(path, payload):
            if path == ORDER_LIST:
                return {'pageCount': 1, 'recordList': [
                    {'id': remote['id'], 'code': remote['code']}] if created else []}
            if path == ORDER_CREATE:
                created.append(deepcopy(payload))
                raise UserError('Simulated response lost after ERP commit')
            if path == ORDER_DETAIL:
                return remote
            raise AssertionError(path)
        with self._mock(fake):
            self.assertFalse(job._process_locked())
            self.assertEqual(job.state, 'failed')
            self.assertTrue(job._process_locked())
        self.assertEqual(len(created), 1)
        self.assertEqual(job.state, 'success')
