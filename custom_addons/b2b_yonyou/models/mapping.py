import hashlib
import json
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from .config import INTERNAL, MANAGER, WRITE_TOKEN, check_role, notification
from .principal import PRINCIPAL_INPUTS


class Mapping(models.AbstractModel):
    _name = 'b2b.yonyou.mapping.mixin'
    _description = 'Server Verified ERP Mapping'
    _erp_inputs = frozenset({'yonyou_code', 'yonyou_class_code'})
    _erp_product = False

    yonyou_code = fields.Char(string='ERP Code', copy=False, groups=INTERNAL)
    yonyou_snapshot = fields.Json(copy=False, readonly=True, groups=INTERNAL)
    yonyou_checked_at = fields.Datetime(string='Last ERP Verification', copy=False, readonly=True, groups=INTERNAL)
    yonyou_result = fields.Char(string='ERP Verification Result', copy=False, readonly=True, groups=INTERNAL)
    yonyou_status = fields.Selection([('unverified', 'Not Verified'), ('verified', 'Verified'),
        ('stale', 'Changed — Verify Again')], string='ERP Mapping Status', compute='_compute_yonyou_status', groups=INTERNAL)
    yonyou_class_code = fields.Char(string='ERP Customer Category Code', copy=False, groups=MANAGER)
    yonyou_class_snapshot = fields.Json(copy=False, readonly=True, groups=MANAGER)
    yonyou_class_result = fields.Char(string='ERP Customer Category', readonly=True, copy=False, groups=MANAGER)

    def _erp_connection(self):
        return self.env.ref('b2b_yonyou.connection').sudo()

    def _erp_company(self):
        return self.env['res.company']

    def _erp_fingerprint(self):
        self.ensure_one()
        config = self._erp_connection()
        data = [self.yonyou_code, config.revision, config._org(self._erp_company())]
        if not self._erp_product:
            data += [self.yonyou_class_code, self._erp_company().id]
        return hashlib.sha256(json.dumps(data).encode()).hexdigest()

    @api.depends('yonyou_code', 'yonyou_snapshot', 'yonyou_class_code')
    def _compute_yonyou_status(self):
        for rec in self:
            snapshot = rec.yonyou_snapshot or {}
            rec.yonyou_status = ('verified' if snapshot.get('fingerprint') == rec._erp_fingerprint()
                else 'stale' if snapshot else 'unverified')

    def _erp_guard(self, vals):
        keys = {k for k in vals if k.startswith('yonyou_')}
        if not keys or self.env.context.get('_yonyou_write') is WRITE_TOKEN:
            return
        check_role(self, self._erp_product)
        if PRINCIPAL_INPUTS & keys and hasattr(self, '_principal_locked'):
            if any(rec._principal_locked() for rec in self):
                raise UserError(_('The ERP salesperson assignment is locked. Change an existing customer in ERP, then use Verify & Refresh. A pending creation request cannot be changed.'))
        if keys - self._erp_inputs:
            raise AccessError(_('ERP verification results are server-managed. Use Verify.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._erp_guard(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._erp_guard(vals)
        if 'yonyou_class_code' in vals and self.env.context.get('_yonyou_write') is not WRITE_TOKEN:
            vals = dict(vals, yonyou_class_snapshot=False, yonyou_class_result=False)
        return super().write(vals)

    def _erp_store(self, vals):
        return self.with_context(_yonyou_write=WRITE_TOKEN).write(vals)

    def _erp_class(self):
        self.ensure_one()
        code = (self.yonyou_class_code or '').strip()
        result = self.env['b2b.yonyou.client']._class(code)
        result['revision'] = self._erp_connection().revision
        self._erp_store({'yonyou_class_code': code, 'yonyou_class_snapshot': result,
                         'yonyou_class_result': '%s — %s' % (code, result['name'])})
        return result

    def action_yonyou_verify_class(self):
        self.ensure_one()
        check_role(self)
        try:
            result = self._erp_class()
        except UserError as exc:
            self._erp_store({'yonyou_class_snapshot': False, 'yonyou_class_result': str(exc)})
            return notification(str(exc), True)
        return notification(_('Category verified: %s', result['name']))

    def _erp_verify(self):
        self.ensure_one()
        code = (self.yonyou_code or '').strip()
        client = self.env['b2b.yonyou.client']
        org = self._erp_connection()._org(self._erp_company())
        result = client._product(code, org) if self._erp_product else client._customer(code, org)
        if self._erp_product:
            result['odoo_uom'] = self.uom_id.id
        self._erp_validate_result(result)
        vals = {'yonyou_code': code}
        if not self._erp_product:
            actual_class = result.get('class_code')
            if self.yonyou_class_code and self.yonyou_class_code != actual_class:
                raise UserError(_('ERP customer category is %(actual)s, not %(selected)s. Confirm the correct customer/category; ERP was not modified.', actual=actual_class or '?', selected=self.yonyou_class_code))
            vals['yonyou_class_code'] = actual_class
            vals['b2b_erp_customer_id'] = result['id']
        self._erp_store(vals)
        result['fingerprint'] = self._erp_fingerprint()
        self._erp_store({'yonyou_snapshot': result, 'yonyou_checked_at': fields.Datetime.now(),
                        'yonyou_result': '%s — %s | ERP organization %s' % (code, result['name'], org)})
        return result

    def _erp_validate_result(self, result):
        """Validate before persisting any successful result."""
        return None

    def action_yonyou_verify(self):
        self.ensure_one()
        check_role(self, self._erp_product)
        try:
            self._erp_verify()
        except UserError as exc:
            vals = {'yonyou_snapshot': False, 'yonyou_checked_at': False, 'yonyou_result': str(exc)}
            if self._name == 'res.partner':
                vals['b2b_erp_customer_id'] = False
                vals['yonyou_bound_id'] = False
            self._erp_store(vals)
            return notification(str(exc), True)
        return notification(_('Verified against ERP. The mapping has been saved using the native form.'))


class Product(models.Model):
    _name = 'product.product'
    _inherit = ['product.product', 'b2b.yonyou.mapping.mixin']
    _erp_product = True
    _erp_inputs = Mapping._erp_inputs | {'yonyou_company_id'}
    yonyou_code = fields.Char(string='ERP Material Code', copy=False, groups=INTERNAL)
    yonyou_company_id = fields.Many2one('res.company', string='Verify for Selling Company',
        default=lambda self: self.env.company, groups=INTERNAL, copy=False)

    def _erp_company(self):
        company = self.yonyou_company_id
        if company and not self.env.su and company not in self.env.user.company_ids:
            raise AccessError(_('You do not have access to the selected selling company.'))
        return company

    @api.depends('yonyou_company_id', 'yonyou_code', 'yonyou_snapshot')
    def _compute_yonyou_status(self):
        return super()._compute_yonyou_status()


class Template(models.Model):
    _inherit = 'product.template'
    yonyou_code = fields.Char(related='product_variant_id.yonyou_code', depends=['product_variant_ids.yonyou_code'], readonly=False, groups=INTERNAL)
    yonyou_company_id = fields.Many2one(related='product_variant_id.yonyou_company_id', depends=['product_variant_ids.yonyou_company_id'], readonly=False, groups=INTERNAL)
    yonyou_result = fields.Char(related='product_variant_id.yonyou_result', depends=['product_variant_ids.yonyou_result'], groups=INTERNAL)
    yonyou_status = fields.Selection(related='product_variant_id.yonyou_status', depends=['product_variant_ids.yonyou_status'], groups=INTERNAL)
    yonyou_checked_at = fields.Datetime(related='product_variant_id.yonyou_checked_at', depends=['product_variant_ids.yonyou_checked_at'], groups=INTERNAL)

    def _get_related_fields_variant_template(self):
        # Reuse native restoration of template values after its first variant
        # is created (the same mechanism used for barcode/default_code).
        return super()._get_related_fields_variant_template() + ['yonyou_code', 'yonyou_company_id']

    def action_yonyou_verify(self):
        self.ensure_one()
        check_role(self, True)
        if len(self.product_variant_ids) != 1:
            raise UserError(_('Open each product variant to maintain its own ERP material mapping.'))
        return self.product_variant_id.action_yonyou_verify()

    def write(self, vals):
        if {'yonyou_code', 'yonyou_company_id'} & vals.keys():
            check_role(self, True)
            if any(len(t.product_variant_ids) != 1 for t in self):
                raise UserError(_('Maintain ERP mappings on each variant, not on a multi-variant template.'))
        return super().write(vals)


class Partner(models.Model):
    _name = 'res.partner'
    _inherit = ['res.partner', 'b2b.yonyou.mapping.mixin', 'b2b.yonyou.principal.mixin']
    yonyou_code = fields.Char(string='ERP Customer Code', copy=False, groups=MANAGER)
    yonyou_contact_code = fields.Char(string='Company ERP Customer Code', related='commercial_partner_id.yonyou_code', groups=MANAGER)
    yonyou_bound_id = fields.Char(copy=False, readonly=True, groups=MANAGER, index=True)
    yonyou_order_currency = fields.Char(string='ERP Order Currency', compute='_compute_order_defaults', groups=MANAGER)
    yonyou_fiscal_position_id = fields.Many2one('account.fiscal.position',
        string='Customer Tax Rule (Selling Company)', compute='_compute_order_defaults',
        inverse='_inverse_order_fiscal_position', groups=MANAGER)
    _erp_inputs = Mapping._erp_inputs | {'yonyou_fiscal_position_id'} | PRINCIPAL_INPUTS
    _erp_unique = models.Constraint('UNIQUE(yonyou_bound_id)', 'This ERP customer is already bound to another Odoo company. Use that company instead.')

    @api.depends('yonyou_snapshot', 'b2b_selling_company_id', 'property_account_position_id')
    def _compute_order_defaults(self):
        for partner in self:
            company = partner.b2b_selling_company_id
            partner.yonyou_order_currency = (partner.yonyou_snapshot or {}).get('currency')
            partner.yonyou_fiscal_position_id = partner.with_company(company).property_account_position_id if company else False

    def _inverse_order_fiscal_position(self):
        for partner in self:
            check_role(partner)
            company = partner._erp_company()
            rule = partner.yonyou_fiscal_position_id
            if rule and rule.company_id != company:
                raise ValidationError(_('Select a native fiscal position belonging to the customer selling company.'))
            partner.with_company(company).property_account_position_id = rule

    def _erp_company(self):
        company = self.b2b_selling_company_id
        if not company:
            raise UserError(_('Assign the customer selling company before verifying ERP.'))
        if not self.env.su and company not in self.env.user.company_ids:
            raise AccessError(_('You do not have access to this customer selling company.'))
        return company

    def _erp_fingerprint(self):
        if not self.b2b_selling_company_id:
            return ''
        return super()._erp_fingerprint()

    @api.depends('yonyou_code', 'yonyou_class_code', 'yonyou_snapshot', 'b2b_selling_company_id')
    def _compute_yonyou_status(self):
        return super()._compute_yonyou_status()

    def _erp_verify(self):
        if not self.is_company or self.commercial_partner_id != self:
            raise UserError(_('Maintain the ERP binding on the customer company, not its contact.'))
        result = super()._erp_verify()
        self._erp_store({'yonyou_bound_id': result['id']})
        self._store_principal(result)
        return result

    def _principal_locked(self):
        return bool(self.yonyou_bound_id)

    def _principal_company(self):
        return self.b2b_selling_company_id

    @api.depends('yonyou_salesperson', 'yonyou_department', 'yonyou_principal_snapshot', 'b2b_selling_company_id')
    def _compute_principal(self):
        return super()._compute_principal()

    def _erp_validate_result(self, result):
        duplicate = self.sudo().search([('id', '!=', self.id), ('yonyou_bound_id', '=', result['id'])], limit=1)
        if duplicate:
            raise UserError(_('This ERP customer is already bound to another Odoo company. Link that company instead.'))

    @api.onchange('b2b_account_brand_id')
    def _onchange_erp_brand(self):
        if self.b2b_account_brand_id and not self.yonyou_bound_id:
            self.yonyou_class_code = self.b2b_account_brand_id.yonyou_class_code
            self.yonyou_salesperson = self.b2b_account_brand_id.yonyou_salesperson
            self.yonyou_department = self.b2b_account_brand_id.yonyou_department

    @api.constrains('yonyou_code', 'yonyou_class_code', 'yonyou_salesperson', 'yonyou_department', 'parent_id', 'is_company')
    def _check_mapping_owner(self):
        if any((r.yonyou_code or r.yonyou_class_code or r.yonyou_salesperson or r.yonyou_department)
               and (not r.is_company or r.commercial_partner_id != r) for r in self):
            raise ValidationError(_('Maintain ERP customer and category codes on the customer company only.'))

    def write(self, vals):
        vals = dict(vals)
        if vals.get('b2b_account_brand_id') and 'yonyou_class_code' not in vals and not any(self.mapped('yonyou_bound_id')):
            vals['yonyou_class_code'] = self.env['b2b.product.brand'].browse(vals['b2b_account_brand_id']).yonyou_class_code
        if self.env.context.get('_yonyou_write') is not WRITE_TOKEN:
            if vals.get('b2b_erp_customer_id') and any(self.mapped('yonyou_code')):
                raise AccessError(_('Use the ERP Customer Code and Verify button instead of entering an ERP ID manually.'))
            if {'yonyou_code', 'b2b_selling_company_id', 'yonyou_class_code'} & vals.keys():
                self._erp_guard({k: v for k, v in vals.items() if k not in ('yonyou_bound_id', 'b2b_erp_customer_id')})
                vals.update(yonyou_bound_id=False, b2b_erp_customer_id=False)
                if 'yonyou_class_code' in vals:
                    vals.update(yonyou_class_snapshot=False, yonyou_class_result=False)
                return super(Partner, self.with_context(_yonyou_write=WRITE_TOKEN)).write(vals)
        return super().write(vals)


class Brand(models.Model):
    _name = 'b2b.product.brand'
    _inherit = ['b2b.product.brand', 'b2b.yonyou.mapping.mixin', 'b2b.yonyou.principal.mixin']
    _erp_inputs = Mapping._erp_inputs | {'yonyou_salesperson', 'yonyou_department'}
    @api.depends('yonyou_salesperson', 'yonyou_department', 'yonyou_principal_snapshot', 'b2b_selling_company_id')
    def _compute_principal(self):
        return super()._compute_principal()

    def _erp_company(self):
        return self.b2b_selling_company_id

    def action_yonyou_verify(self):
        return self.action_yonyou_verify_class()
