from werkzeug.exceptions import NotFound
from odoo import http
from odoo.http import request


class OrderProgress(http.Controller):
    def _owned_order(self, order_id):
        # The same ownership boundary as the existing order progress page.
        # No access tokens, arbitrary filters or customer ids accepted here.
        partner = request.env.user.partner_id.commercial_partner_id
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        if not order or order.partner_id.commercial_partner_id != partner:
            raise NotFound()
        return order

    def _response(self, order):
        status = order._yonyou_public_progress()
        return {'pending': status['pending'], 'updated_at': status['updated_at'],
            'refresh': status['refresh'], 'content_key': status['content_key'],
            'delayed': status['delayed'], 'html': request.env['ir.ui.view']._render_template(
                'b2b_yonyou.progress_panel', {'order': order, 'status': status})}

    @http.route('/my/orders/<int:order_id>/erp-status/check', type='jsonrpc',
                auth='user', website=True, methods=['POST'])
    def check_progress(self, order_id):
        order = self._owned_order(order_id)
        # Polling is read-only. Only entering the HTML page can queue a read.
        return self._response(order)

    @http.route('/my/orders/<int:order_id>/erp-status/refresh', type='jsonrpc',
                auth='user', website=True, methods=['POST'])
    def refresh_progress(self, order_id):
        order = self._owned_order(order_id)
        requested = order._yonyou_request_progress(manual=True)
        result = self._response(order)
        # SKIP LOCKED may see another request before its queued state commits.
        # Join its polling cycle rather than queueing a duplicate or claiming success.
        if not requested and result['refresh']['supported'] and not result['refresh']['retry_after']:
            result['pending'] = True
        return result
