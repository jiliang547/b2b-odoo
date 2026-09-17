"""An immutable execution owner, independent from the selling legal entity."""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    b2b_fulfilment_mode = fields.Selection([
        ('external', 'External ERP'), ('odoo', 'Odoo Fulfilment')],
        readonly=True, copy=False, string='Fulfilment Provider')
    b2b_fulfilment_factory_id = fields.Many2one('res.company', readonly=True, copy=False, ondelete='restrict')
    b2b_external_change_pending = fields.Boolean(readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            website = self.env['website'].sudo().browse(vals.get('website_id')).exists()
            source = self.sudo().browse(vals.get('b2b_source_order_id')).exists() if vals.get('b2b_is_change_revision') else self.browse()
            # Never accept visitor-provided execution mode or factory.
            mode = source.b2b_fulfilment_mode if source else (
                website.b2b_fulfilment_mode if website.b2b_multicompany_enabled else False)
            factory = source.b2b_fulfilment_factory_id if source else (
                website.b2b_factory_company_id if mode == 'odoo' else self.env['res.company'])
            vals.update(b2b_fulfilment_mode=mode, b2b_fulfilment_factory_id=factory.id,
                        b2b_external_change_pending=False)
            if mode == 'external':
                # Copies can carry a historic cross-company warehouse. External
                # fulfilment never needs a local stock default on a new order.
                vals['warehouse_id'] = False
            prepared.append(vals)
        return super().create(prepared)

    @api.depends('user_id', 'company_id', 'website_id', 'b2b_fulfilment_mode')
    def _compute_warehouse_id(self):
        external = self.filtered(lambda order: order.b2b_fulfilment_mode == 'external')
        external.warehouse_id = False
        for order in self - external:
            scoped = order.with_company(order.company_id or self.env.company)
            super(SaleOrder, scoped)._compute_warehouse_id()
            # website_sale_stock may fall back to the website/operator's
            # warehouse. It is never valid for a different legal seller.
            if order.b2b_routed_company and order.warehouse_id.company_id != order.company_id:
                order.warehouse_id = self.env['stock.warehouse'].search([
                    ('company_id', '=', order.company_id.id)], limit=1)

    @api.model
    def _b2b_repair_external_warehouses(self):
        """Upgrade only: do not touch any order with physical stock history."""
        repaired, skipped = [], []
        orders = self.search([('b2b_fulfilment_mode', '=', 'external'), ('warehouse_id', '!=', False)])
        for order in orders.filtered(lambda item: item.warehouse_id.company_id != item.company_id):
            if (order.picking_ids or order.order_line.move_ids
                    or order.order_line.purchase_line_ids
                    or any(line.qty_delivered for line in order.order_line)):
                skipped.append(order.id)
                continue
            order.with_company(order.company_id).write({'warehouse_id': False})
            repaired.append(order.id)
        logging.getLogger(__name__).info('External warehouse repair: cleared=%s; stock-history review required=%s', repaired, skipped)
        return {'repaired': repaired, 'skipped': skipped}

    def write(self, vals):
        for order in self:
            for name in ('b2b_fulfilment_mode', 'b2b_fulfilment_factory_id'):
                current = order[name].id if name.endswith('_id') else order[name]
                if name in vals and vals[name] != current:
                    raise ValidationError(_('An existing order keeps its original fulfilment provider and factory.'))
        if 'b2b_external_change_pending' in vals:
            raise ValidationError(_('External change status is maintained by the revision workflow.'))
        return super().write(vals)

    def _b2b_mark_external_change_pending(self):
        # Private method: no public RPC write path for a fake ERP acknowledgement.
        super(SaleOrder, self).write({'b2b_external_change_pending': True})

    @api.constrains('warehouse_id', 'state', 'order_line')
    def _check_warehouse(self):
        native = self.filtered(lambda order: order.b2b_fulfilment_mode != 'external')
        return super(SaleOrder, native)._check_warehouse()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _action_launch_stock_rule(self, *, previous_product_uom_qty=False):
        native = self.filtered(lambda line: line.order_id.b2b_fulfilment_mode != 'external')
        return super(SaleOrderLine, native)._action_launch_stock_rule(
            previous_product_uom_qty=previous_product_uom_qty)

    def _purchase_service_generation(self):
        native = self.filtered(lambda line: line.order_id.b2b_fulfilment_mode != 'external')
        return super(SaleOrderLine, native)._purchase_service_generation()
