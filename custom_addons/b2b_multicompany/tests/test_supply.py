from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.addons.b2b_website.tests.test_collection import B2BCollectionCommon


@tagged('post_install', '-at_install')
class TestFactorySupply(B2BCollectionCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.factory = cls.env['res.company'].create({
            'name': 'UAT Factory Supply',
            'intercompany_generate_sales_orders': True,
            'intercompany_user_id': cls.env.ref('base.user_root').id,
            'intercompany_document_state': 'draft',
        })
        cls.factory.intercompany_warehouse_id = cls.env['stock.warehouse'].search([('company_id', '=', cls.factory.id)], limit=1) or cls.env['stock.warehouse'].create({
            'name': 'UAT Factory Warehouse', 'code': 'UFW', 'company_id': cls.factory.id})
        cls.brand.b2b_selling_company_id = cls.env.company
        cls.customer.b2b_selling_company_id = cls.env.company
        cls.website.write({
            'b2b_fulfilment_mode': 'odoo',
            'b2b_selling_company_ids': [Command.set(cls.env.company.ids)],
            'b2b_factory_company_id': cls.factory.id,
        })
        cls.supplier = cls.env['product.supplierinfo'].create({
            'partner_id': cls.factory.partner_id.id,
            'product_tmpl_id': cls.product.product_tmpl_id.id,
            'company_id': cls.env.company.id, 'price': 40,
            'currency_id': cls.env.company.currency_id.id,
        })
        # Native intercompany requires the selling company's customer
        # pricelist on the factory side to use the PO currency.
        cls.internal_pricelist = cls.env['product.pricelist'].create({
            'name': 'UAT Internal Supply Currency', 'company_id': cls.factory.id,
            'currency_id': cls.env.company.currency_id.id})
        cls.env.company.partner_id.with_company(cls.factory).property_product_pricelist = cls.internal_pricelist

    def test_native_factory_documents_and_shipment_hold(self):
        order = self._order('c')
        order.action_confirm()
        purchase = order.order_line.purchase_line_ids.order_id
        self.assertEqual(len(purchase), 1)
        self.assertEqual(purchase.company_id, order.company_id)
        self.assertEqual(purchase.partner_id, self.factory.partner_id)
        self.assertEqual(purchase.order_line.price_unit, 40)
        self.assertEqual(purchase.picking_type_id.code, 'dropship')
        purchase.button_confirm()
        factory_sale = self.env['sale.order'].sudo().search([('auto_purchase_order_id', '=', purchase.id)])
        self.assertEqual(len(factory_sale), 1)
        self.assertEqual(factory_sale.company_id, self.factory)
        self.assertEqual(factory_sale.partner_shipping_id, order.partner_shipping_id)
        self.assertFalse(factory_sale.website_id)
        factory_sale.action_confirm()
        self.assertTrue(factory_sale.picking_ids)
        with self.assertRaises(UserError):
            factory_sale.picking_ids._b2b_check_collection_release()
        with self.assertRaises(UserError):
            purchase.picking_ids._b2b_check_collection_release()
        receipt = self._receipt(order, order.amount_total)
        receipt.action_confirm_receipt()
        factory_sale.picking_ids._b2b_check_collection_release()
        with self.assertRaises(UserError):
            purchase.picking_ids._b2b_check_collection_release()
        factory_sale.picking_ids.move_ids.quantity = 1
        factory_sale.picking_ids.move_ids.picked = True
        factory_sale.picking_ids.button_validate()
        purchase.picking_ids.move_ids.quantity = 1
        purchase.picking_ids.move_ids.picked = True
        purchase.picking_ids.button_validate()
        self.assertEqual(order.order_line.qty_delivered, 1)

    def test_missing_supply_price_blocks_production(self):
        self.supplier.unlink()
        order = self._order('c')
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_external_erp_needs_no_factory_or_local_stock(self):
        self.website.write({'b2b_fulfilment_mode': 'external', 'b2b_factory_company_id': False})
        self.supplier.unlink()
        order = self._order('c')
        self.assertEqual(order.b2b_fulfilment_mode, 'external')
        self.assertFalse(order.b2b_fulfilment_factory_id)
        order.warehouse_id = False
        order.action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.picking_ids)
        self.assertFalse(order.order_line.purchase_line_ids)
        order.order_line.product_uom_qty = 2
        self.assertFalse(order.picking_ids)
        self.assertFalse(order.order_line.purchase_line_ids)

    def test_provider_switch_preserves_existing_order(self):
        old = self._order('c')
        self.website.b2b_fulfilment_mode = 'external'
        new = self._order('c')
        self.assertEqual(old.b2b_fulfilment_mode, 'odoo')
        self.assertEqual(old.b2b_fulfilment_factory_id, self.factory)
        self.assertEqual(new.b2b_fulfilment_mode, 'external')
        old.action_confirm()
        new.action_confirm()
        self.assertTrue(old.order_line.purchase_line_ids)
        self.assertFalse(new.order_line.purchase_line_ids)

    def test_external_change_requires_permission_and_remains_pending(self):
        self.website.write({'b2b_fulfilment_mode': 'external', 'b2b_factory_company_id': False})
        order = self._order('c')
        order.action_confirm()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'External revision'})
        change.action_start_review()
        change.revision_order_id.order_line.product_uom_qty = 2
        with self.assertRaisesRegex(UserError, 'Open the Factory Permission tab'):
            change.action_send_proposal()
        change.b2b_factory_permission_note = 'External provider approved REF-EXTERNAL'
        change.action_confirm_factory_permission()
        change.action_send_proposal()
        change.with_user(self.portal_user).action_customer_accept()
        self.assertTrue(order.b2b_external_change_pending)
        self.assertEqual(order.order_line.product_uom_qty, 2)
        self.assertFalse(order.picking_ids)
        self.assertFalse(order.order_line.purchase_line_ids)

    def test_operator_cannot_change_customer_seller(self):
        with self.assertRaises(AccessError):
            self.customer.with_user(self.operator).write({'b2b_selling_company_id': self.factory.id})

    def test_operator_cannot_enable_routing(self):
        with self.assertRaises(AccessError):
            self.website.with_user(self.operator).write({'b2b_factory_company_id': False})

    def test_confirmed_supply_quantity_cannot_be_silently_changed(self):
        order = self._order('c')
        order.action_confirm()
        with self.assertRaises(UserError):
            order.order_line.product_uom_qty = 2

    def test_credit_delivery_posts_selling_company_receivable(self):
        order = self._order('d')
        order.action_confirm()
        purchase = order.order_line.purchase_line_ids.order_id
        purchase.button_confirm()
        factory_sale = self.env['sale.order'].sudo().search([('auto_purchase_order_id', '=', purchase.id)])
        factory_sale.action_confirm()
        factory_sale.picking_ids.move_ids.quantity = 1
        factory_sale.picking_ids.move_ids.picked = True
        factory_sale.picking_ids.button_validate()
        purchase.picking_ids.move_ids.quantity = 1
        purchase.picking_ids.move_ids.picked = True
        purchase.picking_ids.button_validate()
        invoices = order.invoice_ids.filtered(lambda i: i.state == 'posted')
        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices.company_id, order.company_id)
        self.assertEqual(invoices.partner_bank_id, self.journal.bank_account_id)
        self.assertEqual(invoices.amount_residual, order.amount_total)

    def test_prepaid_deposit_and_special_terms_gate_factory(self):
        self.env.ref('b2b_website.collection_policy_e').write({
            'production_percent': 25, 'shipment_percent': 75,
            'payment_term_id': self.env.ref('b2b_website.collection_net30').id})
        for policy, deposit, before_shipping in [('a', 100, 100), ('b30', 30, 100), ('b20', 20, 100), ('e', 25, 75)]:
            with self.subTest(policy=policy):
                order = self._order(policy)
                with self.assertRaises(UserError):
                    order.action_confirm()
                self.assertFalse(order.order_line.purchase_line_ids)
                self._receipt(order, deposit).action_confirm_receipt()
                self.assertEqual(order.state, 'sale')
                purchase = order.order_line.purchase_line_ids.order_id
                purchase.button_confirm()
                factory_sale = self.env['sale.order'].sudo().search([('auto_purchase_order_id', '=', purchase.id)])
                factory_sale.action_confirm()
                if deposit < before_shipping:
                    with self.assertRaises(UserError):
                        factory_sale.picking_ids._b2b_check_collection_release()
                    self._receipt(order, before_shipping - deposit).action_confirm_receipt()
                factory_sale.picking_ids._b2b_check_collection_release()

    def _factory_change(self):
        order = self._order('c')
        order.action_confirm()
        purchase = order.order_line.purchase_line_ids.order_id
        purchase.button_confirm()
        factory = self.env['sale.order'].sudo().search([('auto_purchase_order_id', '=', purchase.id)])
        factory.action_confirm()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'Increase quantity to two'})
        change.action_start_review()
        change.revision_order_id.order_line.product_uom_qty = 2
        return order, purchase, factory, change

    def test_factory_permission_required_and_revision_invalidates_it(self):
        order, purchase, factory, change = self._factory_change()
        with self.assertRaises(UserError):
            change.action_send_proposal()
        change.b2b_factory_permission_note = 'UAT factory supervisor permits two units'
        change.action_confirm_factory_permission()
        change.revision_order_id.order_line.product_uom_qty = 3
        with self.assertRaises(UserError):
            change.action_send_proposal()
        self.assertEqual(purchase.state, 'purchase')
        self.assertEqual(factory.state, 'sale')

    def test_factory_permission_acceptance_rebuilds_supply(self):
        order, purchase, factory, change = self._factory_change()
        change.b2b_factory_permission_note = 'UAT factory supervisor approval REF-2'
        change.action_confirm_factory_permission()
        change.action_send_proposal()
        self.assertEqual(factory.state, 'sale')
        change.with_user(self.portal_user).action_customer_accept()
        self.assertEqual(factory.state, 'cancel')
        self.assertEqual(purchase.state, 'cancel')
        self.assertEqual(order.order_line.product_uom_qty, 2)
        replacements = order.order_line.purchase_line_ids.order_id.filtered(lambda p: p.state != 'cancel')
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements.order_line.product_qty, 2)

    def test_factory_permission_decline_keeps_supply(self):
        order, purchase, factory, change = self._factory_change()
        change.b2b_factory_permission_note = 'UAT factory approval'
        change.action_confirm_factory_permission()
        change.action_send_proposal()
        change.with_user(self.portal_user).action_customer_cancel()
        self.assertEqual(factory.state, 'sale')
        self.assertEqual(purchase.state, 'purchase')
        self.assertEqual(order.order_line.product_uom_qty, 1)

    def test_operator_cannot_attest_or_forge_factory_permission(self):
        _order, _purchase, _factory, change = self._factory_change()
        with self.assertRaises(AccessError):
            change.with_user(self.operator).action_confirm_factory_permission()
        with self.assertRaises(UserError):
            change.write({'b2b_factory_permission_by': self.operator.id})
