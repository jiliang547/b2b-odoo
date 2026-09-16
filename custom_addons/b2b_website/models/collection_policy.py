from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


def check_manager(env):
    if not (env.is_superuser() or env.user.has_group('b2b_core.group_b2b_manager')):
        raise AccessError(env._('Only a B2B Manager can change collection terms.'))


class CollectionPolicy(models.Model):
    _name = 'b2b.collection.policy'
    _description = 'Production / Shipment Collection Conditions'
    _order = 'sequence, id'

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    category = fields.Selection([(c, c) for c in 'ABCDE'], required=True, default='A')
    production_percent = fields.Float(string='Required % Before Production', required=True, default=100)
    shipment_percent = fields.Float(string='Cumulative % Before Shipment', required=True, default=100,
                                   help='Total collected percentage, including the deposit; not an additional payment.')
    payment_term_id = fields.Many2one('account.payment.term', string='Invoice Payment Terms')
    block_overdue = fields.Boolean(default=True, help='For credit/special terms, block release when this company has overdue receivables.')
    note = fields.Text(translate=True)

    @api.constrains('category', 'production_percent', 'shipment_percent', 'payment_term_id')
    def _check_percentages(self):
        for policy in self:
            start, end = policy.production_percent, policy.shipment_percent
            if not (0 <= start <= end <= 100):
                raise ValidationError(_('Collection percentages must satisfy 0 <= production <= shipment <= 100.'))
            valid = {'A': start == end == 100, 'B': 0 < start < 100 and end == 100,
                     'C': start == 0 and end == 100, 'D': start == end == 0, 'E': True}
            if not valid[policy.category]:
                raise ValidationError(_('The percentages do not match the selected collection category.'))
            if end < 100 and not policy.payment_term_id:
                raise ValidationError(_('Credit terms require native invoice payment terms.'))


class Partner(models.Model):
    _inherit = 'res.partner'

    b2b_collection_policy_id = fields.Many2one('b2b.collection.policy', string='Production / Shipment Collection Conditions')
    b2b_account_brand_id = fields.Many2one('b2b.product.brand', string='Account Brand')

    @api.model_create_multi
    def create(self, vals_list):
        if any(set(v) & {'b2b_collection_policy_id', 'b2b_account_brand_id'} for v in vals_list):
            check_manager(self.env)
        return super().create(vals_list)

    def write(self, vals):
        if set(vals) & {'b2b_collection_policy_id', 'b2b_account_brand_id'}:
            check_manager(self.env)
        return super().write(vals)


class Brand(models.Model):
    _inherit = 'b2b.product.brand'

    b2b_collection_journal_ids = fields.Many2many('account.journal', string='Receiving Bank Journals',
        domain="[('type', '=', 'bank')]", groups='base.group_user')

    def write(self, vals):
        if 'b2b_collection_journal_ids' in vals and not (self.env.is_superuser() or self.env.user.has_group('b2b_website.group_b2b_finance')):
            raise AccessError(_('Only Finance can maintain receiving accounts.'))
        if (not self.env.is_superuser() and self.env.user.has_group('b2b_website.group_b2b_finance')
                and not self.env.user.has_group('b2b_core.group_b2b_manager')
                and not self.env.user.has_group('b2b_core.group_b2b_product_manager')
                and set(vals) - {'b2b_collection_journal_ids'}):
            raise AccessError(_('Finance can maintain the receiving-account mapping; brand content requires a product manager.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any('b2b_collection_journal_ids' in v for v in vals_list) and not (self.env.is_superuser() or self.env.user.has_group('b2b_website.group_b2b_finance')):
            raise AccessError(_('Only Finance can maintain receiving accounts.'))
        return super().create(vals_list)


class Website(models.Model):
    _inherit = 'website'

    b2b_default_account_brand_id = fields.Many2one('b2b.product.brand', string='Default Collection Brand')


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'

    b2b_default_account_brand_id = fields.Many2one(related='website_id.b2b_default_account_brand_id', readonly=False)
