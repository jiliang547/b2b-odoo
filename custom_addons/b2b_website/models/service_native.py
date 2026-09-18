"""Keep externally fulfilled service requests out of native stock execution."""
from odoo import _, api, models
from odoo.exceptions import ValidationError


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
