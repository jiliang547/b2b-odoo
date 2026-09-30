import math
import uuid
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

MANAGER = 'b2b_core.group_b2b_manager'
PRODUCT = 'b2b_core.group_b2b_product_manager'
INTERNAL = MANAGER + ',' + PRODUCT
WRITE_TOKEN = object()


def check_role(record, product=False):
    if not (record.env.su or record.env.user.has_group(MANAGER)
            or (product and record.env.user.has_group(PRODUCT))):
        raise AccessError(record.env._('You do not have permission to maintain this ERP mapping.'))
    record.check_access('write')


def notification(message, error=False):
    return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {
        'title': 'ERP Verification', 'message': message,
        # Errors also remain on the record. Avoid stacked toasts hiding native
        # right-hand navigation / View buttons during repeated verification.
        'type': 'danger' if error else 'success', 'sticky': False,
        'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
    }}


class Connection(models.Model):
    _name = 'b2b.yonyou.connection'
    _description = 'Yonyou C4 Mapping Configuration'

    name = fields.Char(default='Yonyou C4', required=True)
    singleton = fields.Integer(default=1, readonly=True, required=True)
    enabled = fields.Boolean(string='Enable Mapping Queries', default=False)
    registration_sync = fields.Boolean(string='Create / Verify ERP Customer on Approval', default=False)
    test_mode = fields.Boolean(default=True, string='Restrict All Organizations to 999')
    management_org = fields.Char(default='999', required=True)
    default_use_org = fields.Char(default='999', required=True)
    order_sync = fields.Boolean(string='Send Newly Confirmed Orders to ERP', default=False)
    sales_org = fields.Char(string='ERP Sales / Invoice / Stock Organization', default='999', required=True)
    usd_rate = fields.Float(string='USD to CNY Interface Rate', default=6.3, digits=(16, 8), required=True)
    app_key = fields.Char(groups='base.group_system', copy=False)
    app_secret = fields.Char(groups='base.group_system', copy=False)
    token = fields.Char(groups='base.group_system', copy=False, readonly=True)
    token_expiry = fields.Float(groups='base.group_system', copy=False, readonly=True)
    revision = fields.Char(default=lambda s: uuid.uuid4().hex, readonly=True, copy=False)
    code_prefix = fields.Char(default='PH_TEST_', required=True)
    transaction_type = fields.Char(default='SYCSR001', required=True)
    exchange_rate_type = fields.Char(default='01', required=True)
    tax_category = fields.Selection([('0', 'General taxpayer'), ('1', 'Small-scale taxpayer'),
                                     ('2', 'Non VAT taxpayer')], default='0', required=True)
    pay_way = fields.Integer(default=99, required=True)
    price_marking = fields.Integer(default=0, required=True)
    _single = models.Constraint('UNIQUE(singleton)', 'Only one C4 connection is supported.')
    _single_value = models.Constraint('CHECK(singleton = 1)', 'Use the existing C4 connection.')

    @api.constrains('test_mode', 'management_org', 'default_use_org', 'code_prefix', 'registration_sync', 'enabled')
    def _check_configuration(self):
        for rec in self:
            if rec.test_mode and (rec.management_org != '999' or rec.default_use_org != '999'):
                raise ValidationError(_('Test mode requires management and using organization 999.'))
            if not rec.code_prefix.strip() or len(rec.code_prefix) > 12:
                raise ValidationError(_('Use a customer code prefix between 1 and 12 characters.'))
            if rec.registration_sync and not rec.enabled:
                raise ValidationError(_('Enable mapping queries before registration synchronization.'))

    @api.constrains('order_sync', 'sales_org', 'usd_rate', 'enabled', 'test_mode')
    def _check_order_configuration(self):
        for rec in self:
            if not math.isfinite(rec.usd_rate) or rec.usd_rate <= 0:
                raise ValidationError(_('The USD to CNY interface rate must be positive.'))
            if rec.order_sync and (not rec.enabled or not rec.test_mode or rec.sales_org != '999'):
                raise ValidationError(_('Order submission currently requires enabled mapping and test organization 999.'))

    def write(self, vals):
        vals = dict(vals)
        if self.env.context.get('_yonyou_write') is not WRITE_TOKEN:
            if {'token', 'token_expiry', 'revision', 'singleton'} & vals.keys():
                raise AccessError(_('Connection verification data cannot be edited manually.'))
            if {'app_key', 'app_secret', 'test_mode', 'management_org', 'default_use_org'} & vals.keys():
                vals['revision'] = uuid.uuid4().hex
            if {'app_key', 'app_secret'} & vals.keys():
                vals.update(token=False, token_expiry=0)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_module_uninstall(self):
        raise AccessError(_('Disable the connection instead of deleting its audit identity.'))

    def _org(self, company=None):
        self.ensure_one()
        if self.test_mode:
            return '999'
        return (company.sudo().yonyou_use_org if company else False) or self.default_use_org


class Company(models.Model):
    _inherit = 'res.company'
    yonyou_use_org = fields.Char(string='ERP Using Organization Code', default='999', groups='base.group_system')
