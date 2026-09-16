from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.addons.website_sale.tests.common import MockRequest
from unittest.mock import patch
from psycopg2.errors import UniqueViolation
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestSellingConfiguration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.seller = cls.env['res.company'].create({'name': 'UAT Legal Seller'})
        cls.factory = cls.env['res.company'].create({'name': 'UAT Stock Owner'})
        cls.brand = cls.env['b2b.product.brand'].create({
            'name': 'UAT Account Brand', 'b2b_selling_company_id': cls.seller.id})
        cls.customer = cls.env['res.partner'].create({
            'name': 'UAT Commercial Customer', 'is_company': True,
            'b2b_selling_company_id': cls.seller.id, 'b2b_account_brand_id': cls.brand.id})
        cls.website = cls.env['website'].create({
            'b2b_fulfilment_mode': 'odoo',
            'name': 'UAT Multi-company Website', 'company_id': cls.env.company.id,
            'b2b_selling_company_ids': [Command.set(cls.seller.ids)],
            'b2b_factory_company_id': cls.factory.id,
            'b2b_default_account_brand_id': cls.brand.id})

    def test_contact_details_follow_customer_brand_without_company_access(self):
        other = self.env['res.company'].create({'name': 'UAT Default Contact Seller'})
        default_brand = self.env['b2b.product.brand'].create({
            'name': 'UAT Default Contact Brand', 'b2b_selling_company_id': other.id})
        self.website.write({'b2b_selling_company_ids': [Command.link(other.id)],
                            'b2b_default_account_brand_id': default_brand.id})
        self.seller.write({'email': 'seller-contact@example.test', 'phone': '+1 202 555 0100',
                           'street': '123 UAT Seller Street'})
        contact = self.env['res.partner'].create({'name': 'UAT Brand Contact', 'parent_id': self.customer.id})
        user = self.env['res.users'].create({'name': contact.name, 'login': 'uat-brand-contact',
            'partner_id': contact.id, 'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)]})
        website = self.website.with_user(user)
        with MockRequest(website.env, website=website):
            details = website.b2b_contact_details()
            self.assertEqual(details['name'], self.seller.name)
            self.assertEqual(details['email'], 'seller-contact@example.test')
            self.assertIn('123 UAT Seller Street', details['address'])
            self.assertEqual(set(details), {'name', 'email', 'phone', 'address'})
            self.assertNotIn(self.seller, user.company_ids)
            self.assertEqual(website.env.company, self.website.company_id)

    def test_contact_default_brand_fallback_and_missing_fields(self):
        public_website = self.website.with_user(self.website.user_id)
        with MockRequest(public_website.env, website=public_website):
            self.assertEqual(public_website.b2b_contact_details()['name'], self.seller.name)
            self.seller.write({'email': False, 'phone': False, 'street': False, 'street2': False,
                               'city': False, 'state_id': False, 'zip': False, 'country_id': False})
            details = public_website.b2b_contact_details()
            self.assertFalse(details['email'])
            self.assertFalse(details['phone'])
            self.assertEqual(details['address'], 'Contact us for our current office address.')
            self.website.b2b_default_account_brand_id = False
            self.assertEqual(public_website.b2b_contact_details()['name'], self.website.company_id.name)

    def test_contact_incomplete_setup_has_no_pricing_exception(self):
        user = self.env['res.users'].create({'name': 'UAT Contact Fallback', 'login': 'uat-contact-fallback',
            'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)]})
        website = self.website.with_user(user)
        with MockRequest(website.env, website=website):
            self.assertEqual(website.b2b_contact_details()['name'], self.seller.name)
            self.website.b2b_default_account_brand_id = False
            self.assertEqual(website.b2b_contact_details()['name'], self.website.company_id.name)
            self.assertFalse(website._get_and_cache_current_pricelist())
            self.assertFalse(website.b2b_currency_pricelists())
            with self.assertRaises(ValidationError):
                website._prepare_sale_order_values(user.partner_id)

    def test_missing_customer_pricing_allows_reading_but_blocks_cart(self):
        from odoo.addons.b2b_website.controllers.website_sale import PartnerHubCart, PartnerHubCartPayment
        from odoo.exceptions import UserError
        from odoo.addons.website_sale.models.website import PRICELIST_SESSION_CACHE_KEY
        user = self.env['res.users'].create({
            'name': 'UAT Missing Pricing', 'login': 'uat-missing-pricing',
            'partner_id': self.customer.id,
            'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)],
        })
        category = self.env['b2b.customer.type'].create({'name': 'UAT Unconfigured Prices'})
        self.customer.b2b_customer_type_id = category
        self.website.write({'b2b_price_display_mode': 'approved', 'b2b_require_approved_checkout': True})
        website = self.website.with_user(user)
        service = self.env['b2b.product.service'].with_user(user)
        with MockRequest(website.env, website=website) as http_request:
            http_request.session[PRICELIST_SESSION_CACHE_KEY] = self.env['product.pricelist'].search([], limit=1).id
            self.assertFalse(website._get_and_cache_current_pricelist())
            self.assertNotIn(PRICELIST_SESSION_CACHE_KEY, http_request.session)
            self.assertFalse(website.b2b_currency_pricelists())
            self.assertEqual(service.price_state(website=website), 'pending_approval')
            self.customer.b2b_approved = True
            self.assertEqual(service.price_state(website=website), 'pricing_pending')
            self.assertFalse(service.can_view_price(website=website))
            with self.assertRaises(UserError):
                PartnerHubCart().add_to_cart(product_template_id=0, product_id=0)
            with self.assertRaises(UserError):
                PartnerHubCart().update_cart(line_id=0, quantity=2)
            with self.assertRaises(UserError):
                PartnerHubCartPayment().shop_payment_transaction(order_id=0, access_token='')
            with self.assertRaises(ValidationError):
                website._prepare_sale_order_values(user.partner_id)
            base = self.env['product.pricelist'].create({'name': 'UAT Restored Prices', 'company_id': False})
            self.env['b2b.customer.type.pricelist'].create({
                'customer_type_id': category.id, 'website_id': self.website.id, 'pricelist_id': base.id})
            self.assertFalse(website.b2b_pricing_pending())
            self.assertEqual(service.price_state(website=website), 'visible')
            self.assertEqual(website._get_and_cache_current_pricelist().b2b_effective_partner_id, self.customer)

    def test_full_accounting_is_installed_without_elevating_b2b_finance(self):
        accounting = self.env['ir.module.module'].search([('name', '=', 'accountant')])
        self.assertEqual(accounting.state, 'installed')
        manager = self.env.ref('account.group_account_manager')
        self.assertIn(self.env.ref('account.group_account_user'), manager.implied_ids)
        finance = self.env['res.users'].create({
            'name': 'UAT Accounting Dependency Finance',
            'login': 'uat-accounting-dependency-finance',
            'group_ids': [Command.set(self.env.ref('b2b_website.group_b2b_finance').ids)],
        })
        self.assertTrue(finance.has_group('account.group_account_invoice'))
        self.assertFalse(finance.has_group('account.group_account_manager'))

    def test_setup_native_pages_support_list_form_navigation(self):
        self.env.user.company_ids = [Command.link(self.seller.id)]
        wizard = self.env['b2b.business.setup'].create({
            'website_id': self.website.id, 'selling_company_ids': [Command.set(self.seller.ids)],
            'bank_company_id': self.seller.id})
        for method, model in [('action_companies', 'res.company'), ('action_users', 'res.users'),
                              ('action_brands', 'b2b.product.brand'), ('action_banks', 'account.journal')]:
            action = getattr(wizard, method)()
            self.assertEqual(action['target'], 'current', method)
            self.assertEqual(action['res_model'], model)
            self.assertEqual([kind for _id, kind in action['views']], ['list', 'form'])
        self.assertEqual(wizard.action_users()['domain'], [('share', '=', False)])
        users_action = wizard.action_users()
        self.assertEqual(users_action['views'][1], (self.env.ref('base.view_users_form').id, 'form'))
        self.assertTrue(users_action['context']['is_action_res_users'])
        view = self.env['res.users'].get_view(view_id=users_action['views'][1][0], view_type='form')
        self.assertIn('name="company_ids"', view['arch'])
        self.assertIn('name="company_id"', view['arch'])
        self.assertIn('name="access_rights"', view['arch'])
        bank = wizard.action_banks()
        self.assertIn(('company_id', '=', self.seller.id), bank['domain'])
        self.assertEqual(bank['context']['default_company_id'], self.seller.id)

    def test_contact_inherits_fixed_seller(self):
        contact = self.env['res.partner'].create({'name': 'UAT Contact', 'parent_id': self.customer.id})
        self.assertEqual(contact.b2b_effective_selling_company_id, self.seller)
        self.assertEqual(self.website._b2b_configured_seller(contact), self.seller)

    def test_setup_bank_save_keeps_target_when_global_context_is_restored(self):
        current = self.env.company
        self.env.user.company_ids = [Command.link(self.seller.id)]
        wizard = self.env['b2b.business.setup'].create({
            'website_id': self.website.id, 'selling_company_ids': [Command.set(self.seller.ids)],
            'bank_company_id': self.seller.id})
        action = wizard.action_banks()
        context = dict(action['context'], allowed_company_ids=[current.id, self.seller.id])
        # The same code in the current company must not conflict with the target.
        self.env['account.journal'].create({'name': 'UAT Current Bank', 'code': 'UCTX',
                                          'type': 'bank', 'company_id': current.id})
        journal = self.env['account.journal'].with_context(context).create({
            'name': 'UAT Target Bank', 'code': 'UCTX', 'type': 'bank'})
        self.assertEqual(journal.company_id, self.seller)
        self.assertIn(self.seller, journal.default_account_id.company_ids)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['account.journal'].with_context(context).create({
                'name': 'UAT Wrong Target', 'code': 'UCT2', 'type': 'bank', 'company_id': current.id})
        with self.assertRaises(UniqueViolation), mute_logger('odoo.sql_db'), self.cr.savepoint():
            self.env['account.journal'].with_context(context).create({
                'name': 'UAT Duplicate Target', 'code': 'UCTX', 'type': 'bank'})
        form = self.env['account.journal'].get_view(view_id=action['views'][1][0], view_type='form')
        self.assertIn('force_save="1"', form['arch'])
        self.assertIn('default_company_ids', form['arch'])

    def test_setup_bank_context_does_not_grant_company_access(self):
        user = self.env['res.users'].create({
            'name': 'UAT Restricted Bank Admin', 'login': 'uat-restricted-bank-admin',
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)],
            'group_ids': [Command.set(self.env.ref('account.group_account_manager').ids)]})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['account.journal'].with_user(user).with_context(
                b2b_bank_setup_company_id=self.seller.id).create({
                    'name': 'UAT Forbidden Bank', 'type': 'bank', 'code': 'UFB'})

    def test_setup_default_external_and_batch_assignment(self):
        self.env.user.company_ids = [Command.link(self.seller.id)]
        website = self.env['website'].create({'name': 'UAT Simplified Setup'})
        wizard = self.env['b2b.business.setup'].create({
            'website_id': website.id, 'selling_company_ids': [Command.set(self.seller.ids)],
            'default_brand_id': self.brand.id})
        wizard.action_save_setup()
        self.assertEqual(website.b2b_fulfilment_mode, 'external')
        wizard.bank_company_id = self.seller
        action = wizard.action_banks()
        self.assertEqual(action['context']['allowed_company_ids'], self.seller.ids)
        self.assertEqual(action['context']['default_company_id'], self.seller.id)
        self.assertEqual(website.b2b_company_setup_status, 'configured')
        self.assertFalse(website.b2b_factory_company_id)
        customer = self.env['res.partner'].create({'name': 'UAT Batch Customer', 'is_company': True})
        wizard.write({'customer_ids': [Command.set(customer.ids)],
                      'customer_seller_id': self.seller.id, 'customer_brand_id': self.brand.id})
        wizard.action_assign_customers()
        self.assertEqual(customer.b2b_selling_company_id, self.seller)
        self.assertEqual(customer.b2b_account_brand_id, self.brand)
        order = self.env['sale.order'].create({'website_id': website.id, 'partner_id': customer.id,
                                              'b2b_fulfilment_mode': 'odoo'})
        self.assertEqual(order.b2b_fulfilment_mode, 'external')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.b2b_fulfilment_mode = 'odoo'

    def test_setup_does_not_bypass_native_company_access(self):
        user = self.env['res.users'].create({
            'name': 'UAT Setup Manager', 'login': 'uat-setup-manager@example.test',
            'company_id': self.env.company.id, 'company_ids': [Command.set(self.env.company.ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)]})
        wizard = self.env['b2b.business.setup'].with_user(user).create({'website_id': self.website.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            wizard.write({'selling_company_ids': [Command.set(self.seller.ids)]})

    def test_setup_checklist_handles_unsaved_browser_relations(self):
        wizard = self.env['b2b.business.setup'].new({'website_id': self.website.id, 'fulfilment_mode': 'external'})
        wizard.selling_company_ids = self.seller.new({}, origin=self.seller)
        wizard.default_brand_id = self.brand.new({}, origin=self.brand)
        wizard._compute_checklist()
        self.assertNotIn('Missing:', wizard.checklist)
        self.assertNotIn('create or link its account brand', wizard.checklist)

    def test_setup_blocks_filtered_companies_and_allows_scoped_manager(self):
        companies = self.env.company | self.seller
        user = self.env['res.users'].create({
            'name': 'UAT Setup All Sellers', 'login': 'uat-setup-all@example.test',
            'company_id': self.env.company.id, 'company_ids': [Command.set(companies.ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)]})
        wizard = self.env['b2b.business.setup'].with_user(user).with_context(
            allowed_company_ids=self.env.company.ids).create({'website_id': self.website.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard._onchange_website()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            wizard.action_save_setup()
        wizard = wizard.with_context(allowed_company_ids=companies.ids)
        wizard.write({'selling_company_ids': [Command.set(self.seller.ids)],
                      'default_brand_id': self.brand.id, 'fulfilment_mode': 'external'})
        wizard.action_save_setup()
        self.assertEqual(self.website.b2b_fulfilment_mode, 'external')
        self.assertEqual(self.website.b2b_selling_company_ids, self.seller)
        self.assertFalse(self.website.b2b_factory_company_id)

    def test_default_brand_routes_unassigned_customer(self):
        customer = self.env['res.partner'].create({'name': 'UAT New Customer'})
        self.assertEqual(self.website._b2b_configured_seller(customer), self.seller)

    def test_portal_default_company_does_not_hide_assigned_seller(self):
        user = self.env['res.users'].create({
            'name': 'UAT Restricted Portal', 'login': 'uat-restricted-mc@example.test',
            'partner_id': self.customer.id,
            'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)],
        })
        website = self.website.with_user(user).with_context(
            allowed_company_ids=self.website.company_id.ids)
        self.assertEqual(website._b2b_configured_seller(user.partner_id), self.seller)
        # The adapter must not expand the visitor's native company access.
        self.assertNotIn(self.seller, user.company_ids)

    def test_portal_cart_preparation_does_not_require_sales_team_acl(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        user = self.env['res.users'].create({
            'name': 'UAT Cart Portal', 'login': 'uat-cart-mc@example.test',
            'partner_id': self.customer.id,
            'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)],
        })
        self.website.salesteam_id = self.env['crm.team'].create({
            'name': 'UAT Website Team', 'company_id': self.website.company_id.id})
        category = self.env['b2b.customer.type'].create({'name': 'UAT Portal Category'})
        base = self.env['product.pricelist'].create({'name': 'UAT Portal Base', 'company_id': False})
        self.env['b2b.customer.type.pricelist'].create({
            'customer_type_id': category.id, 'website_id': self.website.id,
            'pricelist_id': base.id})
        self.customer.b2b_customer_type_id = category
        website = self.website.with_user(user).with_context(
            allowed_company_ids=self.website.company_id.ids)
        with MockRequest(website.env, website=website):
            values = website._prepare_sale_order_values(user.partner_id.sudo())
        self.assertEqual(values['company_id'], self.seller.id)
        self.assertFalse(values['team_id'])
        order = self.env['sale.order'].create(values)
        order.b2b_collection_active = True
        with MockRequest(website.env, website=website, sale_order_id=order.id) as http_request:
            self.assertEqual(http_request.cart, order)
        order.action_quotation_sent()
        with MockRequest(website.env, website=website, sale_order_id=order.id) as http_request:
            self.assertFalse(http_request.cart)

    def test_portal_reads_only_own_routed_orders_without_company_grants(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        user = self.env['res.users'].create({
            'name': 'UAT Order Reader', 'login': 'uat-order-reader@example.test',
            'partner_id': self.customer.id,
            'company_id': self.website.company_id.id,
            'company_ids': [Command.set(self.website.company_id.ids)],
            'group_ids': [Command.set(self.env.ref('base.group_portal').ids)],
        })
        product = self.env['product.product'].create({'name': 'UAT Portal Line'})
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': product.id})]})
        other = self.env['res.partner'].create({
            'name': 'UAT Other Customer', 'b2b_selling_company_id': self.seller.id,
            'b2b_account_brand_id': self.brand.id})
        foreign = self.env['sale.order'].create({
            'partner_id': other.id, 'website_id': self.website.id})
        ordinary = self.env['sale.order'].with_company(self.seller).create({
            'partner_id': self.customer.id})
        portal = self.env['sale.order'].with_user(user).with_context(
            allowed_company_ids=user.company_ids.ids)
        self.assertIn(order, portal.search([('id', '=', order.id)]))
        order.with_env(portal.env).check_access('read')
        order.order_line.with_env(portal.env).check_access('read')
        for denied in (foreign, ordinary):
            self.assertFalse(portal.search([('id', '=', denied.id)]))
            with self.assertRaises(AccessError):
                denied.with_env(portal.env).check_access('read')
        with self.assertRaises(AccessError):
            order.with_env(portal.env).check_access('write')
        self.assertNotIn(self.seller, user.company_ids)

    def test_factory_cannot_be_seller(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.website.b2b_selling_company_ids = [Command.link(self.factory.id)]

    def test_confirmed_increase_collects_missing_deposit_first(self):
        product = self.env['product.product'].create({'name': 'UAT Deposit Increase', 'type': 'consu', 'taxes_id': [Command.clear()]})
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'state': 'sale',
            'b2b_collection_active': True, 'b2b_production_percent': 30,
            'b2b_shipment_percent': 100,
            'order_line': [Command.create({'product_id': product.id,
                'product_uom_qty': 3, 'price_unit': 100, 'tax_ids': [Command.clear()]})]})
        with patch.object(type(order), '_b2b_received_amount', return_value=60):
            order._compute_collection_summary()
            self.assertEqual(order.b2b_payable_now, 30)
        with patch.object(type(order), '_b2b_received_amount', return_value=90):
            order._compute_collection_summary()
            self.assertEqual(order.b2b_payable_now, 210)

    def test_changes_are_numbered_assigned_and_isolated_by_seller(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        manager = self.env['res.users'].create({
            'name': 'UAT Seller Manager', 'login': 'uat-seller-manager@example.test',
            'company_id': self.seller.id, 'company_ids': [Command.set(self.seller.ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)],
        })
        outsider = self.env['res.users'].create({
            'name': 'UAT Other Manager', 'login': 'uat-other-manager@example.test',
            'company_id': self.factory.id, 'company_ids': [Command.set(self.factory.ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)],
        })
        # Build a confirmed, unshipped fixture without running procurement.
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'website_id': self.website.id,
            'state': 'sale', 'b2b_collection_active': True})
        change = self.env['b2b.order.change.request'].with_company(self.seller).create({
            'order_id': order.id, 'requested_changes': 'UAT company isolation',
            'assigned_user_id': outsider.id})
        self.assertNotEqual(change.name, 'New')
        self.assertEqual(change.assigned_user_id, manager)
        outside_change = change.with_user(outsider).with_context(allowed_company_ids=outsider.company_ids.ids)
        inside_change = change.with_user(manager).with_context(allowed_company_ids=manager.company_ids.ids)
        self.assertNotIn(change, outside_change.search([]))
        self.assertIn(change, inside_change.search([]))
        with self.assertRaises(AccessError):
            outside_change.check_access('read')

    def test_brand_customer_mismatch_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.customer.b2b_selling_company_id = self.factory

    def test_contact_cannot_override_seller(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['res.partner'].create({'name': 'UAT Invalid Contact', 'parent_id': self.customer.id, 'b2b_selling_company_id': self.seller.id})

    def test_configuration_automatically_routes_and_partial_setup_blocks(self):
        website = self.env['website'].create({'name': 'UAT Automatic Setup', 'b2b_fulfilment_mode': 'odoo'})
        self.assertFalse(website.b2b_multicompany_enabled)
        self.assertEqual(website.b2b_company_setup_status, 'unconfigured')
        website.b2b_selling_company_ids = [Command.set(self.seller.ids)]
        self.assertTrue(website.b2b_multicompany_enabled)
        self.assertEqual(website.b2b_company_setup_status, 'incomplete')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['sale.order'].create({'website_id': website.id, 'partner_id': self.customer.id})
        website.write({'b2b_factory_company_id': self.factory.id,
                       'b2b_default_account_brand_id': self.brand.id})
        self.assertEqual(website.b2b_company_setup_status, 'configured')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            website.write({'b2b_multicompany_enabled': False})
        order = self.env['sale.order'].create({'website_id': website.id, 'partner_id': self.customer.id})
        self.assertEqual(order.company_id, self.seller)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            website.b2b_factory_company_id = False

    def test_cross_company_bank_rejected(self):
        journal = self.env['account.journal'].create({'name': 'UAT Wrong Company Bank', 'code': 'UMC', 'type': 'bank', 'company_id': self.factory.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.brand.b2b_collection_journal_ids = [Command.link(journal.id)]

    def test_routed_order_company_cannot_be_forged(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['sale.order'].create({'website_id': self.website.id, 'partner_id': self.customer.id, 'company_id': self.factory.id})

    def test_routed_order_uses_native_seller(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        order = self.env['sale.order'].create({'website_id': self.website.id, 'partner_id': self.customer.id})
        self.assertEqual(order.company_id, self.seller)
        self.assertEqual(order.website_id, self.website)
        self.assertTrue(order.b2b_routed_company)
        self.assertFalse(order.user_id, 'A website cart must not inherit the superuser as salesperson')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.company_id = self.factory

    def test_external_seller_warehouse_and_revision_ignore_current_company(self):
        manager = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Warehouse UAT Manager', 'login': 'warehouse-uat-manager',
            'company_id': self.env.company.id,
            'company_ids': [Command.set((self.env.company | self.seller).ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)]})
        self.website.b2b_fulfilment_mode = 'external'
        self.customer.b2b_collection_policy_id = self.env.ref('b2b_website.collection_policy_c')
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        self.assertTrue(warehouse)
        order = self.env['sale.order'].with_context(default_warehouse_id=warehouse.id).create({
            'website_id': self.website.id, 'partner_id': self.customer.id})
        self.assertEqual(order.company_id, self.seller)
        self.assertFalse(order.warehouse_id)
        order.user_id = self.env.user
        self.assertFalse(order.warehouse_id)
        order.action_confirm()
        self.assertFalse(order.picking_ids)
        with self.assertRaises(UserError), self.cr.savepoint():
            order.write({'warehouse_id': warehouse.id})
        # Simulate pre-fix data without weakening the runtime company checks.
        order.flush_recordset()
        self.env.cr.execute('UPDATE sale_order SET warehouse_id=%s WHERE id=%s', [warehouse.id, order.id])
        order.invalidate_recordset(['warehouse_id'])
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'UAT warehouse revision'})
        change.with_user(manager).with_context(allowed_company_ids=manager.company_ids.ids).action_start_review()
        self.assertEqual(change.state, 'under_review')
        self.assertEqual(change.revision_order_id.company_id, self.seller)
        self.assertFalse(change.revision_order_id.warehouse_id)
        result = self.env['sale.order']._b2b_repair_external_warehouses()
        self.assertIn(order.id, result['repaired'])
        self.assertFalse(order.warehouse_id)
        self.assertEqual(order.state, 'sale')
        self.assertNotIn(order.id, self.env['sale.order']._b2b_repair_external_warehouses()['repaired'])
        service = self.env['product.product'].create({'name': 'Warehouse Repair Delivered Service', 'type': 'service'})
        line = self.env['sale.order.line'].create({'order_id': order.id, 'product_id': service.id,
                                                 'product_uom_qty': 1, 'price_unit': 0})
        line.qty_delivered = 1
        order.flush_recordset()
        self.env.cr.execute('UPDATE sale_order SET warehouse_id=%s WHERE id=%s', [warehouse.id, order.id])
        order.invalidate_recordset(['warehouse_id'])
        self.assertIn(order.id, self.env['sale.order']._b2b_repair_external_warehouses()['skipped'])
        self.assertEqual(order.warehouse_id, warehouse)

    def test_odoo_seller_never_uses_other_company_warehouse(self):
        warehouse = self.env['stock.warehouse'].create({'name': 'UAT Seller Warehouse', 'code': 'USWH', 'company_id': self.seller.id})
        order = self.env['sale.order'].create({'website_id': self.website.id, 'partner_id': self.customer.id})
        self.assertEqual(order.warehouse_id.company_id, self.seller)
        foreign = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        with self.assertRaises(UserError), self.cr.savepoint():
            order.warehouse_id = foreign

    def test_five_sellers_share_catalog_not_orders(self):
        sellers = self.env['res.company'].create([{'name': 'UAT Seller %s' % n} for n in range(5)])
        self.website.write({'b2b_selling_company_ids': [Command.set((sellers | self.seller).ids)]})
        product = self.env['product.product'].create({'name': 'UAT Shared Catalog Product', 'company_id': False, 'type': 'consu', 'b2b_visibility_mode': 'all'})
        for seller in sellers:
            brand = self.env['b2b.product.brand'].create({'name': 'UAT Brand %s' % seller.id, 'b2b_selling_company_id': seller.id})
            customer = self.env['res.partner'].create({'name': 'UAT Customer %s' % seller.id, 'is_company': True, 'b2b_selling_company_id': seller.id, 'b2b_account_brand_id': brand.id})
            order = self.env['sale.order'].create({'website_id': self.website.id, 'partner_id': customer.id, 'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 100})]})
            self.assertEqual(order.company_id, seller)
            self.assertEqual(order.order_line.product_id, product)

    def test_layered_price_is_native_and_customer_specific(self):
        self.assertTrue(self.website.b2b_multicompany_enabled)
        category = self.env['b2b.customer.type'].create({'name': 'UAT Multicompany Distributor'})
        base = self.env['product.pricelist'].create({'name': 'UAT Distributor Base', 'company_id': False})
        self.env['b2b.customer.type.pricelist'].create({'customer_type_id': category.id, 'website_id': self.website.id, 'pricelist_id': base.id})
        self.customer.b2b_customer_type_id = category
        effective = self.customer._b2b_get_effective_pricelist(self.website, base.currency_id)
        self.assertTrue(effective)
        self.assertFalse(effective.company_id)
        self.assertEqual(effective.b2b_effective_partner_id, self.customer)
        product = self.env['product.product'].create({'name': 'UAT Layered Product', 'list_price': 100})
        override = self.env['product.pricelist'].create({'name': 'UAT Seller Specific Override', 'company_id': self.seller.id,
            'currency_id': base.currency_id.id, 'item_ids': [Command.create({'applied_on': '0_product_variant', 'product_id': product.id, 'compute_price': 'fixed', 'fixed_price': 80})]})
        self.env['b2b.partner.pricelist.override'].create({'partner_id': self.customer.id, 'website_id': self.website.id, 'pricelist_id': override.id})
        self.assertEqual(effective._compute_price_rule(product, 1)[product.id][0], 80)
