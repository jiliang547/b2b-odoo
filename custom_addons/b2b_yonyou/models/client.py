"""Small server-side C4 client. No automatic HTTP write retries."""
import base64
import hashlib
import hmac
import json
import re
import time
from urllib import error, parse, request
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .config import WRITE_TOKEN

GATEWAY = 'https://c4.yonyoucloud.com/iuap-api-gateway'
AUTH = 'https://c4.yonyoucloud.com/iuap-api-auth/open-auth/selfAppAuth/base/v1/getAccessToken'
PRODUCT_LIST = '/yonbip/digitalModel/product/listproductbycondition'
PRODUCT_DETAIL = '/yonbip/digitalModel/product/batchdetailnew'
CUSTOMER_LIST = '/yonbip/digitalModel/merchant/newlist'
CUSTOMER_DETAIL = '/yonbip/PFC/merchant/v1/batchDetail'
CLASS_LIST = '/yonbip/digitalModel/custcategory/newtree'
CUSTOMER_CREATE = '/yonbip/digitalModel/merchant/idempotent/newinsert'
ORDER_CREATE = '/yonbip/sd/voucherorder/singleSave'
ORDER_LIST = '/yonbip/sd/voucherorder/list'
ORDER_DETAIL = '/yonbip/sd/voucherorder/detail'
STAFF_DETAIL = '/yonbip/digitalModel/staff/detail'
DEPARTMENT_DETAIL = '/yonbip/digitalModel/admindept/detail'
ORG_DETAIL = '/yonbip/digitalModel/orgunit/detail'
GET_PATHS = {ORDER_DETAIL, STAFF_DETAIL, DEPARTMENT_DETAIL, ORG_DETAIL}
PATHS = {PRODUCT_LIST, PRODUCT_DETAIL, CUSTOMER_LIST, CUSTOMER_DETAIL, CLASS_LIST,
         CUSTOMER_CREATE, ORDER_CREATE, ORDER_LIST} | GET_PATHS


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def label(value):
    if isinstance(value, dict):
        return next((value[k] for k in ('englishName', 'en_US', 'simplifiedName', 'zh_CN') if value.get(k)), '')
    return str(value or '')


def stopped(data, env):
    value = data.get('stopstatus', data.get('stopStatus'))
    if value not in (False, 0, '0'):
        raise UserError(env._('ERP record is stopped or its enabled status could not be verified.'))


class Client(models.AbstractModel):
    _name = 'b2b.yonyou.client'
    _description = 'Yonyou C4 Private Client'

    @api.model
    def _connection(self):
        config = self.env.ref('b2b_yonyou.connection').sudo()
        if not config.enabled:
            raise UserError(_('Enable Yonyou C4 mapping in configuration first.'))
        return config

    @api.model
    def _http(self, url, body=None):
        req = request.Request(url, method='POST' if body is not None else 'GET',
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with request.build_opener(NoRedirect()).open(req, timeout=20) as response:
                raw = response.read(5_000_001)
            if len(raw) > 5_000_000:
                raise UserError(_('ERP response exceeds the safe size limit.'))
            result = json.loads(raw)  # Python preserves integer IDs exactly.
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except error.HTTPError as exc:
            raise UserError(_('ERP HTTP %(status)s. Check authorization for this API. No write was retried.', status=exc.code)) from None
        except (error.URLError, TimeoutError, OSError):
            raise UserError(_('ERP connection failed or timed out. The result may be unknown; retry uses the same customer code and first checks ERP.')) from None
        except (ValueError, UnicodeError):
            raise UserError(_('ERP returned an invalid response. No write was retried.')) from None

    @api.model
    def _token(self, config):
        if config.token and config.token_expiry > time.time() + 300:
            return config.token
        if not config.app_key or not config.app_secret:
            raise UserError(_('A Settings administrator must configure the C4 App Key and App Secret.'))
        params = {'appKey': config.app_key, 'timestamp': str(int(time.time() * 1000))}
        message = ''.join(k + params[k] for k in sorted(params))
        params['signature'] = base64.b64encode(hmac.new(config.app_secret.encode(), message.encode(), hashlib.sha256).digest()).decode()
        result = self._http(AUTH + '?' + parse.urlencode(params))
        data = result.get('data') or {}
        if str(result.get('code')) != '00000' or not isinstance(data, dict) or not data.get('access_token'):
            raise UserError(_('C4 authentication failed. Check credentials, authorization and server time.'))
        if not re.fullmatch(r'[0-9]+', str(data.get('expire'))) or int(data['expire']) <= 0:
            raise UserError(_('C4 did not return a valid token lifetime.'))
        config.with_context(_yonyou_write=WRITE_TOKEN).write({
            'token': data['access_token'], 'token_expiry': time.time() + int(data['expire'])})
        return data['access_token']

    @api.model
    def _call(self, path, payload):
        if path not in PATHS:
            raise UserError(_('Unsupported ERP mapping endpoint.'))
        config = self._connection()
        if path == CUSTOMER_CREATE:
            data = payload.get('data') or {}
            if data.get('createOrgCode') != '999' or data.get('merchantApplyRanges') != [{'orgIdCode': '999'}]:
                raise UserError(_('This release only creates ERP customers in test organization 999.'))
        if path == ORDER_CREATE:
            data = payload.get('data') or {}
            if not config.order_sync:
                raise UserError(_('ERP order submission is disabled.'))
            # Production rollout is a separate, explicit operation. Never let
            # a company/configuration change write test orders to a live org.
            if (not config.test_mode or data.get('salesOrgId') != '999'
                    or data.get('settlementOrgId') != '999'
                    or not data.get('orderDetails')
                    or any(line.get('stockOrgId') != '999' or line.get('settlementOrgId') != '999'
                           for line in data['orderDetails'])):
                raise UserError(_('This release only creates ERP orders in test organization 999.'))
        token = self._token(config)
        params = {'access_token': token}
        if path in GET_PATHS:
            params.update(payload)
        result = self._http(GATEWAY + path + '?' + parse.urlencode(params),
                            None if path in GET_PATHS else payload)
        # C4 customer-list API reports an empty search as a business status.
        # Match only this endpoint/status/message; permission failures must not
        # be mistaken for permission to create a new customer.
        if (path == CUSTOMER_LIST and str(result.get('code')) == '118001'
                and result.get('message') == '根据条件查询结果为空'):
            return []
        if str(result.get('code')) != '200':
            code = str(result.get('code', 'unknown'))
            safe_code = code if re.fullmatch(r'[0-9]{1,12}', code) else 'unknown'
            # Do not expose raw provider text; it can echo credentials or personal data.
            raise UserError(_('ERP rejected %(path)s (code %(code)s). Check required fields, organization and API authorization.', path=path, code=safe_code))
        return result.get('data')

    @api.model
    def _search(self, path, code):
        code = (code or '').strip()
        if not code:
            raise UserError(_('Enter an ERP code before clicking Verify.'))
        found = {}
        for page in range(1, 101):
            payload = {'pageIndex': page, 'pageSize': 100,
                       'productCode' if path == PRODUCT_LIST else 'code': code}
            if path == CUSTOMER_LIST:
                payload['filterPotential'] = False
            data = self._call(path, payload)
            records = data.get('recordList') if isinstance(data, dict) else data
            if not isinstance(records, list):
                raise UserError(_('ERP returned an unexpected search structure.'))
            pending = list(records)
            while pending:
                row = pending.pop()
                if not isinstance(row, dict):
                    raise UserError(_('ERP returned an invalid search record.'))
                if row.get('code') == code and row.get('id'):
                    found[str(row['id'])] = row
                pending.extend(row.get('children') or [])
            if isinstance(data, dict) and data.get('pageCount') is not None:
                complete = page >= int(data['pageCount'])
            else:
                complete = len(records) < 100
            if complete:
                break
        else:
            raise UserError(_('Too many ERP search results. Refine the code before binding.'))
        if len(found) > 1:
            raise UserError(_('More than one ERP record has this exact code. Resolve duplicates before binding.'))
        return next(iter(found.values()), None)

    @api.model
    def _order_by_code(self, code):
        """The list endpoint returns one row per order LINE, not per order."""
        found = {}
        for page in range(1, 101):
            data = self._call(ORDER_LIST, {'pageIndex': page, 'pageSize': 100, 'code': code})
            if not isinstance(data, dict) or not isinstance(data.get('recordList'), list):
                raise UserError(_('Cannot verify whether this ERP order already exists.'))
            for row in data['recordList']:
                if not isinstance(row, dict):
                    raise UserError(_('Unexpected ERP order lookup record.'))
                if row.get('code') == code:
                    if not row.get('id'):
                        raise UserError(_('ERP order lookup is missing its document ID.'))
                    found[str(row['id'])] = row
            if data.get('pageCount') is None or not str(data['pageCount']).isdigit():
                raise UserError(_('ERP order lookup is missing pagination information.'))
            if page >= int(data['pageCount']):
                break
        else:
            raise UserError(_('ERP order lookup exceeded the safe page limit. No order was created.'))
        if len(found) > 1:
            raise UserError(_('Multiple ERP documents have this order number. Review manually; no new order was created.'))
        return next(iter(found), None)

    @api.model
    def _class(self, code):
        row = self._search(CLASS_LIST, code)
        if not row or row.get('isEnabled') is not True:
            raise UserError(_('ERP customer category was not found or is not enabled.'))
        return {'id': str(row['id']), 'code': code, 'name': label(row.get('name'))}

    @api.model
    def _principal(self, code, department, org):
        """Validate an enabled salesperson's current main/part-time assignment.

        Staff details include organization/department IDs, not their codes.
        Resolve those IDs through the documented detail APIs; never compare
        names or store the employee's unrelated personal/bank information.
        """
        code, department = (code or '').strip(), (department or '').strip()
        if not code:
            raise UserError(_('Enter an ERP salesperson code, then click Verify Salesperson.'))
        staff = self._call(STAFF_DETAIL, {'code': code})
        if (not isinstance(staff, dict) or staff.get('code') != code or not staff.get('id')
                or str(staff.get('enable')) != '1' or str(staff.get('biz_man_tag')) not in ('1', 'True')):
            raise UserError(_('The ERP employee was not found, is disabled, or is not marked as a salesperson.'))
        today = fields.Date.to_string(fields.Date.context_today(self.with_context(tz='Asia/Shanghai')))
        jobs = (staff.get('mainJobList') or []) + (staff.get('ptJobList') or [])
        if len(jobs) > 50:
            raise UserError(_('Too many ERP employee assignments. Review this employee in ERP first.'))
        orgs, departments, matches = {}, {}, {}
        for job in jobs:
            if (str(job.get('dr')) != '0' or not job.get('org_id') or not job.get('dept_id')
                    or str(job.get('staff_id')) != str(staff['id'])):
                continue
            if (job.get('begindate') and str(job['begindate'])[:10] > today
                    or job.get('enddate') and str(job['enddate'])[:10] < today):
                continue
            org_id, dept_id = str(job['org_id']), str(job['dept_id'])
            if org_id not in orgs:
                orgs[org_id] = self._call(ORG_DETAIL, {'id': org_id})
            unit = orgs[org_id]
            if (not isinstance(unit, dict) or str(unit.get('id')) != org_id
                    or unit.get('code') != org or str(unit.get('enable')) != '1'):
                continue
            if dept_id not in departments:
                departments[dept_id] = self._call(DEPARTMENT_DETAIL, {'id': dept_id})
            dept = departments[dept_id]
            if (not isinstance(dept, dict) or str(dept.get('id')) != dept_id
                    or str(dept.get('enable')) != '1' or str(dept.get('dr')) != '0'
                    or str(dept.get('parentorgid')) != org_id or not dept.get('code')):
                continue
            if department and dept['code'] != department:
                continue
            matches[dept_id] = dept
        if len(matches) != 1:
            raise UserError(_('No unique active salesperson/department assignment was verified for ERP organization %(org)s. Check the department code and employee assignments in ERP; no customer was created.', org=org))
        dept = next(iter(matches.values()))
        return {'salesperson': code, 'salesperson_id': str(staff['id']), 'salesperson_name': label(staff.get('name')),
                'department': dept['code'], 'department_id': str(dept['id']),
                'department_name': label(dept.get('name')), 'org': org}

    @api.model
    def _product(self, code, org):
        row = self._search(PRODUCT_LIST, code)
        if not row:
            raise UserError(_('No exact ERP material code was found.'))
        records = self._call(PRODUCT_DETAIL, [{'productCode': code, 'orgCode': org}])
        matches = [r for r in records or [] if r.get('code') == code and str(r.get('id')) == str(row['id'])]
        if len(matches) != 1:
            raise UserError(_('ERP material could not be verified in the selected organization.'))
        product = matches[0]
        detail = product.get('detail') or {}
        ranges = [r for r in product.get('productOrges', []) if r.get('orgCode') == org and r.get('isApplied') is True]
        if len(ranges) != 1 or str(detail.get('orgId')) != str(ranges[0].get('orgId')):
            raise UserError(_('Material is not applied to this ERP organization. Ask ERP staff to assign it first.'))
        stopped(detail, self.env)
        if product.get('deleted') is not False or detail.get('canSale') is not True:
            raise UserError(_('ERP material is deleted or not available for sale.'))
        if product.get('hasSpecs') or not product.get('defaultSKUId'):
            raise UserError(_('This ERP material requires a specific SKU. Use a distinct material for the variant; multi-SKU selection needs separate validation.'))
        units = [product.get('unitCode'), detail.get('batchUnitCode'), detail.get('batchPriceUnitCode')]
        if not all(units) or len(set(units)) != 1 or product.get('enableAssistUnit'):
            raise UserError(_('ERP material uses missing or different units. Confirm the unit conversion before binding; it is not assumed to be 1.'))
        return {'id': str(product['id']), 'code': code, 'name': label(product.get('name')),
                'sku_id': str(product['defaultSKUId']), 'unit_code': units[0],
                'unit_name': product.get('unitName'), 'org': org}

    @api.model
    def _customer(self, code, org):
        row = self._search(CUSTOMER_LIST, code)
        if not row:
            raise UserError(_('No exact ERP customer code was found.'))
        stopped(row, self.env)
        records = self._call(CUSTOMER_DETAIL, [{'code': code, 'belongOrgCode': org}])
        matches = [r for r in records or [] if r.get('code') == code and str(r.get('id')) == str(row['id'])]
        if len(matches) != 1:
            raise UserError(_('Customer details were not found in this ERP using organization.'))
        customer = matches[0]
        detail = customer.get('merchantAppliedDetail') or {}
        if detail.get('belongOrgId___code') != org:
            raise UserError(_('Customer exists but is not available in this using organization. Ask ERP staff to assign it; do not create a duplicate.'))
        stopped(detail, self.env)
        currency = detail.get('transactionCurrencyId___code')
        if not currency and detail.get('transactionCurrencyId'):
            raise UserError(_('ERP customer currency has an ID but no code. Verify its currency configuration.'))
        currency = str(currency or 'USD').strip().upper()
        if currency == 'RMB':
            currency = 'CNY'
        all_ranges = customer.get('merchantApplyRanges') or []
        ranges = [r for r in all_ranges
                  if r.get('orgId___code') == org]
        range_ids = {str(r['id']) for r in ranges if r.get('id')}
        principals = [p for p in customer.get('principals', [])
                      if str(p.get('merchantApplyRangeId')) in range_ids]
        for r in ranges:
            principals.extend(r.get('principals') or [])
        if not all_ranges:
            # C4 also returns organization-scoped details without the range
            # table (e.g. globally managed customers). The requested using
            # organization was verified above against merchantAppliedDetail.
            # In that shape principals belong to this detail, not createOrg.
            principals = customer.get('principals') or []
            principal_ranges = {str(p['merchantApplyRangeId']) for p in principals
                                if p.get('merchantApplyRangeId')}
            if len(principal_ranges) > 1:
                principals = []  # Mixed scopes cannot be resolved safely.
        # Explicit contradictory ownership must never be accepted, including
        # in the scoped-detail variant without a range table.
        principals = [p for p in principals
                      if (not p.get('merchantId') or str(p['merchantId']) == str(customer['id']))
                      and (not p.get('merchantId___code') or p['merchantId___code'] == code)
                      and (not p.get('belongOrgId___code') or p['belongOrgId___code'] == org)
                      and (not p.get('orgId___code') or p['orgId___code'] == org)]
        # De-duplicate nested / top-level representations of the same row.
        defaults = {str(p.get('id') or (p.get('professSalesman'), p.get('specialManagementDep'))): p
                    for p in principals if p.get('isDefault') is True}
        principal = next(iter(defaults.values())) if len(defaults) == 1 else {}
        invoices = [p for p in customer.get('invoicingCustomerss', [])
                    if str(p.get('merchantApplyRangeId')) in range_ids and p.get('isDefault') is True]
        for r in ranges:
            invoices.extend(p for p in r.get('invoicingCustomerss', []) if p.get('isDefault') is True)
        invoice_codes = {p.get('invoicingCustomersId___code') for p in invoices}
        invoice = next(iter(invoice_codes)) if len(invoice_codes) == 1 else (
            customer.get('invoicingCustomers___code') or code) if not invoices else None
        return {'id': str(customer['id']), 'code': code, 'name': label(customer.get('name')),
                'class_code': customer.get('customerClass___code') or row.get('customerClassCode'),
                'class_name': customer.get('customerClass___name') or row.get('customerClassName'),
                'management_org': customer.get('createOrg___code'), 'org': org,
                'currency': currency, 'currency_defaulted': not bool(detail.get('transactionCurrencyId___code')),
                'country': customer.get('country___code'),
                'salesperson': principal.get('professSalesman___code'),
                'salesperson_name': label(principal.get('professSalesman___name')),
                'department': principal.get('specialManagementDep___code'),
                'department_name': label(principal.get('specialManagementDep___name')),
                'invoice_customer': invoice}
