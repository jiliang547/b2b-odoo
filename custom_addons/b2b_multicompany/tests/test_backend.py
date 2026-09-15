from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import Form, tagged
from odoo.addons.b2b_website.tests.test_collection import B2BCollectionCommon


@tagged('post_install', '-at_install')
class TestCustomerFirstBackend(B2BCollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.other_data = cls.setup_other_company()
        cls.other = cls.other_data['company']
        cls.env.user.company_ids = [Command.link(cls.other.id)]
        cls.seller = cls.env.company
        cls.brand.b2b_selling_company_id = cls.seller
        cls.customer.b2b_account_brand_id = cls.brand
        cls.website.write({'b2b_selling_company_ids': [Command.set(cls.seller.ids)],
                           'b2b_fulfilment_mode': 'external'})
        cls.category = cls.env['b2b.customer.type'].create({'name': 'Backend UAT category'})
        cls.base_price = cls.env['product.pricelist'].create({
            'name': 'Backend UAT base', 'company_id': False,
            'currency_id': cls.seller.currency_id.id,
            'item_ids': [Command.create({'compute_price': 'fixed', 'fixed_price': 80})]})
        cls.env['b2b.customer.type.pricelist'].sudo().create({
            'customer_type_id': cls.category.id, 'website_id': cls.website.id,
            'pricelist_id': cls.base_price.id})
        cls.customer.b2b_customer_type_id = cls.category
        cls.customer.b2b_collection_policy_id = cls.env.ref('b2b_website.collection_policy_c')
        cls.sales = cls.env['sale.order'].with_context(allowed_company_ids=[cls.other.id, cls.seller.id])

    def test_brand_alone_assigns_company(self):
        self.assertEqual(self.customer.b2b_selling_company_id, self.seller)
        contact = self.env['res.partner'].create({'name': 'Backend UAT contact', 'parent_id': self.customer.id})
        self.assertEqual(contact._b2b_backend_seller(), self.seller)

    def test_new_quote_routes_and_initializes_collection(self):
        order = self.sales.create({'partner_id': self.customer.id, 'b2b_backend_order': True})
        self.assertEqual(order.company_id, self.seller)
        self.assertEqual(order.website_id, self.website)
        self.assertEqual(order.b2b_fulfilment_mode, 'external')
        self.assertTrue(order.b2b_backend_order)
        self.assertTrue(order.b2b_collection_active)
        self.assertEqual(order.b2b_receiving_journal_id, self.journal)
        self.assertEqual(order.pricelist_id.b2b_effective_partner_id, self.customer)
        self.assertEqual(self.sales.env.company, self.other)

    def test_native_quote_form_customer_first(self):
        with Form(self.sales) as form:
            form.partner_id = self.customer
            self.assertEqual(form.company_id, self.seller)
            with form.order_line.new() as line:
                line.product_id = self.product
                line.product_uom_qty = 1
        order = form.record
        self.assertTrue(order.b2b_backend_order)
        self.assertEqual(order.order_line.price_unit, 80)
        order.action_confirm()
        self.assertFalse(order.picking_ids)
        self.assertFalse(order.order_line.purchase_line_ids)
        self.assertEqual(order._prepare_invoice()['company_id'], self.seller.id)
        self.assertEqual(order._prepare_invoice()['partner_bank_id'], self.journal.bank_account_id.id)

    def test_company_mismatch_cannot_save(self):
        with self.assertRaises(ValidationError):
            self.sales.create({'partner_id': self.customer.id, 'company_id': self.other.id, 'b2b_backend_order': True})

    def test_missing_pricing_blocks_quote(self):
        customer = self.env['res.partner'].create({'name': 'Backend UAT no prices', 'is_company': True,
                                                  'b2b_account_brand_id': self.brand.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.sales.create({'partner_id': customer.id, 'b2b_backend_order': True})

    def test_saved_quote_cannot_reassign_customer_or_price_agreement(self):
        order = self.sales.create({'partner_id': self.customer.id, 'b2b_backend_order': True})
        other_customer = self.env['res.partner'].create({'name': 'Backend UAT another buyer', 'is_company': True,
            'b2b_account_brand_id': self.brand.id})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.partner_id = other_customer
        with self.assertRaises(ValidationError), self.cr.savepoint():
            order.pricelist_id = self.base_price

    def test_multiple_websites_require_choice(self):
        self.website.copy({'name': 'Backend UAT ambiguous', 'b2b_selling_company_ids': [Command.set(self.seller.ids)]})
        with self.assertRaises(ValidationError):
            self.customer._b2b_backend_website()
        self.assertEqual(self.customer._b2b_backend_website(self.website), self.website)

    def test_restricted_and_unselected_company(self):
        restricted = self.env['res.users'].sudo().create({
            'name': 'Backend UAT restricted', 'login': 'backend-uat-restricted',
            'company_id': self.other.id, 'company_ids': [Command.set(self.other.ids)],
            'group_ids': [Command.set(self.env.ref('b2b_core.group_b2b_manager').ids)]})
        with self.assertRaises(AccessError):
            self.customer.with_user(restricted).with_context(allowed_company_ids=self.other.ids)._b2b_backend_seller()
        restricted.sudo().company_ids = [Command.link(self.seller.id)]
        with self.assertRaises(ValidationError):
            self.customer.with_user(restricted).with_context(allowed_company_ids=self.other.ids)._b2b_backend_seller()

    def test_financial_native_forms(self):
        context = dict(allowed_company_ids=[self.other.id, self.seller.id])
        with Form(self.env['account.move'].with_context(**context, default_move_type='out_invoice')) as invoice:
            invoice.partner_id = self.customer
            self.assertEqual(invoice.company_id, self.seller)
            self.assertEqual(invoice.journal_id.company_id, self.seller)
        with Form(self.env['account.payment'].with_context(**context, default_payment_type='inbound', default_partner_type='customer')) as payment:
            payment.partner_id = self.customer
            self.assertEqual(payment.company_id, self.seller)
            self.assertEqual(payment.journal_id, self.journal)
            payment.amount = 10

    def test_saved_invoice_does_not_follow_new_assignment(self):
        invoice = self.env['account.move'].create({'move_type': 'out_invoice', 'partner_id': self.customer.id,
            'company_id': self.other.id, 'journal_id': self.other_data['default_journal_sale'].id})
        with Form(invoice) as form:
            form.ref = 'Keep original seller'
        self.assertEqual(invoice.company_id, self.other)

    def test_ordinary_customer_keeps_native_quote(self):
        customer = self.env['res.partner'].create({'name': 'Backend UAT non-hub customer'})
        order = self.sales.create({'partner_id': customer.id})
        self.assertEqual(order.company_id, self.other)
        self.assertFalse(order.website_id)
        self.assertFalse(order.b2b_backend_order)

    def test_standalone_invoice_suggests_company(self):
        invoice = self.env['account.move'].with_context(allowed_company_ids=[self.other.id, self.seller.id]).new({
            'move_type': 'out_invoice', 'company_id': self.other.id,
            'journal_id': self.other_data['default_journal_sale'].id, 'partner_id': self.customer.id})
        invoice._onchange_b2b_customer_company()
        self.assertEqual(invoice.company_id, self.seller)
        self.assertEqual(invoice.journal_id.company_id, self.seller)

    def test_standalone_receipt_suggests_company_and_bank(self):
        payment = self.env['account.payment'].with_context(allowed_company_ids=[self.other.id, self.seller.id]).new({
            'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.customer.id,
            'company_id': self.other.id, 'journal_id': self.other_data['default_journal_bank'].id,
            'currency_id': self.seller.currency_id.id})
        payment._onchange_b2b_customer_company()
        self.assertEqual(payment.company_id, self.seller)
        self.assertEqual(payment.journal_id, self.journal)

    def test_source_defaults_and_refunds_never_redirect(self):
        for kind in ('inbound', 'outbound'):
            payment = self.env['account.payment'].with_context(default_company_id=self.other.id).new({
                'payment_type': kind, 'partner_type': 'customer', 'partner_id': self.customer.id,
                'company_id': self.other.id, 'journal_id': self.other_data['default_journal_bank'].id})
            payment._onchange_b2b_customer_company()
            self.assertEqual(payment.company_id, self.other)
        invoice = self.env['account.move'].new({'move_type': 'out_refund', 'partner_id': self.customer.id,
            'company_id': self.other.id, 'journal_id': self.other_data['default_journal_sale'].id})
        invoice._onchange_b2b_customer_company()
        self.assertEqual(invoice.company_id, self.other)

    def test_refund_action_uses_original_order_company(self):
        order = self.sales.create({'partner_id': self.customer.id, 'b2b_backend_order': True,
            'order_line': [Command.create({'product_id': self.product.id, 'price_unit': 80})]})
        order.action_confirm()
        change = self.env['b2b.order.change.request'].create({
            'order_id': order.id, 'requested_changes': 'UAT refund'})
        change.sudo().write({'state': 'finance_review', 'collection_adjustment': True, 'refund_amount': 10})
        action = change.action_b2b_open_bank_refund()
        self.assertEqual(action['context']['default_company_id'], order.company_id.id)
        self.assertEqual(action['context']['default_journal_id'], order.b2b_receiving_journal_id.id)
        self.assertEqual(action['context']['default_payment_type'], 'outbound')
        self.assertFalse(change.refund_payment_id)
        change.sudo().state = 'completed'
        with self.assertRaises(ValidationError):
            change.action_b2b_open_bank_refund()
