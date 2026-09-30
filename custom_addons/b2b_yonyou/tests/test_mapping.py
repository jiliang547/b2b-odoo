from copy import deepcopy
from unittest.mock import patch
from odoo import fields
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.mail.tests.common import mail_new_test_user
from ..models.client import PRODUCT_LIST, PRODUCT_DETAIL, CUSTOMER_LIST, CUSTOMER_DETAIL, CLASS_LIST, CUSTOMER_CREATE
from ..models.client import STAFF_DETAIL, DEPARTMENT_DETAIL, ORG_DETAIL
from ..models.config import WRITE_TOKEN


@tagged('post_install', '-at_install')
class TestYonyouMapping(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.env.ref('b2b_yonyou.connection')
        cls.config.write({'enabled': True, 'registration_sync': True, 'test_mode': True,
            'management_org': '999', 'default_use_org': '999'})
        cls.manager = mail_new_test_user(cls.env, login='erp-uat-manager',
            groups='b2b_core.group_b2b_manager,b2b_core.group_b2b_product_manager')
        cls.operator = mail_new_test_user(cls.env, login='erp-uat-operator', groups='b2b_core.group_b2b_operator')
        cls.portal = mail_new_test_user(cls.env, login='erp-uat-portal', groups='base.group_portal')
        cls.brand = cls.env['b2b.product.brand'].create({'name': 'ERP Unit Test Brand',
            'b2b_selling_company_id': cls.env.company.id, 'yonyou_class_code': '05',
            'yonyou_salesperson': 'LQS0008', 'yonyou_department': '05'})
        cls.product = cls.env['product.product'].create({'name': 'ERP Unit Test Material', 'yonyou_code': '000020'})
        cls.customer = cls.env['res.partner'].create({'name': 'ERP Unit Test Customer', 'is_company': True,
            'b2b_selling_company_id': cls.env.company.id, 'yonyou_code': 'C001'})
        cls.product_detail = {'id': 2496605597954211851, 'code': '000020', 'name': {'simplifiedName': 'Test'},
            'deleted': False, 'hasSpecs': False, 'defaultSKUId': 2496605597954211858,
            'unitCode': '006', 'unitName': 'Each', 'enableAssistUnit': False,
            'detail': {'orgId': 'org999', 'canSale': True, 'stopstatus': False,
                'batchUnitCode': '006', 'batchPriceUnitCode': '006'},
            'productOrges': [{'orgCode': '999', 'orgId': 'org999', 'isApplied': True}]}

    def _fake(self, path, payload):
        if path == PRODUCT_LIST:
            return {'pageCount': 1, 'recordList': [{'id': 55, 'code': 'SEC10000020'},
                {'id': 2496605597954211851, 'code': '000020'}]}
        if path == PRODUCT_DETAIL:
            return [deepcopy(self.product_detail)]
        if path == CLASS_LIST:
            return [{'id': 15, 'code': payload['code'], 'name': {'simplifiedName': 'LIKE'}, 'isEnabled': True}]
        if path == CUSTOMER_LIST:
            return [{'id': 1234567890123456789, 'code': payload['code'], 'stopStatus': False, 'customerClassCode': '05'}]
        if path == CUSTOMER_DETAIL:
            return [{'id': 1234567890123456789, 'code': payload[0]['code'], 'name': {'simplifiedName': 'Customer'},
                'createOrg___code': '999', 'customerClass___code': '05', 'customerClass___name': 'LIKE',
                'merchantAppliedDetail': {'belongOrgId___code': '999', 'stopstatus': False},
                'principals': [{'id': 'p1', 'isDefault': True, 'professSalesman___code': 'LQS0008',
                    'professSalesman___name': 'Test Salesperson', 'specialManagementDep___code': '05',
                    'specialManagementDep___name': 'Test Department'}]}]
        if path == STAFF_DETAIL:
            return {'id': 'staff1', 'code': payload['code'], 'name': 'Test Salesperson', 'enable': 1,
                'biz_man_tag': 1, 'mainJobList': [{'staff_id': 'staff1', 'org_id': 'org999',
                    'dept_id': 'dept05', 'dr': 0, 'begindate': '2020-01-01 00:00:00'}]}
        if path == ORG_DETAIL:
            return {'id': payload['id'], 'code': '999', 'enable': 1}
        if path == DEPARTMENT_DETAIL:
            return {'id': payload['id'], 'code': '05', 'name': {'en_US': 'Test Department'},
                'enable': 1, 'dr': 0, 'parentorgid': 'org999'}
        raise AssertionError(path)

    def _create_timeout(self, path, payload):
        if path == CUSTOMER_CREATE:
            raise UserError('Simulated creation timeout')
        return self._fake(path, payload)

    def _mock(self, fn=None):
        return patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=fn or self._fake)

    def test_product_exact_and_long_ids(self):
        with self._mock():
            self.product.with_user(self.manager).action_yonyou_verify()
        self.assertEqual(self.product.yonyou_status, 'verified')
        self.assertEqual(self.product.yonyou_snapshot['id'], '2496605597954211851')
        self.assertEqual(self.product.yonyou_snapshot['sku_id'], '2496605597954211858')
        self.assertEqual(self.product.yonyou_snapshot['unit_code'], '006')
        self.assertEqual(self.product.name, 'ERP Unit Test Material')

    def test_changed_code_invalidates(self):
        with self._mock():
            self.product.action_yonyou_verify()
        self.product.yonyou_code = '000021'
        self.assertEqual(self.product.yonyou_status, 'stale')

    def test_template_writes_variant(self):
        self.product.product_tmpl_id.write({'yonyou_code': '000020'})
        with self._mock():
            self.product.product_tmpl_id.with_user(self.manager).action_yonyou_verify()
        self.assertEqual(self.product.yonyou_status, 'verified')

    def test_new_template_keeps_entered_material_code(self):
        template = self.env['product.template'].with_user(self.manager).create({
            'name': 'New mapped template', 'yonyou_code': '000020',
            'yonyou_company_id': self.env.company.id})
        self.assertEqual(template.product_variant_id.yonyou_code, '000020')
        with self._mock():
            self.assertEqual(template.action_yonyou_verify()['params']['type'], 'success')

    def test_product_manager_can_verify_without_customer_permissions(self):
        user = mail_new_test_user(self.env, login='erp-product-only', groups='b2b_core.group_b2b_product_manager')
        with self._mock():
            self.assertEqual(self.product.with_user(user).action_yonyou_verify()['params']['type'], 'success')
        with self.assertRaises(AccessError):
            self.customer.with_user(user).action_yonyou_verify()

    def test_wrong_organization_rejected(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == PRODUCT_DETAIL:
                data[0]['detail']['orgId'] = 'wrong'
            return data
        with self._mock(fake):
            action = self.product.action_yonyou_verify()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertFalse(self.product.yonyou_snapshot)

    def test_failure_revokes_verification(self):
        with self._mock():
            self.product.action_yonyou_verify()
        with patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=UserError('Unavailable')):
            self.product.action_yonyou_verify()
        self.assertEqual(self.product.yonyou_status, 'unverified')

    def test_multi_unit_rejected(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == PRODUCT_DETAIL:
                data[0]['detail']['batchUnitCode'] = 'BOX'
            return data
        with self._mock(fake):
            self.assertEqual(self.product.action_yonyou_verify()['params']['type'], 'danger')

    def test_multi_sku_rejected(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == PRODUCT_DETAIL:
                data[0]['hasSpecs'] = True
            return data
        with self._mock(fake):
            self.assertEqual(self.product.action_yonyou_verify()['params']['type'], 'danger')

    def test_no_status_does_not_mean_enabled(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == PRODUCT_DETAIL:
                del data[0]['detail']['stopstatus']
            return data
        with self._mock(fake):
            self.assertEqual(self.product.action_yonyou_verify()['params']['type'], 'danger')

    def test_native_stop_status_supported(self):
        def fake(path, payload):
            data = self._fake(path, payload)
            if path == PRODUCT_DETAIL:
                data[0]['detail']['stopStatus'] = data[0]['detail'].pop('stopstatus')
            return data
        with self._mock(fake):
            self.assertEqual(self.product.action_yonyou_verify()['params']['type'], 'success')

    def test_exact_duplicate_rejected(self):
        with self._mock(lambda path, payload: [{'id': 1, 'code': '05'}, {'id': 2, 'code': '05'}]):
            with self.assertRaises(UserError):
                self.env['b2b.yonyou.client']._search(CLASS_LIST, '05')

    def test_category_real_name(self):
        with self._mock():
            self.brand.with_user(self.manager).action_yonyou_verify_class()
        self.assertEqual(self.brand.yonyou_class_result, '05 — LIKE')
        self.brand.yonyou_class_code = '06'
        self.assertFalse(self.brand.yonyou_class_snapshot)

    def test_customer_contact_inherits(self):
        with self._mock():
            self.customer.with_user(self.manager).action_yonyou_verify()
        contact = self.env['res.partner'].create({'name': 'Child', 'parent_id': self.customer.id})
        self.assertEqual(contact.yonyou_contact_code, 'C001')
        self.assertEqual(contact.b2b_effective_erp_customer_id, '1234567890123456789')
        self.assertFalse(contact.yonyou_code)

    def test_customer_duplicate_binding(self):
        with self._mock():
            self.customer.action_yonyou_verify()
            other = self.env['res.partner'].create({'name': 'Other', 'is_company': True,
                'b2b_selling_company_id': self.env.company.id, 'yonyou_code': 'C001'})
            self.assertEqual(other.action_yonyou_verify()['params']['type'], 'danger')
            self.assertFalse(other.b2b_erp_customer_id)

    def test_customer_class_conflict_no_erp_write(self):
        self.customer.yonyou_class_code = '06'
        with self._mock() as mock:
            self.assertEqual(self.customer.action_yonyou_verify()['params']['type'], 'danger')
        self.assertNotIn(CUSTOMER_CREATE, [call.args[0] for call in mock.call_args_list])

    def test_unprivileged_actions_denied(self):
        for user in (self.operator, self.portal):
            with self.assertRaises(AccessError):
                self.product.with_user(user).action_yonyou_verify()
            with self.assertRaises(AccessError):
                self.customer.with_user(user).action_yonyou_verify()
            with self.assertRaises(AccessError):
                self.brand.with_user(user).action_yonyou_verify_class()

    def test_cannot_forge_snapshot_even_with_rpc_context(self):
        with self.assertRaises(AccessError):
            self.product.with_user(self.manager).with_context(_yonyou_write=True).write({'yonyou_snapshot': {'id': 'fake'}})

    def test_secrets_not_readable_by_manager(self):
        with self.assertRaises(AccessError):
            self.config.with_user(self.manager).read(['app_secret'])
        with self.assertRaises(AccessError):
            self.config.with_user(self.manager).write({'enabled': False})

    def test_no_order_endpoint(self):
        with self.assertRaises(UserError):
            self.env['b2b.yonyou.client']._call('/yonbip/sd/voucherorder/singleSave', {})

    def test_live_c4_empty_customer_search_status(self):
        client = self.env['b2b.yonyou.client']
        with patch.object(type(client), '_token', return_value='test-token'), \
             patch.object(type(client), '_http', return_value={'code': '118001', 'message': '根据条件查询结果为空'}):
            self.assertIsNone(client._search(CUSTOMER_LIST, 'NEW-CUSTOMER'))
            with self.assertRaises(UserError):
                client._call(CUSTOMER_CREATE, {'data': {'createOrgCode': '999', 'merchantApplyRanges': [{'orgIdCode': '999'}]}})

    def test_customer_query_permission_failure_is_not_empty(self):
        client = self.env['b2b.yonyou.client']
        with patch.object(type(client), '_token', return_value='test-token'), \
             patch.object(type(client), '_http', return_value={'code': '118001', 'message': 'Permission denied'}), \
             self.assertRaises(UserError):
            client._search(CUSTOMER_LIST, 'NEW-CUSTOMER')

    def test_no_production_customer_creation(self):
        with self.assertRaises(UserError):
            self.env['b2b.yonyou.client']._call(CUSTOMER_CREATE, {'data': {'createOrgCode': 'global00'}})

    def test_test_organization_guard(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.config.management_org = 'global00'

    def _application(self):
        user = mail_new_test_user(self.env, login='erp-reg-new', groups='base.group_portal')
        kind = self.env['b2b.customer.type'].create({'name': 'ERP Registration UAT'})
        return self.env['b2b.registration.application'].create({
            'user_id': user.id, 'partner_id': user.partner_id.id, 'website_id': self.env['website'].search([], limit=1).id,
            'state': 'pending', 'email_verified_at': fields.Datetime.now(), 'full_name': 'Test Person',
            'job_title': 'Buyer', 'company_name': 'Customer', 'country_id': self.env.ref('base.ro').id,
            'business_email': 'erp-reg@example.test', 'company_phone': '+40 212345678', 'mobile': '+40 721234567',
            'customer_type_id': kind.id, 'company_resolution': 'create', 'yonyou_brand_id': self.brand.id,
            'yonyou_class_code': '05'})

    def test_registration_timeout_recovery_no_duplicate_create(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock():
            app.action_yonyou_verify_class()
        with patch.object(type(self.env['b2b.yonyou.client']), '_search', return_value=None), \
             patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=self._create_timeout):
            action = app.action_approve()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(app.state, 'pending')
        key = app.yonyou_create_payload['data']['resubmitCheckKey']
        with self._mock() as mock:
            app.action_approve()
        self.assertEqual(app.state, 'approved')
        self.assertEqual(app.yonyou_create_payload['data']['resubmitCheckKey'], key)
        self.assertNotIn(CUSTOMER_CREATE, [call.args[0] for call in mock.call_args_list])
        self.assertEqual(app.partner_id.commercial_partner_id.b2b_erp_customer_id, '1234567890123456789')

    def test_registration_success_and_payload(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock():
            app.action_yonyou_verify_class()
        created = []
        def fake(path, payload):
            if path == CUSTOMER_LIST and not created:
                return []
            if path == CUSTOMER_CREATE:
                created.append(payload)
                return {'id': 1234567890123456789}
            return self._fake(path, payload)
        with self._mock(fake):
            app.action_approve()
        self.assertEqual(app.state, 'approved')
        self.assertEqual(len(created), 1)
        data = created[0]['data']
        self.assertEqual(data['createOrgCode'], '999')
        self.assertEqual(data['merchantApplyRanges'], [{'orgIdCode': '999'}])
        self.assertEqual(data['email'], app.business_email)
        self.assertEqual(data['contactTel'], app.company_phone)
        self.assertEqual(data['merchantContactInfos'][0]['areaCodeMobile'], '+40-721234567')
        self.assertNotIn('password', str(data))

    def test_registration_unverified_email_cannot_create(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        app.email_verified_at = False
        with self._mock() as mock, self.assertRaises(UserError):
            app.action_approve()
        mock.assert_not_called()

    def test_existing_company_approval_queries_only(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        app.write({'company_resolution': 'existing', 'resolved_partner_id': self.customer.id})
        app.activity_schedule('mail.mail_activity_data_todo', user_id=self.manager.id)
        self.assertTrue(app.activity_ids)
        with self._mock() as mock:
            app.action_approve()
        self.assertEqual(app.state, 'approved')
        self.assertFalse(app.activity_ids)
        self.assertTrue(app.message_ids)
        self.assertEqual(app.partner_id.parent_id, self.customer)
        self.assertEqual(self.customer.phone, app.company_phone)
        self.assertNotIn(CUSTOMER_CREATE, [call.args[0] for call in mock.call_args_list])

    def test_disabled_sync_keeps_native_approval(self):
        self.config.write({'registration_sync': False})
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock() as mock:
            app.action_approve()
        self.assertEqual(app.state, 'approved')
        mock.assert_not_called()

    def test_payload_cannot_change_after_uncertain_attempt(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock():
            app.action_yonyou_verify_class()
        with patch.object(type(self.env['b2b.yonyou.client']), '_search', return_value=None), \
             patch.object(type(self.env['b2b.yonyou.client']), '_call', side_effect=self._create_timeout):
            app.action_approve()
        app.company_name = 'Different Name'
        with self._mock() as mock:
            result = app.action_approve()
        self.assertEqual(result['params']['type'], 'danger')
        self.assertEqual(app.state, 'pending')
        mock.assert_not_called()

    def test_repeat_approval_does_not_create_again(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        app.write({'company_resolution': 'existing', 'resolved_partner_id': self.customer.id})
        with self._mock():
            app.action_approve()
        with self._mock() as mock, self.assertRaises(UserError):
            app.action_approve()
        mock.assert_not_called()

    def test_partner_category_change_invalidates_result(self):
        self.customer.yonyou_class_code = '05'
        with self._mock():
            self.customer.action_yonyou_verify_class()
        self.customer.yonyou_class_code = '06'
        self.assertFalse(self.customer.yonyou_class_snapshot)

    def test_existing_code_never_creates_or_overwrites(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock() as mock:
            app.action_yonyou_verify_class()
            result = app.action_approve()
        self.assertEqual(result['params']['type'], 'danger')
        self.assertEqual(app.state, 'pending')
        self.assertNotIn(CUSTOMER_CREATE, [call.args[0] for call in mock.call_args_list])
