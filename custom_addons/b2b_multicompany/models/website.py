"""Narrow adapter around website_sale's single legal-company assumption."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.addons.website_sale.models.website import CART_SESSION_CACHE_KEY, PRICELIST_SESSION_CACHE_KEY


class Website(models.Model):
    _inherit = 'website'

    b2b_fulfilment_mode = fields.Selection([
        ('external', 'External ERP'), ('odoo', 'Odoo Fulfilment')],
        default='external', required=True, string='Fulfilment Provider')

    # Configuration drives routing; this is no longer a stored/manual switch.
    # Partial configuration must enter the guarded path, not silently fall
    # back to the website's legal entity while operators finish setup.
    b2b_multicompany_enabled = fields.Boolean(
        string='Customer-company Routing Configured',
        compute='_compute_company_routing', compute_sudo=True)
    b2b_company_setup_status = fields.Selection([
        ('unconfigured', 'Not configured — existing single-company flow'),
        ('incomplete', 'Incomplete — customer-company ordering blocked'),
        ('configured', 'Routing configured — customer/payment/supply checks still apply'),
    ], compute='_compute_company_routing', compute_sudo=True)

    @api.depends('b2b_selling_company_ids', 'b2b_factory_company_id', 'b2b_fulfilment_mode',
                 'b2b_default_account_brand_id.b2b_selling_company_id')
    def _compute_company_routing(self):
        for website in self:
            configured = bool(website.b2b_selling_company_ids or website.b2b_factory_company_id)
            complete = ((website.b2b_fulfilment_mode == 'external' or website.b2b_factory_company_id) and website.b2b_selling_company_ids
                        and website.b2b_default_account_brand_id.b2b_selling_company_id in website.b2b_selling_company_ids)
            website.b2b_multicompany_enabled = configured
            website.b2b_company_setup_status = 'configured' if complete else 'incomplete' if configured else 'unconfigured'

    def _b2b_request_company(self):
        return self._b2b_configured_seller(self._b2b_frontend_user().partner_id)

    def _b2b_contact_company(self):
        self.ensure_one()
        website = self.sudo()
        user = self._b2b_frontend_user()
        brands = self.env['b2b.product.brand'].sudo()
        if not user._is_public():
            brands = user.partner_id.sudo().commercial_partner_id.b2b_account_brand_id
        for brand in (brands, website.b2b_default_account_brand_id):
            seller = brand.b2b_selling_company_id
            if seller and seller in website.b2b_selling_company_ids:
                return seller
        # Contact is a read-only public page, not a production-readiness check.
        return super()._b2b_contact_company()

    def _b2b_frontend_user(self):
        # Website records may be held in a superuser environment by native
        # rendering helpers. Routing must follow the authenticated visitor.
        return request.env.user if request else self.env.user

    def _b2b_customer_pricelists(self):
        customer = self._b2b_frontend_user().partner_id.sudo().commercial_partner_id
        try:
            seller = self._b2b_request_company()
        except ValidationError:
            # Incomplete routing has no displayable prices. Transaction entry
            # points still reject missing pricing/routing before any ordering.
            return self.env['product.pricelist'].sudo()
        return self.env['product.pricelist'].sudo().search([
            ('active', '=', True), ('website_id', '=', self.id),
            ('b2b_effective_partner_id', '=', customer.id),
            ('company_id', 'in', [False, seller.id]),
        ])

    def get_pricelist_available(self, show_visible=False):
        if not self.b2b_multicompany_enabled or self._b2b_frontend_user()._is_public():
            return super().get_pricelist_available(show_visible=show_visible)
        return self._b2b_customer_pricelists()

    def b2b_pricing_pending(self):
        if not self.b2b_multicompany_enabled or self._b2b_frontend_user()._is_public():
            return super().b2b_pricing_pending()
        return not bool(self._b2b_customer_pricelists())

    def _get_and_cache_current_pricelist(self):
        if not self.b2b_multicompany_enabled or self._b2b_frontend_user()._is_public():
            return super()._get_and_cache_current_pricelist()
        candidates = self._b2b_customer_pricelists()
        selected = candidates.filtered(lambda p: p.id == request.session.get(PRICELIST_SESSION_CACHE_KEY))[:1]
        selected = selected or candidates[:1]
        if not selected:
            # Account/header rendering is not an ordering operation. Do not
            # substitute public pricing or another customer's agreement.
            request.session.pop(PRICELIST_SESSION_CACHE_KEY, None)
            return self.env['product.pricelist']
        request.session[PRICELIST_SESSION_CACHE_KEY] = selected.id
        cart = request.cart
        revision = self._b2b_frontend_user().partner_id.sudo().commercial_partner_id.b2b_pricing_revision
        if cart and (cart.pricelist_id != selected or cart.b2b_pricing_revision != revision):
            cart.write({'pricelist_id': selected.id, 'b2b_pricing_revision': revision})
            cart._recompute_prices()
        return selected

    def _get_and_cache_current_fiscal_position(self):
        if not self.b2b_multicompany_enabled or self._b2b_frontend_user()._is_public():
            return super()._get_and_cache_current_fiscal_position()
        seller = self._b2b_request_company()
        partner = request.cart.partner_shipping_id or self._b2b_frontend_user().partner_id
        return self.env['account.fiscal.position'].sudo().with_company(seller)._get_fiscal_position(partner)

    def _get_and_cache_current_cart(self):
        if not self.b2b_multicompany_enabled:
            return super()._get_and_cache_current_cart()
        orders = self.env['sale.order'].sudo()
        cart = orders.browse(request.session.get(CART_SESSION_CACHE_KEY)).exists()
        # Never restore a submitted quotation, another customer's cart, or a
        # previous seller's cart after an account assignment changes.
        customer = self._b2b_frontend_user().partner_id.sudo().commercial_partner_id
        try:
            seller = self._b2b_request_company() if cart else self.env['res.company']
        except ValidationError:
            seller = self.env['res.company']
        valid = cart and not self._b2b_frontend_user()._is_public() and (
            cart.company_id == seller
            and cart.partner_id.commercial_partner_id == customer
            and cart.website_id == self and cart.state == 'draft'
            # Opening the payment page initializes collection terms while
            # the order is still an editable cart. Submission changes state
            # to sent/sale; collection_active alone is not submission.
            and cart.b2b_review_state != 'pending'
            and cart.get_portal_last_transaction().state not in ('pending', 'authorized', 'done')
        )
        if not valid:
            request.session.pop(CART_SESSION_CACHE_KEY, None)
            request.session['website_sale_cart_quantity'] = 0
            return orders
        return cart.with_company(cart.company_id)

    def _prepare_sale_order_values(self, partner_sudo):
        if self.b2b_pricing_pending():
            raise ValidationError(_('Your pricing is being configured. Please contact us for assistance.'))
        values = super()._prepare_sale_order_values(partner_sudo)
        if self.b2b_multicompany_enabled:
            seller = self._b2b_configured_seller(partner_sudo)
            values['company_id'] = seller.id
            # Visitors cannot read crm.team. Inspect only this website's
            # configured team; do not grant portal users sales-team access.
            team = self.sudo().salesteam_id
            if team.company_id and team.company_id != seller:
                values['team_id'] = False
        return values


class Partner(models.Model):
    _inherit = 'res.partner'

    def _b2b_override_pricing_company(self, website):
        if website.b2b_multicompany_enabled:
            return website._b2b_configured_seller(self)
        return super()._b2b_override_pricing_company(website)

    def _b2b_effective_pricing_company(self, website):
        if website.b2b_multicompany_enabled:
            # An effective price agreement belongs to the commercial customer,
            # not to an accounting ledger. Shared native pricelists remain
            # valid on historic orders when future seller assignment changes.
            return self.env['res.company']
        return super()._b2b_effective_pricing_company(website)


class ProductPricelist(models.Model):
    _inherit = 'product.pricelist'

    def _is_available_on_website(self, website):
        if website.b2b_multicompany_enabled and self.sudo().b2b_effective_partner_id:
            user = request.env.user if request else self.env.user
            customer = user.partner_id.sudo().commercial_partner_id
            return bool(self.active and self.website_id == website and self.sudo().b2b_effective_partner_id == customer)
        return super()._is_available_on_website(website)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    b2b_routed_company = fields.Boolean(readonly=True, copy=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = self.browse()
        for original in vals_list:
            vals = dict(original)
            vals.pop('b2b_routed_company', None)
            website = self.env['website'].browse(vals.get('website_id')).sudo()
            if not website.b2b_multicompany_enabled:
                records |= super().create([vals])
                continue
            partner = self.env['res.partner'].browse(vals.get('partner_id')).sudo()
            seller = website._b2b_configured_seller(partner)
            if vals.get('company_id') and vals['company_id'] != seller.id:
                raise ValidationError(_('The order company must match the customer legal seller.'))
            # website_sale.create explicitly refuses any different legal
            # company. Create the native order in the correct company first,
            # then attach its website before returning from this transaction.
            # This preserves the native create chain; no vendor monkey patch.
            vals.pop('website_id', None)
            vals.update(company_id=seller.id, b2b_routed_company=True)
            # Native website carts deliberately leave the salesperson blank
            # until confirmation. Without this explicit value the temporary
            # website-less create would assign the superuser (OdooBot).
            vals.setdefault('user_id', False)
            scoped = self.with_company(seller).with_context(default_website_id=False)
            order = super(SaleOrder, scoped).create([vals])
            order.write({'website_id': website.id})
            records |= order
        return records

    def write(self, vals):
        if 'b2b_routed_company' in vals and any(order.b2b_routed_company != vals['b2b_routed_company'] for order in self):
            raise ValidationError(_('The company routing snapshot cannot be changed.'))
        for order in self.filtered('b2b_routed_company'):
            if order.website_id and 'website_id' in vals and vals['website_id'] != order.website_id.id:
                raise ValidationError(_('The website of a routed order cannot be changed.'))
            if 'partner_id' in vals:
                partner = self.env['res.partner'].sudo().browse(vals['partner_id'])
                if order.website_id._b2b_configured_seller(partner) != order.company_id:
                    raise ValidationError(_('The new customer belongs to a different legal seller.'))
        if 'company_id' in vals:
            for order in self.filtered('b2b_routed_company'):
                if vals['company_id'] != order.company_id.id:
                    raise ValidationError(_('An order legal seller cannot be changed. Cancel the draft and create a new order instead.'))
        return super().write(vals)

    @api.constrains('b2b_brand_id', 'company_id')
    def _check_routed_brand(self):
        for order in self.filtered('b2b_routed_company'):
            if order.b2b_brand_id and order.b2b_brand_id.b2b_selling_company_id != order.company_id:
                raise ValidationError(_('The order account brand must belong to its legal seller.'))


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    def _get_sales_prices(self, website):
        if website.b2b_multicompany_enabled and not self.env.user._is_public():
            scoped = self.sudo().with_company(website._b2b_request_company())
            return super(ProductTemplate, scoped)._get_sales_prices(website)
        return super()._get_sales_prices(website)

    def _get_combination_info(self, *args, **kwargs):
        website = request.website if request and hasattr(request, 'website') else self.env['website']
        if website.b2b_multicompany_enabled and not self.env.user._is_public():
            scoped = self.sudo().with_company(website._b2b_request_company())
            return super(ProductTemplate, scoped)._get_combination_info(*args, **kwargs)
        return super()._get_combination_info(*args, **kwargs)


class Settings(models.TransientModel):
    _inherit = 'res.config.settings'
    b2b_company_setup_status = fields.Selection(related='website_id.b2b_company_setup_status')
    b2b_fulfilment_mode = fields.Selection(related='website_id.b2b_fulfilment_mode', readonly=False)


class ProductService(models.AbstractModel):
    _inherit = 'b2b.product.service'

    def can_view_price(self, partner=None, website=None):
        allowed = super().can_view_price(partner=partner, website=website)
        website = website or self.env['website'].get_current_website()
        if allowed and not self.env.user._is_internal() and website.b2b_pricing_pending():
            return False
        return allowed

    def price_state(self, partner=None, website=None):
        website = website or self.env['website'].get_current_website()
        if website.b2b_multicompany_enabled and not self.env.user._is_public():
            if website.b2b_require_approved_checkout and not self.commercial_partner(partner).b2b_approved:
                return 'pending_approval'
            if website.b2b_pricing_pending():
                return 'pricing_pending'
        return super().price_state(partner=partner, website=website)
