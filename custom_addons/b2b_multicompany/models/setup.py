"""One workspace for native configuration; no duplicate company or bank models."""
from odoo import api, fields, models, Command, _
from odoo.exceptions import ValidationError
from .configuration import check_configuration_access


class BusinessSetup(models.TransientModel):
    _name = 'b2b.business.setup'
    _description = 'Partner Hub Business Setup'
    _rec_name = 'website_id'

    @api.depends('website_id')
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = _('Business Setup — %s', wizard.website_id.name) if wizard.website_id else _('Business Setup')

    website_id = fields.Many2one('website', required=True, string='Website')
    selling_company_ids = fields.Many2many('res.company', string='Selling Companies')
    default_brand_id = fields.Many2one('b2b.product.brand', string='Default Brand for New Customers')
    bank_company_id = fields.Many2one('res.company', string='Bank Configuration Company')
    fulfilment_mode = fields.Selection([('external', 'External ERP'), ('odoo', 'Odoo Fulfilment')],
                                      required=True, default='external', string='Fulfilment Provider')
    factory_id = fields.Many2one('res.company', string='Stock-owning Factory')
    customer_ids = fields.Many2many('res.partner', string='Customers to Assign')
    customer_seller_id = fields.Many2one('res.company', string='Assign to Selling Company')
    customer_brand_id = fields.Many2one('b2b.product.brand', string='Assign Account Brand')
    checklist = fields.Text(compute='_compute_checklist', string='Configuration Checklist')

    @api.onchange('website_id')
    def _onchange_website(self):
        for wizard in self:
            website = wizard.website_id
            if not self.env.is_superuser() and website.sudo().b2b_selling_company_ids - self.env.companies:
                raise ValidationError(_('Select all configured selling companies in the top-right company selector before editing Business Setup. No configuration has been changed.'))
            wizard.selling_company_ids = website.b2b_selling_company_ids
            wizard.default_brand_id = website.b2b_default_account_brand_id
            wizard.fulfilment_mode = website.b2b_fulfilment_mode or 'external'
            wizard.factory_id = website.b2b_factory_company_id

    @api.depends('selling_company_ids', 'default_brand_id', 'fulfilment_mode', 'factory_id', 'website_id')
    def _compute_checklist(self):
        for wizard in self:
            lines = []
            # Web onchange wraps related records in NewId(origin=...). Use
            # their real identities for searches and cross-record comparison.
            companies = wizard.selling_company_ids._origin
            default_brand = wizard.default_brand_id._origin
            if not companies:
                lines.append(_('Missing: select the selling legal companies.'))
            if not default_brand or default_brand.b2b_selling_company_id not in companies:
                lines.append(_('Missing: a default brand belonging to a selected seller.'))
            if wizard.fulfilment_mode == 'odoo' and not wizard.factory_id:
                lines.append(_('Missing: a factory for Odoo fulfilment.'))
            for company in companies:
                brands = self.env['b2b.product.brand'].search([('b2b_selling_company_id', '=', company.id)])
                if not brands:
                    lines.append(_('%s: create or link its account brand.', company.name))
                elif self.env.user.has_group('b2b_website.group_b2b_finance'):
                    for brand in brands:
                        if not brand.b2b_collection_journal_ids:
                            lines.append(_('%s: finance must link a receiving bank journal.', brand.name))
            lines.append(_('Finance must verify each seller’s journals, accounts, currency and taxes in native Accounting. No accounting defaults are guessed.'))
            lines.append(_('External ERP: no factory or local stock operations required. API integration and status acknowledgement remain pending.')
                         if wizard.fulfilment_mode == 'external' else
                         _('Odoo fulfilment: verify native factory warehouse, intercompany rules and vendor supply prices.'))
            wizard.checklist = '\n'.join(lines)

    def action_save_setup(self):
        self.ensure_one()
        check_configuration_access(self.env)
        if not self.env.is_superuser() and (self.website_id.sudo().b2b_selling_company_ids | self.selling_company_ids) - self.env.companies:
            raise ValidationError(_('Select all configured selling companies in the top-right company selector before saving, to avoid losing hidden company links.'))
        if self.selling_company_ids - self.env.user.company_ids:
            raise ValidationError(_('Ask an administrator to grant access to the selected companies first.'))
        self.website_id.check_access('read')
        if self.website_id.company_id not in self.env.user.company_ids or (self.factory_id and self.factory_id not in self.env.user.company_ids):
            raise ValidationError(_('You need access to the website company and any selected factory.'))
        # A manager may configure only these business fields, not acquire the
        # broad native website administrator role or change arbitrary fields.
        self.website_id.sudo().write({
            'b2b_selling_company_ids': [Command.set(self.selling_company_ids.ids)],
            'b2b_default_account_brand_id': self.default_brand_id.id,
            'b2b_fulfilment_mode': self.fulfilment_mode,
            # Retain a historical factory unless the user explicitly changes it.
            'b2b_factory_company_id': self.factory_id.id,
        })
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Configuration saved'),
                           'message': _('Partial configuration can be saved. Complete the checklist before accepting orders.'),
                           'type': 'success', 'sticky': False}}

    def action_assign_customers(self):
        self.ensure_one()
        check_configuration_access(self.env)
        if not self.customer_ids or not self.customer_seller_id or not self.customer_brand_id:
            raise ValidationError(_('Select customers, their selling company and account brand.'))
        if self.customer_seller_id not in self.website_id.b2b_selling_company_ids:
            raise ValidationError(_('Save this seller in the website configuration first.'))
        if self.customer_seller_id not in self.env.user.company_ids:
            raise ValidationError(_('You do not have access to this selling company.'))
        if self.customer_brand_id.b2b_selling_company_id != self.customer_seller_id:
            raise ValidationError(_('The selected brand must belong to the selected seller.'))
        if any(p != p.commercial_partner_id for p in self.customer_ids):
            raise ValidationError(_('Assign commercial customers, not their individual contacts.'))
        self.customer_ids.write({'b2b_selling_company_id': self.customer_seller_id.id,
                                 'b2b_account_brand_id': self.customer_brand_id.id})
        return {'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Customers assigned'), 'message': _('Existing orders were not reassigned.'), 'type': 'success'}}

    def _open_native(self, model, name, domain=None):
        self.ensure_one()
        check_configuration_access(self.env)
        # Odoo 19 does not switch list -> form in a target=new act_window.
        # Use the native action stack so rows/New work and the setup breadcrumb
        # remains available. Do not use target=main (which clears that stack).
        return {'type': 'ir.actions.act_window', 'name': name, 'res_model': model,
                'view_mode': 'list,form', 'views': [(False, 'list'), (False, 'form')],
                'domain': domain or [], 'target': 'current'}

    def action_companies(self):
        return self._open_native('res.company', _('Companies'))

    def action_brands(self):
        return self._open_native('b2b.product.brand', _('Brand Legal Sellers and Receiving Accounts'))

    def action_banks(self):
        self.ensure_one()
        if not self.bank_company_id or self.bank_company_id not in self.selling_company_ids:
            raise ValidationError(_('Select Bank Configuration Company from your selling companies first.'))
        if self.bank_company_id not in self.env.user.company_ids:
            raise ValidationError(_('You do not have access to this bank company.'))
        action = self._open_native('account.journal', _('Bank Journals — %s', self.bank_company_id.name),
                                   [('type', '=', 'bank'), ('company_id', '=', self.bank_company_id.id)])
        action['context'] = dict(self.env.context, allowed_company_ids=self.bank_company_id.ids,
                                 default_company_id=self.bank_company_id.id, default_type='bank',
                                 b2b_bank_setup_company_id=self.bank_company_id.id)
        action['views'] = [(self.env.ref('b2b_multicompany.view_setup_bank_journals').id, 'list'),
                           (self.env.ref('b2b_multicompany.view_setup_bank_journal_form').id, 'form')]
        return action

    def action_users(self):
        action = self._open_native('res.users', _('Users and Company Access'), [('share', '=', False)])
        # The default res.users form is the simplified contact-like view.
        # Match Settings / Users explicitly; keep native ACLs (no sudo).
        action['views'] = [(self.env.ref('base.view_users_tree').id, 'list'),
                           (self.env.ref('base.view_users_form').id, 'form')]
        action['search_view_id'] = (self.env.ref('base.view_users_search').id, 'search')
        action['context'] = dict(self.env.context, is_action_res_users=True)
        return action
