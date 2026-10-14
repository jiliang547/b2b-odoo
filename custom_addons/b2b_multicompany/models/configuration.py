"""Company configuration; installing this module does not migrate existing orders."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError



def check_configuration_access(env):
    if not (env.is_superuser() or env.user.has_group('b2b_core.group_b2b_manager')):
        raise AccessError(env._('Only a B2B Manager can assign selling companies.'))


class Brand(models.Model):
    _inherit = 'b2b.product.brand'

    b2b_selling_company_id = fields.Many2one(
        'res.company', string='Contracting / Invoicing Company', ondelete='restrict',
        help='Legal seller for this account brand, not the manufacturer of a product.')

    @api.constrains('b2b_selling_company_id', 'b2b_collection_journal_ids')
    def _check_selling_bank_companies(self):
        for brand in self:
            if brand.b2b_selling_company_id and any(
                journal.company_id != brand.b2b_selling_company_id
                for journal in brand.b2b_collection_journal_ids
            ):
                raise ValidationError(_('Every receiving bank journal must belong to the brand legal seller.'))

    @api.model_create_multi
    def create(self, vals_list):
        if any('b2b_selling_company_id' in vals for vals in vals_list):
            check_configuration_access(self.env)
        return super().create(vals_list)

    def write(self, vals):
        if 'b2b_selling_company_id' in vals:
            check_configuration_access(self.env)
            for brand in self:
                if brand.b2b_selling_company_id and brand.b2b_selling_company_id.id != vals['b2b_selling_company_id']:
                    if self.env['sale.order'].sudo().search_count([
                        ('b2b_brand_id', '=', brand.id), ('b2b_collection_active', '=', True),
                    ], limit=1):
                        raise ValidationError(_('This account brand has issued orders. Create a new brand mapping instead of changing its legal seller.'))
        return super().write(vals)


class Partner(models.Model):
    _inherit = 'res.partner'

    b2b_selling_company_id = fields.Many2one(
        'res.company', string='Assigned Selling Company', ondelete='restrict',
        groups='b2b_core.group_b2b_operator',
        help='Assign on the commercial customer. Contacts inherit this assignment; it is not the native contact Company field.')
    b2b_effective_selling_company_id = fields.Many2one(
        related='commercial_partner_id.b2b_selling_company_id',
        string='Effective Selling Company', groups='b2b_core.group_b2b_operator')

    def _b2b_share_order_addresses(self, extra_partner_ids=()):
        """Keep external customer addresses usable by their routed legal seller.

        ``company_id`` on a contact is Odoo's record-owning company, not this
        module's legal-seller assignment. Partner Hub customers are routed by
        ``b2b_selling_company_id`` / account brand, so their ordering addresses
        must stay shared. Native ``check_company`` remains enabled on orders.
        """
        self.ensure_one()
        commercial = self.sudo().commercial_partner_id
        if not commercial:
            return self.env['res.partner']

        # Never turn an internal legal entity's own company contact into a
        # shared customer record, even if it is selected accidentally.
        if self.env['res.company'].sudo().search_count([
            ('partner_id', '=', commercial.id),
        ], limit=1):
            return self.env['res.partner']

        address_ids = set(commercial.address_get(['invoice', 'delivery']).values())
        address_ids.update(int(partner_id) for partner_id in extra_partner_ids if partner_id)
        address_ids.add(commercial.id)
        addresses = self.env['res.partner'].sudo().with_context(active_test=False).browse(
            address_ids
        ).exists().filtered(
            lambda address: address.commercial_partner_id == commercial and address.company_id
        )
        if addresses:
            addresses.with_context(tracking_disable=True).write({'company_id': False})
        return addresses

    @api.onchange('b2b_account_brand_id')
    def _onchange_account_brand_seller(self):
        if self.b2b_account_brand_id.b2b_selling_company_id:
            self.b2b_selling_company_id = self.b2b_account_brand_id.b2b_selling_company_id

    @api.model
    def _b2b_brand_assignment_values(self, original):
        vals = dict(original)
        if vals.get('b2b_account_brand_id') and 'b2b_selling_company_id' not in vals:
            brand = self.env['b2b.product.brand'].browse(vals['b2b_account_brand_id'])
            if brand.b2b_selling_company_id:
                vals['b2b_selling_company_id'] = brand.b2b_selling_company_id.id
        if vals.get('b2b_selling_company_id') and not self.env.su and vals['b2b_selling_company_id'] not in self.env.user.company_ids.ids:
            raise AccessError(_('You do not have access to the selected selling company.'))
        return vals

    @api.constrains('b2b_selling_company_id', 'b2b_account_brand_id', 'parent_id', 'is_company')
    def _check_selling_assignment(self):
        for partner in self:
            if partner.b2b_selling_company_id and partner != partner.commercial_partner_id:
                raise ValidationError(_('Assign the selling company on the commercial customer, not an individual contact.'))
            seller = partner.b2b_selling_company_id
            brand_seller = partner.b2b_account_brand_id.b2b_selling_company_id
            if seller and brand_seller and seller != brand_seller:
                raise ValidationError(_('The account brand and assigned selling company must agree.'))

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._b2b_brand_assignment_values(vals) for vals in vals_list]
        if any('b2b_selling_company_id' in vals for vals in vals_list):
            check_configuration_access(self.env)
        return super().create(vals_list)

    def write(self, vals):
        vals = self._b2b_brand_assignment_values(vals)
        if 'b2b_selling_company_id' in vals:
            check_configuration_access(self.env)
            for partner in self:
                if partner.b2b_selling_company_id.id != vals['b2b_selling_company_id']:
                    orders = self.env['sale.order'].sudo().search_count([
                        ('partner_id.commercial_partner_id', '=', partner.id),
                        ('state', 'in', ['draft', 'sent']),
                        ('b2b_collection_active', '=', True),
                    ], limit=1)
                    if orders:
                        raise ValidationError(_('Complete or cancel submitted quotations before transferring this customer to another seller. Existing orders will never be reassigned.'))
        return super().write(vals)


class Website(models.Model):
    _inherit = 'website'

    b2b_selling_company_ids = fields.Many2many(
        'res.company', 'b2b_website_seller_rel', 'website_id', 'company_id',
        string='Permitted Selling Companies')
    b2b_factory_company_id = fields.Many2one(
        'res.company', string='Stock-owning Factory', ondelete='restrict')

    @api.model_create_multi
    def create(self, vals_list):
        protected = {'b2b_factory_company_id', 'b2b_selling_company_ids', 'b2b_multicompany_enabled', 'b2b_fulfilment_mode'}
        if any(protected.intersection(vals) for vals in vals_list):
            check_configuration_access(self.env)
        if any('b2b_multicompany_enabled' in vals for vals in vals_list):
            raise ValidationError(_('Company routing is automatic. Configure the permitted sellers and factory instead of an activation switch.'))
        return super().create(vals_list)

    def write(self, vals):
        if {'b2b_factory_company_id', 'b2b_selling_company_ids', 'b2b_multicompany_enabled', 'b2b_fulfilment_mode'}.intersection(vals):
            check_configuration_access(self.env)
        if 'b2b_multicompany_enabled' in vals:
            raise ValidationError(_('Company routing is automatic. Configure the permitted sellers and factory instead of an activation switch.'))
        if 'b2b_factory_company_id' in vals:
            for website in self:
                if vals['b2b_factory_company_id'] != website.b2b_factory_company_id.id:
                    routed = self.env['sale.order'].sudo().search([
                        ('website_id', '=', website.id), ('b2b_fulfilment_mode', '=', 'odoo')], limit=1)
                    if routed:
                        raise ValidationError(_('This website has routed orders. Its stock-owning factory cannot be changed without a supply migration.'))
        result = super().write(vals)
        if {'b2b_factory_company_id', 'b2b_selling_company_ids'}.intersection(vals):
            for website in self:
                if not website.b2b_multicompany_enabled and self.env['sale.order'].sudo().search_count([
                    ('website_id', '=', website.id), ('b2b_routed_company', '=', True)], limit=1):
                    raise ValidationError(_('Do not remove company routing configuration from a website with routed orders.'))
            types = self.env['b2b.customer.type.pricelist'].sudo().search([('website_id', 'in', self.ids)]).customer_type_id
            types._b2b_sync_pricing_partners()
        return result

    @api.constrains('b2b_selling_company_ids', 'b2b_factory_company_id')
    def _check_factory_separation(self):
        for website in self:
            if website.b2b_factory_company_id in website.b2b_selling_company_ids:
                raise ValidationError(_('The stock-owning factory must be separate from the selling companies.'))

    def _b2b_configured_seller(self, partner):
        """Server-side resolution; never use a company ID submitted by a visitor."""
        self.ensure_one()
        # The website limits a portal request to its default company. Read
        # the manager-owned routing configuration with privilege, not through
        # that filtered company list; do not grant the visitor company access.
        self = self.sudo()
        if self.b2b_multicompany_enabled and self.b2b_company_setup_status != 'configured':
            raise ValidationError(_('Complete the permitted sellers and default account brand. A factory is required only for Odoo fulfilment.'))
        customer = partner.sudo().commercial_partner_id
        brand = customer.b2b_account_brand_id or self.b2b_default_account_brand_id
        seller = customer.b2b_selling_company_id or brand.b2b_selling_company_id
        if not seller or seller not in self.b2b_selling_company_ids:
            raise ValidationError(_('Our team must configure this customer\'s selling company before ordering.'))
        if not brand.b2b_selling_company_id or brand.b2b_selling_company_id != seller:
            raise ValidationError(_('Configure an account brand belonging to this customer\'s selling company.'))
        return seller


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'

    b2b_selling_company_ids = fields.Many2many(related='website_id.b2b_selling_company_ids', readonly=False)
    b2b_factory_company_id = fields.Many2one(related='website_id.b2b_factory_company_id', readonly=False)
