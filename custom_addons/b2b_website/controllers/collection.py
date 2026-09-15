import base64
import math
import uuid
from datetime import timedelta

from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from odoo import _, fields, http
from odoo.http import request
from odoo.exceptions import UserError, ValidationError
from .website_sale import _can_checkout


class CollectionPortal(http.Controller):
    def _order(self, order_id):
        order = request.env['sale.order'].sudo().browse(order_id).exists()
        user = request.env.user
        if not order:
            raise NotFound()
        if user._is_internal():
            order.with_user(user).check_access('read')
        elif order.partner_id.commercial_partner_id != user.partner_id.commercial_partner_id:
            raise NotFound()
        return order

    def _render(self, order, error=None, submitted=False):
        return request.render('b2b_website.portal_collection', {
            'order': order, 'error': error, 'submitted': submitted,
            'submission_key': str(uuid.uuid4()),
            'receipts': order.b2b_receipt_ids.sorted('id', reverse=True),
            'pis': order.b2b_pi_ids,
        })

    @http.route('/my/orders/<int:order_id>/collection', type='http', auth='user', website=True, methods=['GET'])
    def collection(self, order_id, **kw):
        order = self._order(order_id)
        return self._render(order)

    @http.route('/my/orders/<int:order_id>/collection/proof', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def upload_proof(self, order_id, **post):
        order = self._order(order_id)
        try:
            with request.env.cr.savepoint():
                order._b2b_lock_collection()
                if not order.b2b_collection_active or order.b2b_review_state == 'pending' or order.state == 'cancel' or order.b2b_is_change_revision or not order.b2b_receiving_journal_id:
                    raise UserError(_('This order is not ready for bank payment. Contact our team first.'))
                if order.b2b_balance <= 0:
                    raise UserError(_('This order has no outstanding balance.'))
                key = str(uuid.UUID(post.get('submission_key', '')))
                Receipt = request.env['b2b.bank.receipt'].sudo()
                if Receipt.search_count([('order_id', '=', order.id), ('submission_key', '=', key)], limit=1):
                    return request.redirect('/my/orders/%s/collection' % order.id)
                if Receipt.search_count([('commercial_partner_id', '=', order.partner_id.commercial_partner_id.id), ('create_date', '>=', fields.Datetime.now() - timedelta(days=1))]) >= 30:
                    raise UserError(_('Too many submissions today. Please contact our team.'))
                amount = float(post.get('amount', '0'))
                if not math.isfinite(amount) or amount <= 0:
                    raise UserError(_('Enter a valid positive transfer amount.'))
                date = fields.Date.to_date(post.get('transfer_date'))
                reference = (post.get('reference') or '').strip()[:160]
                if not date or date > fields.Date.today() or not reference:
                    raise UserError(_('Enter the bank reference and a valid transfer date.'))
                upload = request.httprequest.files.get('proof')
                data = upload.read(8 * 1024 * 1024 + 1) if upload else b''
                kind = 'application/pdf' if data.startswith(b'%PDF-') else ('image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else ('image/jpeg' if data.startswith(b'\xff\xd8\xff') else None))
                if not kind or len(data) > 8 * 1024 * 1024:
                    raise UserError(_('Upload a PDF, PNG or JPG file no larger than 8 MB.'))
                receipt = Receipt.create({'order_id': order.id, 'declared_amount': amount, 'transfer_date': date, 'transfer_reference': reference, 'submission_key': key, 'customer_note': (post.get('note') or '')[:2000]})
                attachment = request.env['ir.attachment'].sudo().create({'name': secure_filename(upload.filename) or 'payment-proof', 'datas': base64.b64encode(data), 'mimetype': kind, 'res_model': receipt._name, 'res_id': receipt.id, 'public': False})
                receipt.attachment_ids = [(4, attachment.id)]
        except (UserError, ValidationError) as exc:
            return self._render(order, error=str(exc))
        except (ValueError, TypeError):
            return self._render(order, error=_('Please check the amount, date and form, then submit again.'))
        return self._render(order, submitted=True)

    @http.route('/my/orders/<int:order_id>/collection/proof/<int:receipt_id>/<int:attachment_id>', type='http', auth='user', website=True)
    def evidence(self, order_id, receipt_id, attachment_id, **kw):
        order = self._order(order_id)
        receipt = order.b2b_receipt_ids.filtered(lambda r: r.id == receipt_id)
        attachment = receipt.attachment_ids.filtered(lambda a: a.id == attachment_id)
        if not attachment:
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas), headers=[('Content-Type', attachment.mimetype), ('Content-Disposition', 'attachment; filename="payment-proof"'), ('X-Content-Type-Options', 'nosniff'), ('Cache-Control', 'private, no-store')])

    @http.route('/my/orders/<int:order_id>/collection/pi', type='http', auth='user', website=True)
    def pi(self, order_id, version=None, **kw):
        order = self._order(order_id)
        try:
            with request.env.cr.savepoint():
                record = order.b2b_pi_ids.filtered(lambda p: str(p.id) == version) if version else order._b2b_issue_pi()
                if not record:
                    raise NotFound()
                content = base64.b64decode(record.pdf)
        except UserError as exc:
            return self._render(order, error=str(exc))
        return request.make_response(content, headers=[('Content-Type', 'application/pdf'), ('Content-Disposition', 'attachment; filename="PI-%s-v%s.pdf"' % (secure_filename(order.name), record.revision)), ('Cache-Control', 'private, no-store')])

    @http.route('/shop/b2b-submit-order', type='http', auth='user', website=True, methods=['POST'], csrf=True)
    def submit_order(self, **post):
        if not _can_checkout():
            return request.redirect('/my')
        order = request.cart
        if not order or order.state != 'draft' or not order.website_order_line or not order._is_cart_ready():
            return request.redirect('/shop/cart')
        order = order.sudo()
        try:
            with request.env.cr.savepoint():
                order._b2b_lock_collection()
                order._b2b_start_collection()
                for line in order.website_order_line:
                    order._b2b_check_product_allowed(line.product_id.id)
                    order._b2b_validate_sale_quantity(line.product_id.id, line.product_uom_qty)
                order.action_quotation_sent()
                if order._b2b_can_produce():
                    order.action_confirm()
        except UserError as exc:
            return self._render(order, error=str(exc))
        request.session['sale_last_order_id'] = order.id
        request.website.sale_reset()
        return request.redirect('/my/orders/%s/collection' % order.id)
