from urllib.parse import urlencode

from werkzeug.exceptions import NotFound
from odoo import fields, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.http import request, route, Controller


class PartnerService(Controller):
    @route('/my/service/<int:ticket_id>/tracking', type='http', auth='user', website=True, methods=['POST'])
    def submit_tracking(self, ticket_id, **post):
        ticket = request.env['helpdesk.ticket'].search([
            ('id', '=', ticket_id), ('b2b_request_type', '!=', False),
            ('partner_id.commercial_partner_id', '=', request.env.user.partner_id.commercial_partner_id.id),
        ], limit=1)
        if not ticket:
            raise NotFound()
        try:
            with request.env.cr.savepoint():
                # Serialize repeat submissions and approval changes.
                request.env.cr.execute('SELECT id FROM helpdesk_ticket WHERE id = %s FOR UPDATE', [ticket.id])
                ticket.invalidate_recordset()
                shipped_on = fields.Date.to_date(post.get('shipped_on'))
                if not shipped_on:
                    raise ValidationError(_('Enter a shipment date.'))
                ticket.sudo()._b2b_submit_tracking(post.get('carrier', ''), post.get('tracking', ''), shipped_on)
        except (ValueError, TypeError):
            error = _('Enter a valid shipment date.')
        except (AccessError, UserError, ValidationError) as exc:
            error = str(exc)
        else:
            return request.redirect('/my/ticket/%s?return_submitted=1' % ticket_id, code=303)
        return request.redirect('/my/ticket/%s?%s' % (ticket_id, urlencode({'service_error': error})), code=303)
