from copy import deepcopy
from unittest.mock import patch
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from .test_mapping import TestYonyouMapping
from ..models.client import STAFF_DETAIL, ORG_DETAIL, DEPARTMENT_DETAIL, CUSTOMER_CREATE, CUSTOMER_LIST, CUSTOMER_DETAIL


@tagged('post_install', '-at_install')
class TestYonyouPrincipal(TestYonyouMapping):
    def test_detect_department_and_minimal_snapshot(self):
        self.customer.yonyou_salesperson = 'LQS0008'
        with self._mock():
            self.customer.with_user(self.manager).action_yonyou_verify_principal()
        self.assertEqual(self.customer.yonyou_department, '05')
        self.assertEqual(self.customer.yonyou_principal_status, 'verified')
        self.assertEqual(self.customer.yonyou_salesperson_name, 'Test Salesperson')
        self.assertNotIn('mainJobList', self.customer.yonyou_principal_snapshot)
        self.assertNotIn('bankAcctList', self.customer.yonyou_principal_snapshot)
        self.customer.yonyou_salesperson = 'OTHER'
        self.assertEqual(self.customer.yonyou_principal_status, 'stale')
        self.assertFalse(self.customer.yonyou_salesperson_name)

    def test_customer_refresh_uses_erp_and_locks_manual_edits(self):
        with self._mock() as mock:
            self.customer.action_yonyou_verify()
        self.assertEqual(self.customer.yonyou_salesperson, 'LQS0008')
        self.assertEqual(self.customer.yonyou_department, '05')
        self.assertNotIn(STAFF_DETAIL, [c.args[0] for c in mock.call_args_list])
        with self.assertRaises(UserError):
            self.customer.with_user(self.manager).write({'yonyou_salesperson': 'OTHER'})

    def test_category_verify_never_overwrites_principal(self):
        self.customer.write({'yonyou_salesperson': 'KEEP', 'yonyou_class_code': '05'})
        with self._mock():
            self.customer.action_yonyou_verify_class()
        self.assertEqual(self.customer.yonyou_salesperson, 'KEEP')

    def test_brand_prefill_and_review_override(self):
        app = self._application()
        self.assertEqual(app.yonyou_salesperson, self.brand.yonyou_salesperson)
        app.write({'yonyou_salesperson': 'OVERRIDE', 'yonyou_department': '05'})
        with self._mock():
            app.action_yonyou_verify_principal()
        payload = app._erp_create_values(self.config, 'NEW', 'key')
        self.assertEqual(payload['data']['principals'][0]['professSalesmanCode'], 'OVERRIDE')
        self.assertEqual(self.brand.yonyou_salesperson, 'LQS0008')

    def test_api_rejects_stopped_non_salesperson_wrong_code_and_org(self):
        for kind in ('disabled', 'not_salesperson', 'wrong_code', 'wrong_org', 'wrong_department', 'deleted', 'expired', 'future'):
            with self.subTest(kind=kind):
                def fake(path, payload):
                    value = self._fake(path, payload)
                    if path == STAFF_DETAIL:
                        if kind == 'disabled': value['enable'] = 2
                        if kind == 'not_salesperson': value['biz_man_tag'] = 0
                        if kind == 'wrong_code': value['code'] = 'OTHER'
                        if kind == 'expired': value['mainJobList'][0]['enddate'] = '2020-01-01'
                        if kind == 'future': value['mainJobList'][0]['begindate'] = '9999-01-01'
                    if path == ORG_DETAIL and kind == 'wrong_org': value['code'] = 'OTHER'
                    if path == DEPARTMENT_DETAIL:
                        if kind == 'wrong_department': value['parentorgid'] = 'OTHER'
                        if kind == 'deleted': value['dr'] = 1
                    return value
                with self._mock(fake), self.assertRaises(UserError):
                    self.env['b2b.yonyou.client']._principal('LQS0008', '05', '999')

    def test_ambiguous_departments_require_explicit_code(self):
        def fake(path, payload):
            value = self._fake(path, payload)
            if path == STAFF_DETAIL:
                value['ptJobList'] = [dict(value['mainJobList'][0], dept_id='dept06')]
            if path == DEPARTMENT_DETAIL and payload['id'] == 'dept06': value['code'] = '06'
            return value
        with self._mock(fake):
            client = self.env['b2b.yonyou.client']
            with self.assertRaises(UserError): client._principal('LQS0008', '', '999')
            self.assertEqual(client._principal('LQS0008', '06', '999')['department'], '06')

    def test_unprivileged_cannot_select_verify_or_forge(self):
        for user in (self.operator, self.portal):
            with self.assertRaises(AccessError):
                self.customer.with_user(user).write({'yonyou_salesperson': 'LQS0008'})
            with self.assertRaises(AccessError):
                self.customer.with_user(user).action_yonyou_verify_principal()
        with self.assertRaises(AccessError):
            self.customer.with_user(self.manager).write({'yonyou_principal_snapshot': {'verified': True}})

    def test_verification_failure_clears_old_success(self):
        self.customer.write({'yonyou_salesperson': 'LQS0008'})
        with self._mock(): self.customer.action_yonyou_verify_principal()
        with self._mock(lambda *args: (_ for _ in ()).throw(UserError('API permission denied'))):
            action = self.customer.action_yonyou_verify_principal()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(self.customer.yonyou_principal_status, 'unverified')

    def test_frozen_registration_assignment_cannot_be_changed(self):
        app = self._application()
        app._erp_store({'yonyou_create_payload': {'data': {'principals': []}}})
        with self.assertRaises(UserError): app.write({'yonyou_salesperson': 'OTHER'})
        with self.assertRaises(UserError): app.action_yonyou_verify_principal()

    def test_unavailable_principal_blocks_approval_before_erp_create(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        with self._mock(): app.action_yonyou_verify_class()
        calls = []
        def fake(path, payload):
            calls.append(path)
            if path == STAFF_DETAIL: raise UserError('Employee unavailable')
            return self._fake(path, payload)
        with self._mock(fake): action = app.action_approve()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(app.state, 'pending')
        self.assertNotIn(CUSTOMER_CREATE, calls)
        self.assertFalse(app.yonyou_create_payload)

    def test_new_customer_readback_checks_override_and_does_not_overwrite_existing(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        app.yonyou_salesperson = 'OVERRIDE'
        with self._mock(): app.action_yonyou_verify_class()
        created = []
        def fake(path, payload):
            if path == CUSTOMER_LIST and not created: return []
            if path == CUSTOMER_CREATE:
                created.append(deepcopy(payload))
                return {'id': 1234567890123456789}
            return self._fake(path, payload)  # ERP returns the wrong default LQS0008.
        with self._mock(fake): action = app.action_approve()
        self.assertEqual(action['params']['type'], 'danger')
        self.assertEqual(app.state, 'pending')
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]['data']['principals'][0]['professSalesmanCode'], 'OVERRIDE')
        self.assertFalse(app.yonyou_pending_company_id)

    def test_new_customer_override_round_trip(self):
        app = self._application().with_user(self.manager).with_context(b2b_skip_registration_email=True)
        app.yonyou_salesperson = 'OVERRIDE'
        with self._mock(): app.action_yonyou_verify_class()
        created = []
        def fake(path, payload):
            if path == CUSTOMER_LIST and not created: return []
            if path == CUSTOMER_CREATE:
                created.append(deepcopy(payload))
                return {'id': 1234567890123456789}
            data = self._fake(path, payload)
            if path == CUSTOMER_DETAIL: data[0]['principals'][0]['professSalesman___code'] = 'OVERRIDE'
            return data
        with self._mock(fake): app.action_approve()
        self.assertEqual(app.state, 'approved')
        self.assertEqual(app.partner_id.commercial_partner_id.yonyou_salesperson, 'OVERRIDE')
        self.assertEqual(self.brand.yonyou_salesperson, 'LQS0008')
