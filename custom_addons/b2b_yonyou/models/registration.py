import hashlib
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.addons.phone_validation.tools import phone_validation
from .config import MANAGER, check_role, notification
from .client import CUSTOMER_LIST, CUSTOMER_CREATE
from .principal import PRINCIPAL_INPUTS


class Registration(models.Model):
    _name = 'b2b.registration.application'
    _inherit = ['b2b.registration.application', 'b2b.yonyou.mapping.mixin', 'b2b.yonyou.principal.mixin']
    _erp_inputs = frozenset({'yonyou_brand_id', 'yonyou_class_code', 'yonyou_code'}) | PRINCIPAL_INPUTS
    yonyou_brand_id = fields.Many2one('b2b.product.brand', string='Account Brand', groups=MANAGER)
    yonyou_pending_company_id = fields.Many2one('res.partner', string='ERP Linked Company', readonly=True, copy=False, groups=MANAGER)
    yonyou_create_payload = fields.Json(readonly=True, copy=False, groups=MANAGER)
    yonyou_code = fields.Char(string='ERP Customer Code (blank = generate for new company)', copy=False, groups=MANAGER)

    def _erp_company(self):
        return self.yonyou_brand_id.b2b_selling_company_id

    @api.onchange('yonyou_brand_id')
    def _onchange_yonyou_brand(self):
        self.yonyou_class_code = self.yonyou_brand_id.yonyou_class_code
        if not self._principal_locked():
            self.yonyou_salesperson = self.yonyou_brand_id.yonyou_salesperson
            self.yonyou_department = self.yonyou_brand_id.yonyou_department

    @api.model_create_multi
    def create(self, vals_list):
        values = []
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('yonyou_brand_id'):
                brand = self.env['b2b.product.brand'].browse(vals['yonyou_brand_id'])
                vals.setdefault('yonyou_salesperson', brand.yonyou_salesperson)
                vals.setdefault('yonyou_department', brand.yonyou_department)
            values.append(vals)
        return super().create(values)

    def write(self, vals):
        if vals.get('yonyou_brand_id') and not PRINCIPAL_INPUTS & vals.keys():
            brand = self.env['b2b.product.brand'].browse(vals['yonyou_brand_id'])
            vals = dict(vals, yonyou_salesperson=brand.yonyou_salesperson, yonyou_department=brand.yonyou_department)
        return super().write(vals)

    def _principal_locked(self):
        return self.state == 'approved' or bool(self.yonyou_create_payload)

    @api.depends('yonyou_salesperson', 'yonyou_department', 'yonyou_principal_snapshot', 'yonyou_brand_id', 'yonyou_brand_id.b2b_selling_company_id')
    def _compute_principal(self):
        return super()._compute_principal()

    def action_yonyou_verify(self):
        raise UserError(_('For an existing company, open its Partner Hub tab and verify the ERP Customer Code there.'))

    def _resolve_company(self):
        if (self.company_resolution == 'create' and self.yonyou_pending_company_id
                and self._erp_connection().registration_sync):
            return self.yonyou_pending_company_id
        return super()._resolve_company()

    def _erp_create_values(self, config, code, key):
        if not self.yonyou_salesperson or not self.yonyou_department:
            raise UserError(_('Enter the ERP salesperson on this registration and click Verify Salesperson before approval.'))
        name = self.company_name.strip()
        mobile = phone_validation.phone_parse(self.mobile, self.country_id.code)
        if not mobile:
            raise UserError(_('Mobile number parsing is unavailable. Contact the administrator.'))
        formatted = phone_validation.phone_format(self.mobile, self.country_id.code,
            self.country_id.phone_code, force_format='E164')
        dial = '+' + str(mobile.country_code)
        return {'data': {
            'resubmitCheckKey': key, 'code': code,
            'name': {'simplifiedName': name, 'englishName': name},
            'shortname': {'simplifiedName': name[:100], 'englishName': name[:100]},
            'enterpriseName': name, 'createOrgCode': config.management_org,
            'transTypeCode': config.transaction_type, 'countryCode': self.country_id.code,
            'retailInvestors': False, 'internalOrg': False, 'enterpriseNature': 0,
            'taxPayingCategories': int(config.tax_category), 'customerClassCode': self.yonyou_class_code,
            'email': self.business_email, 'contactName': self.full_name,
            'contactTel': self.company_phone or self.mobile,
            'merchantContactInfos': [{'fullName': {'simplifiedName': self.full_name, 'englishName': self.full_name},
                'areaCodeMobile': dial + '-' + formatted[len(dial):],
                'email': self.business_email, 'isDefault': True}],
            **({'website': self.company_website} if self.company_website else {}),
            'merchantApplyRanges': [{'orgIdCode': config._org(self._erp_company())}],
            'merchantAppliedDetail': {'searchCode': code, 'exchangeRateTypeCode': config.exchange_rate_type,
                'payWay': config.pay_way, 'priceMarking': config.price_marking, 'isTradeCustomers': '0'},
            'principals': [{'specialManagementDepCode': self.yonyou_department,
                'professSalesmanCode': self.yonyou_salesperson, 'isDefault': True}],
        }}

    def _erp_sync_customer(self):
        client = self.env['b2b.yonyou.client']
        config = client._connection()
        if self.company_resolution == 'existing':
            company = self.company_id
            if not company:
                raise UserError(_('Select the existing customer company first.'))
            check_role(company)
            company._erp_verify()  # Fresh query; no ERP write or silent reclassification.
            return company
        if self.company_resolution != 'create':
            raise UserError(_('Choose the company resolution first.'))
        brand = self.yonyou_brand_id
        if not brand or not brand.b2b_selling_company_id:
            raise UserError(_('Select an account brand linked to a selling company.'))
        if not self.env.su and brand.b2b_selling_company_id not in self.env.user.company_ids:
            raise AccessError(_('You do not have access to the selected selling company.'))
        if not config.test_mode or config.management_org != '999':
            raise UserError(_('Customer creation is restricted to test organization 999 in this release.'))
        category = self.yonyou_class_snapshot or {}
        if category.get('code') != self.yonyou_class_code or category.get('revision') != config.revision:
            raise UserError(_('Verify the ERP customer category before approving this registration.'))
        database_uuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        if not database_uuid:
            raise UserError(_('Database identity is missing; contact the administrator.'))
        key = hashlib.sha256(('%s:registration:%s' % (database_uuid, self.id)).encode()).hexdigest()[:32]
        code = self.yonyou_code or (config.code_prefix + key[:16].upper())
        # Existing pending requests retain the original pair, including requests
        # created before this field was introduced. Never replace it on retry.
        stored = self.yonyou_create_payload
        if not self.yonyou_salesperson and not self.yonyou_department:
            principal = (stored or {}).get('data', {}).get('principals', [{}])[0]
            self._erp_store({'yonyou_salesperson': principal.get('professSalesmanCode') or brand.yonyou_salesperson,
                'yonyou_department': principal.get('specialManagementDepCode') or brand.yonyou_department})
        if not stored:
            self._verify_principal()  # Fresh ERP check, not a trusted browser badge.
        payload = self._erp_create_values(config, code, key)
        if stored and stored != payload:
            raise UserError(_('A previous ERP creation attempt uses different reviewed data. Query and resolve that customer before changing its creation request; no duplicate was created.'))
        existing = client._search(CUSTOMER_LIST, code)
        if existing and not stored:
            raise UserError(_('This ERP code already exists. Choose Link Existing Company and verify its customer mapping instead.'))
        self._erp_store({'yonyou_code': code, 'yonyou_create_payload': payload})
        if not existing:
            if stored:
                self._verify_principal()
            client._call(CUSTOMER_CREATE, payload)
        actual = client._customer(code, '999')
        if actual['management_org'] != '999' or actual['class_code'] != self.yonyou_class_code or actual['name'] != self.company_name.strip():
            raise UserError(_('ERP customer was found but does not match the reviewed name, category or test organization. Resolve it before approval.'))
        if actual.get('salesperson') != self.yonyou_salesperson or actual.get('department') != self.yonyou_department:
            raise UserError(_('ERP customer exists but its default salesperson or department differs from the approved request. Review this customer in ERP; do not create another.'))
        company = self.yonyou_pending_company_id
        if not company:
            company = super()._resolve_company()
            self._erp_store({'yonyou_pending_company_id': company.id})
        company.write({'b2b_account_brand_id': brand.id, 'yonyou_class_code': self.yonyou_class_code,
                       'yonyou_code': code, 'email': self.business_email})
        company._erp_verify()
        self._erp_store({'yonyou_result': _('ERP customer verified: %s', code)})
        return company

    def action_approve(self):
        self.ensure_one()
        self._check_manager()
        self.check_access('write')
        config = self._erp_connection()
        if not config.registration_sync:
            return super().action_approve()
        # Serialize both link-existing and create-new approval paths.
        self.env.cr.execute('SELECT id FROM b2b_registration_application WHERE id=%s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if self.state not in ('pending', 'rejected') or not self.email_verified_at:
            raise UserError(_('Only email-verified registrations under review can be approved.'))
        if not all((self.full_name, self.job_title, self.company_name, self.country_id,
                    self.business_email, self.mobile, self.customer_type_id)):
            raise UserError(_('Complete all required registration fields before approval.'))
        try:
            company = self._erp_sync_customer()
            self._erp_store({'yonyou_pending_company_id': company.id})
            # If native approval fails, preserve the remote reference but not partial activation.
            with self.env.cr.savepoint():
                return super().action_approve()
        except UserError as exc:
            self._erp_store({'yonyou_result': str(exc)})
            return notification(str(exc), True)
