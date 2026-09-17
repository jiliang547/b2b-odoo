"""Native dropship procurement and intercompany documents, with release gates."""
import hashlib
import json
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _b2b_external_supply_orders(self):
        purchases = self.sudo().auto_purchase_order_id
        return (purchases.b2b_customer_order_id | purchases.order_line.sale_line_id.order_id).filtered('b2b_routed_company')

    def _action_confirm(self):
        for order in self:
            external = order._b2b_external_supply_orders()
            for customer_order in external:
                customer_order._b2b_lock_collection()
                if not customer_order._b2b_can_produce():
                    raise UserError(_('Factory production is blocked by the customer order payment or review requirements.'))
            if order.b2b_fulfilment_mode == 'odoo' and not order.b2b_is_change_revision:
                factory = order.b2b_fulfilment_factory_id
                if not factory.intercompany_generate_sales_orders or not factory.intercompany_user_id or not factory.intercompany_warehouse_id:
                    raise UserError(_('Configure native intercompany sales, an intercompany user and the factory warehouse before production.'))
                if factory == order.company_id:
                    raise UserError(_('The factory must be separate from the selling company.'))
                goods = order.order_line.filtered(lambda l: not l.display_type and l.product_id.type == 'consu')
                for line in goods:
                    line._b2b_factory_supplier()
                goods.write({'route_ids': [Command.set(self.env.ref('stock_dropshipping.route_drop_shipping').ids)]})
        return super()._action_confirm()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    b2b_supply_purchase_line_id = fields.Many2one(
        'purchase.order.line', readonly=True, copy=False, ondelete='restrict',
        string='Originating Factory Purchase Line')

    def _b2b_check_supply_edit(self):
        for line in self.filtered(lambda l: l.order_id.b2b_routed_company and l.order_id.state == 'sale'):
            if line.sudo().purchase_line_ids.order_id.filtered(lambda p: p.state != 'cancel'):
                raise UserError(_('Review and cancel the linked factory supply documents before changing ordered products or quantities.'))

    def write(self, vals):
        changed = self.filtered(lambda line: any(
            key in vals and (line[key].id if key in ('product_id', 'product_uom_id') else line[key]) != vals[key]
            for key in ('product_id', 'product_uom_id', 'product_uom_qty')
        ))
        changed._b2b_check_supply_edit()
        return super().write(vals)

    def unlink(self):
        self._b2b_check_supply_edit()
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            order = self.env['sale.order'].browse(vals.get('order_id'))
            if order.b2b_fulfilment_mode == 'odoo' and not order.b2b_is_change_revision and vals.get('product_id'):
                product = self.env['product.product'].browse(vals['product_id'])
                if product.type == 'consu':
                    vals['route_ids'] = [Command.set(self.env.ref('stock_dropshipping.route_drop_shipping').ids)]
            prepared.append(vals)
        return super().create(prepared)

    def _b2b_factory_supplier(self):
        self.ensure_one()
        factory = self.order_id.b2b_fulfilment_factory_id
        if self.product_id.company_id:
            raise UserError(_('Products sold through multiple sellers must be shared products: %s', self.product_id.display_name))
        supplier = self.product_id.sudo().with_company(self.company_id)._select_seller(
            partner_id=factory.partner_id, quantity=self.product_uom_qty,
            date=self.order_id.date_order.date(), uom_id=self.product_uom_id,
        )
        if not supplier or supplier.price <= 0:
            raise UserError(_('Configure a positive native factory vendor price for %s. Customer prices are not used as internal supply prices.', self.product_id.display_name))
        return supplier

    def _prepare_procurement_values(self):
        values = super()._prepare_procurement_values()
        if self.order_id.b2b_fulfilment_mode == 'odoo' and self.product_id.type == 'consu':
            values['supplierinfo_id'] = self._b2b_factory_supplier()
        return values


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    b2b_customer_order_id = fields.Many2one('sale.order', string='External Customer Order', readonly=True, copy=False, ondelete='restrict')

    def _prepare_sale_order_line_data(self, line, company):
        values = super()._prepare_sale_order_line_data(line, company)
        if line.sale_line_id.order_id.b2b_routed_company:
            values['b2b_supply_purchase_line_id'] = line.id
        return values

    def _prepare_sale_order_data(self, name, partner, company, direct_delivery_address):
        values = super()._prepare_sale_order_data(name, partner, company, direct_delivery_address)
        orders = self.order_line.sale_line_id.order_id.filtered('b2b_routed_company')
        if orders:
            if len(orders) != 1:
                raise UserError(_('Keep each customer order on its own factory purchase order.'))
            if orders.b2b_fulfilment_factory_id != company:
                raise UserError(_('The supplier must be the configured stock-owning factory.'))
            values['partner_shipping_id'] = orders.partner_shipping_id.id
        return values


class StockRule(models.Model):
    _inherit = 'stock.rule'

    def _prepare_purchase_order(self, company_id, origins, values):
        result = super()._prepare_purchase_order(company_id, origins, values)
        lines = self.env['sale.order.line'].sudo().browse([v['sale_line_id'] for v in values if v.get('sale_line_id')])
        orders = lines.order_id.filtered('b2b_routed_company')
        if orders:
            if len(orders) != 1:
                raise UserError(_('Keep each customer order on a separate factory purchase order.'))
            result['b2b_customer_order_id'] = orders.id
        return result


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def _b2b_customer_release_orders(self):
        orders = self.sudo().sale_id._b2b_external_supply_orders()
        orders |= self.sudo().move_ids.purchase_line_id.sale_line_id.order_id.filtered('b2b_routed_company')
        return orders

    def _b2b_check_collection_release(self):
        super()._b2b_check_collection_release()
        for picking in self.filtered(lambda p: p.picking_type_id.code in ('outgoing', 'dropship')):
            for order in picking._b2b_customer_release_orders():
                order._b2b_lock_collection()
                if not order.b2b_collection_active or not order._b2b_can_ship():
                    raise UserError(_('Factory shipment blocked: the customer order has an unpaid balance, an unresolved change/refund, or a credit hold.'))
            if picking.picking_type_id.code == 'dropship':
                for move in picking.sudo().move_ids.filtered(lambda m: m.purchase_line_id.sale_line_id.order_id.b2b_routed_company and m.state not in ('done', 'cancel')):
                    factory_lines = self.env['sale.order.line'].sudo().search([
                        ('b2b_supply_purchase_line_id', '=', move.purchase_line_id.id),
                        ('state', '=', 'sale'),
                    ])
                    delivered = sum(line.product_uom_id._compute_quantity(line.qty_delivered, move.product_uom) for line in factory_lines)
                    recorded = sum(previous.product_uom._compute_quantity(previous.quantity, move.product_uom)
                                   for previous in move.purchase_line_id.move_ids.filtered(lambda m: m.state == 'done' and m.location_dest_id.usage == 'customer'))
                    if move.product_uom.compare(delivered - recorded, move.quantity) < 0 or delivered <= 0:
                        raise UserError(_('Validate the actual factory delivery before completing the linked dropship record.'))

    def _action_done(self):
        result = super()._action_done()
        orders = self.filtered(lambda p: p.state == 'done' and p.picking_type_id.code == 'dropship')._b2b_customer_release_orders()
        for order in orders.filtered(lambda o: o.b2b_collection_active and o.b2b_shipment_percent < 100):
            invoices = order.sudo().with_company(order.company_id).with_context(raise_if_nothing_to_invoice=False)._create_invoices(final=True)
            invoices.action_post()
            for invoice in invoices:
                invoice.activity_schedule('mail.mail_activity_data_todo', summary=_('Review credit-customer receivable and due date'), user_id=invoice.invoice_user_id.id or self.env.uid)
        return result


class OrderChange(models.Model):
    _inherit = 'b2b.order.change.request'

    b2b_factory_permission_note = fields.Text(string='Factory Permission / Reference', copy=False)
    b2b_factory_permission_by = fields.Many2one('res.users', string='Factory Permission Confirmed By', readonly=True, copy=False)
    b2b_factory_permission_at = fields.Datetime(string='Factory Permission Confirmed At', readonly=True, copy=False)
    b2b_factory_permission_digest = fields.Char(readonly=True, copy=False)
    b2b_factory_change = fields.Boolean(related='order_id.b2b_routed_company')

    @api.constrains('order_id', 'assigned_user_id')
    def _check_assigned_company_manager(self):
        for change in self.filtered(lambda r: r.order_id.b2b_routed_company and r.assigned_user_id):
            assigned = change.assigned_user_id.sudo()
            if change.order_id.company_id not in assigned.company_ids or not assigned.has_group('b2b_core.group_b2b_manager'):
                raise UserError(_('Assign a B2B Manager with access to the order selling company.'))

    def _b2b_supply_documents(self):
        self.ensure_one()
        purchases = self.env['purchase.order'].sudo().search([
            ('b2b_customer_order_id', '=', self.order_id.id), ('state', '!=', 'cancel')])
        purchases |= self.order_id.sudo().order_line.purchase_line_ids.order_id.filtered(lambda p: p.state != 'cancel')
        factories = self.env['sale.order'].sudo().search([('auto_purchase_order_id', 'in', purchases.ids), ('state', '!=', 'cancel')])
        return purchases, factories

    def _b2b_permission_digest(self):
        purchases, factories = self._b2b_supply_documents()
        snapshot = [self._snapshot_order(self.revision_order_id), purchases.ids,
                    [(f.id, self._snapshot_order(f)) for f in factories], self.b2b_factory_permission_note]
        return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()

    def write(self, vals):
        if {'b2b_factory_permission_by', 'b2b_factory_permission_at', 'b2b_factory_permission_digest'}.intersection(vals):
            raise UserError(_('Factory permission must be recorded with the confirmation button.'))
        if 'b2b_factory_permission_note' in vals:
            self._check_manager()
            if any(r.state != 'under_review' for r in self):
                raise UserError(_('Record factory permission while the proposal is under review.'))
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        if any({'b2b_factory_permission_by', 'b2b_factory_permission_at', 'b2b_factory_permission_digest', 'b2b_factory_permission_note'}.intersection(v) for v in vals_list):
            raise UserError(_('Record factory permission after starting the review.'))
        vals_list = [dict(vals) for vals in vals_list]
        for vals in vals_list:
            order = self.env['sale.order'].sudo().browse(vals.get('order_id')).exists()
            if order.b2b_routed_company:
                group = self.env.ref('b2b_core.group_b2b_manager')
                assigned = self.env['res.users'].sudo().browse(vals.get('assigned_user_id')).exists()
                if not assigned or order.company_id not in assigned.company_ids or not assigned.has_group('b2b_core.group_b2b_manager'):
                    assigned = self.env['res.users'].sudo().search([
                        ('active', '=', True), ('share', '=', False),
                        ('company_ids', 'in', order.company_id.ids),
                        ('all_group_ids', 'in', group.ids),
                    ], limit=1)
                if not assigned:
                    raise UserError(_('Our team must assign an order-change manager for your selling company.'))
                vals['assigned_user_id'] = assigned.id
        return super().create(vals_list)

    def action_confirm_factory_permission(self):
        self._check_manager()
        self.check_access('write')
        for change in self:
            change.order_id._b2b_lock_collection()
            if change.state != 'under_review' or not change.revision_order_id or not change.order_id.b2b_routed_company:
                raise UserError(_('Prepare the proposed revision before confirming factory permission.'))
            if not (change.b2b_factory_permission_note or '').strip():
                raise UserError(_('Record who at the factory approved this change and the approval reference.'))
            purchases, factories = change._b2b_supply_documents()
            if factories.order_line.filtered(lambda l: l.qty_delivered > 0) or purchases.picking_ids.filtered(lambda p: p.state == 'done'):
                raise UserError(_('This supply has already shipped. Use the return workflow.'))
            super(OrderChange, change).write({
                'b2b_factory_permission_by': self.env.uid,
                'b2b_factory_permission_at': fields.Datetime.now(),
                'b2b_factory_permission_digest': change._b2b_permission_digest(),
            })
            change.message_post(body=_('Operations confirmed factory permission for this proposal: %s', change.b2b_factory_permission_note))
        return True

    def _b2b_check_factory_permission(self):
        for change in self.filtered(lambda r: r.order_id.b2b_routed_company):
            _purchases, factories = change._b2b_supply_documents()
            if (change.order_id.b2b_fulfilment_mode == 'external' or factories.filtered(lambda o: o.state == 'sale')) and (
                not change.b2b_factory_permission_by or change.b2b_factory_permission_digest != change._b2b_permission_digest()
            ):
                raise UserError(_('Operations must confirm that the factory permits this exact proposal before proceeding. If the proposal changed, confirm again.'))

    def action_send_proposal(self):
        self._b2b_check_factory_permission()
        return super().action_send_proposal()

    def _apply_revision(self):
        if self.order_id.b2b_fulfilment_mode == 'external':
            self.order_id._b2b_lock_collection()
            self._b2b_check_factory_permission()
            result = super()._apply_revision()
            self.order_id._b2b_mark_external_change_pending()
            self.message_post(body=_('Commercial revision applied. External ERP execution is pending; API integration is not completed by this action.'))
            return result
        if self.order_id.b2b_fulfilment_mode == 'odoo':
            self.order_id._b2b_lock_collection()
            self._b2b_check_factory_permission()
            purchases, factories = self._b2b_supply_documents()
            if factories.order_line.filtered(lambda l: l.qty_delivered > 0) or purchases.picking_ids.filtered(lambda p: p.state == 'done'):
                raise UserError(_('The factory has shipped this order. Use the return workflow.'))
            if factories.invoice_ids.filtered(lambda i: i.state != 'cancel') or purchases.invoice_ids.filtered(lambda i: i.state != 'cancel'):
                raise UserError(_('Finance must resolve the internal invoices before changing these supply documents.'))
            # Cancellation occurs only after customer acceptance, inside the
            # same transaction as the revised external order and replacement RFQ.
            # A declined proposal never changes production documents.
            factories._action_cancel()
            purchases.button_cancel()
        return super()._apply_revision()
