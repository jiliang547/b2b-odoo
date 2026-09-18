"""Keep externally fulfilled service requests out of native stock execution."""
from odoo import _, api, models
from odoo.exceptions import ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        result = super().action_confirm()
        # helpdesk_stock's native demo writes quantity to existing move lines.
        # With no reservable demo stock those lines do not exist, so its write
        # is a no-op and subsequent validation fails. Prepare only the exact
        # untracked demo moves, never customer deliveries or normal requests.
        if self.env.su and self.env.context.get('install_demo'):
            for number in (1, 3):
                line = self.env.ref(
                    'helpdesk_sale.sale_order_line_helpdesk_%s' % number,
                    raise_if_not_found=False,
                )
                if not line or line.order_id not in self or line.order_id.b2b_collection_active:
                    continue
                for move in line.move_ids.filtered(lambda m: (
                    m.state not in ('done', 'cancel')
                    and m.picking_type_id.code == 'outgoing'
                    and m.product_id.tracking == 'none'
                    and not m.move_line_ids
                )):
                    move.quantity = move.product_uom_qty
        return result


def check_native_service(ticket):
    ticket = ticket.sudo()
    if ticket.b2b_service_step and ticket.b2b_fulfilment_mode == 'external':
        raise ValidationError(_('This service request is fulfilled externally. Record the warehouse result on the service ticket.'))


class ReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _create_return(self):
        for wizard in self:
            if wizard.ticket_id:
                check_native_service(wizard.ticket_id)
        return super()._create_return()


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ticket_id = vals.get('ticket_id') or self.env.context.get('default_ticket_id')
            if ticket_id:
                check_native_service(self.env['helpdesk.ticket'].browse(ticket_id))
        return super().create(vals_list)


class Picking(models.Model):
    _inherit = 'stock.picking'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            ticket_id = vals.get('ticket_id') or self.env.context.get('default_ticket_id')
            if ticket_id:
                check_native_service(self.env['helpdesk.ticket'].browse(ticket_id))
        return super().create(vals_list)
