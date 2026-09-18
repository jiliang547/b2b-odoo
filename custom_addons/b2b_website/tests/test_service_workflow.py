from odoo import Command, fields
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPartnerServiceWorkflow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env['res.partner'].create({'name': 'Service test customer'})
        cls.user = mail_new_test_user(cls.env, login='service-portal-test', groups='base.group_portal', partner_id=cls.customer.id)
        cls.order = cls.env['sale.order'].create({'partner_id': cls.customer.id})
        cls.product = cls.env['product.product'].create({'name': 'Service test product'})

    def new_ticket(self):
        return self.env['helpdesk.ticket'].create({
            'name': 'Service workflow test', 'partner_id': self.customer.id,
            'b2b_sale_order_id': self.order.id, 'b2b_product_id': self.product.id,
            'b2b_request_type': 'repair',
        })

    def test_native_demo_delivery_without_reserved_stock(self):
        product = self.env['product.product'].create({
            'name': 'Isolated demo stock product', 'type': 'consu',
            'is_storable': True, 'tracking': 'none',
        })
        line = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': product.id, 'product_uom_qty': 1,
        })
        xmlid = self.env['ir.model.data'].sudo().search([
            ('module', '=', 'helpdesk_sale'), ('name', '=', 'sale_order_line_helpdesk_3'),
        ])
        if xmlid:
            xmlid.write({'res_id': line.id})
        else:
            self.env['ir.model.data'].sudo().create({
                'module': 'helpdesk_sale', 'name': 'sale_order_line_helpdesk_3',
                'model': 'sale.order.line', 'res_id': line.id,
            })
        self.env.flush_all()
        self.env.registry.clear_cache()
        self.order.sudo().with_context(install_demo=True).action_confirm()
        self.assertTrue(line.move_ids)
        self.assertEqual(sum(line.move_ids.mapped('quantity')), 1)
        line.move_ids.picking_id.sudo().with_context(install_demo=True).button_validate()
        self.assertTrue(all(p.state == 'done' for p in line.move_ids.picking_id))

    def test_ordinary_delivery_is_not_given_demo_quantities(self):
        product = self.env['product.product'].create({
            'name': 'Isolated real stock product', 'type': 'consu', 'is_storable': True,
        })
        line = self.env['sale.order.line'].create({
            'order_id': self.order.id, 'product_id': product.id, 'product_uom_qty': 1,
        })
        self.order.sudo().with_context(install_demo=True).action_confirm()
        self.assertTrue(line.move_ids)
        self.assertFalse(any(line.move_ids.mapped('quantity')))

    def test_external_round_trip_and_duplicate_shipment(self):
        ticket = self.new_ticket()
        self.assertEqual(ticket.company_id, self.order.company_id)
        self.assertEqual(ticket.product_id, self.product)
        ticket.action_b2b_review()
        with self.assertRaises(ValidationError):
            ticket.action_b2b_approve()
        ticket.b2b_return_instructions = 'UAT receiving address'
        ticket.action_b2b_approve()
        ticket._b2b_submit_tracking('DHL', 'UAT123', fields.Date.today())
        with self.assertRaises(ValidationError):
            ticket._b2b_submit_tracking('DHL', 'UAT123', fields.Date.today())
        with self.assertRaises(ValidationError):
            ticket.action_b2b_received()
        ticket.b2b_receipt_note = 'One unit received; serial checked.'
        ticket.action_b2b_received()
        ticket.action_b2b_process()
        with self.assertRaises(ValidationError):
            ticket.action_b2b_ship()
        ticket.write({'b2b_resolution_note': 'Repaired and tested', 'b2b_outbound_carrier': 'DHL',
                      'b2b_outbound_tracking': 'UAT456', 'b2b_outbound_date': fields.Date.today()})
        ticket.action_b2b_ship()
        ticket.action_b2b_complete()
        self.assertTrue(ticket.stage_id.fold)
        self.assertFalse(ticket.picking_ids)
        self.assertFalse(ticket.repair_ids)

    def test_customer_cannot_approve_or_forge_stage(self):
        ticket = self.new_ticket().with_user(self.user)
        with self.assertRaises(AccessError):
            ticket.action_b2b_review()
        with self.assertRaises(AccessError):
            ticket.write({'stage_id': self.env.ref('b2b_website.service_completed').id})

    def test_stage_drag_cannot_skip_receipt(self):
        ticket = self.new_ticket()
        with self.assertRaises(ValidationError):
            ticket.write({'stage_id': self.env.ref('b2b_website.service_shipped').id})

    def test_repeated_staff_action_does_not_duplicate_notification(self):
        ticket = self.new_ticket()
        ticket.action_b2b_review()
        messages = ticket.message_ids
        ticket.action_b2b_review()
        self.assertEqual(ticket.message_ids, messages)

    def test_service_order_cannot_belong_to_another_customer(self):
        other = self.env['res.partner'].create({'name': 'Other service customer'})
        with self.assertRaises(ValidationError):
            self.env['helpdesk.ticket'].create({'name': 'Wrong customer', 'partner_id': other.id,
                                               'b2b_sale_order_id': self.order.id, 'b2b_request_type': 'repair'})

    def test_rejection_requires_reason_and_does_not_create_stock(self):
        ticket = self.new_ticket()
        with self.assertRaises(ValidationError):
            ticket.action_b2b_reject()
        ticket.b2b_resolution_note = 'Duplicate request; please use the original case.'
        ticket.action_b2b_reject()
        self.assertEqual(ticket.b2b_service_step, 'rejected')
        self.assertFalse(ticket.picking_ids)

    def test_company_team_is_reused(self):
        first, second = self.new_ticket(), self.new_ticket()
        self.assertEqual(first.team_id, second.team_id)
        self.assertEqual(first.team_id.privacy_visibility, 'portal')
        self.assertFalse(first.team_id.allow_portal_ticket_closing)

    def test_native_repair_bridge_is_installed(self):
        self.assertIn('picking_ids', self.env['helpdesk.ticket']._fields)
        self.assertIn('repair_ids', self.env['helpdesk.ticket']._fields)

    def test_native_return_repair_delivery_round_trip(self):
        if 'b2b_fulfilment_mode' not in self.order._fields:
            self.skipTest('Fulfilment provider bridge is not installed')
        # Seed the immutable provider snapshot on this isolated test order.
        # Exercise real stock/repair actions without unrelated accounting fixtures.
        self.order.flush_recordset()
        self.env.cr.execute("UPDATE sale_order SET b2b_fulfilment_mode = 'odoo' WHERE id = %s", [self.order.id])
        self.order.invalidate_recordset()
        ticket = self.new_ticket()
        self.assertEqual(ticket.b2b_fulfilment_mode, 'odoo')
        ticket.action_b2b_review()
        ticket.b2b_return_instructions = 'Return to service warehouse'
        ticket.action_b2b_approve()
        ticket._b2b_submit_tracking('UAT carrier', 'IN-001', fields.Date.today())
        ticket.b2b_receipt_note = 'One unit received'
        with self.assertRaises(ValidationError):
            ticket.action_b2b_received()
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.order.company_id.id)], limit=1)
        customer_location = self.env.ref('stock.stock_location_customers')
        receipt = self.env['stock.picking'].create({
            'ticket_id': ticket.id, 'partner_id': self.customer.id,
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': customer_location.id, 'location_dest_id': warehouse.lot_stock_id.id,
            'move_ids': [Command.create({'product_id': self.product.id,
                'product_uom_qty': 1, 'product_uom': self.product.uom_id.id,
                'location_id': customer_location.id, 'location_dest_id': warehouse.lot_stock_id.id})],
        })
        ticket.picking_ids = [Command.link(receipt.id)]
        receipt.action_confirm()
        receipt.move_ids.quantity = 1
        receipt.move_ids.picked = True
        receipt.button_validate()
        ticket.action_b2b_received()
        ticket.action_b2b_process()
        repair_action = ticket.action_repair_order_form()
        repair = self.env['repair.order'].with_context(**repair_action['context']).create({
            'product_id': self.product.id, 'product_qty': 1, 'picking_type_id': warehouse.repair_type_id.id,
        })
        repair.action_validate()
        repair.action_repair_start()
        repair.action_repair_end()
        self.assertEqual(repair.state, 'done')
        self.assertEqual(repair.ticket_id, ticket)
        delivery = self.env['stock.picking'].with_context(replacement_create_trigger=True).create({
            'ticket_id': ticket.id, 'is_replacement': True, 'partner_id': self.customer.id,
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id, 'location_dest_id': customer_location.id,
            'carrier_tracking_ref': 'OUT-001',
            'move_ids': [Command.create({'product_id': self.product.id,
                'product_uom_qty': 1, 'product_uom': self.product.uom_id.id,
                'location_id': warehouse.lot_stock_id.id, 'location_dest_id': customer_location.id})],
        })
        delivery.action_confirm()
        delivery.move_ids.quantity = 1
        delivery.move_ids.picked = True
        delivery.button_validate()
        ticket.write({'b2b_resolution_note': 'Repaired and tested', 'b2b_outbound_carrier': 'UAT carrier'})
        ticket.action_b2b_ship()
        self.assertEqual(ticket.b2b_outbound_tracking, delivery.carrier_tracking_ref)
        ticket.action_b2b_complete()
        self.assertEqual(ticket.b2b_service_step, 'completed')

    def test_cross_company_portal_visibility_preserves_ownership(self):
        if not self.env['ir.module.module'].search_count([('name', '=', 'b2b_multicompany'), ('state', '=', 'installed')]):
            self.skipTest('Multi-company bridge not installed')
        other_company = self.env['res.company'].create({'name': 'Service second legal seller'})
        order = self.env['sale.order'].with_company(other_company).create({'partner_id': self.customer.id})
        ticket = self.env['helpdesk.ticket'].create({
            'name': 'Cross-company service', 'partner_id': self.customer.id,
            'b2b_sale_order_id': order.id, 'b2b_request_type': 'replacement',
        })
        self.assertEqual(ticket.company_id, other_company)
        portal_tickets = self.env['helpdesk.ticket'].with_user(self.user).with_context(allowed_company_ids=self.user.company_ids.ids)
        self.assertEqual(portal_tickets.search([('id', '=', ticket.id)]), ticket)
        stranger = mail_new_test_user(self.env, login='service-stranger', groups='base.group_portal')
        self.assertFalse(self.env['helpdesk.ticket'].with_user(stranger).search([('id', '=', ticket.id)]))

    def test_future_shipment_rejected(self):
        from datetime import timedelta
        ticket = self.new_ticket()
        ticket.action_b2b_review()
        ticket.b2b_return_instructions = 'Return to UAT warehouse'
        ticket.action_b2b_approve()
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            ticket._b2b_submit_tracking('DHL', 'UAT', fields.Date.today() + timedelta(days=1))
        self.assertEqual(ticket.b2b_service_step, 'approved')

    def test_external_cannot_accidentally_create_native_stock(self):
        ticket = self.new_ticket()
        with self.assertRaises(ValidationError):
            ticket.action_repair_order_form()
        with self.assertRaises(ValidationError):
            ticket.action_create_replacement()
