from odoo import _
from odoo.http import request


def render_checkout_error():
    """A recoverable, transaction-safe notice, never raw ERP exception text."""
    return request.render('b2b_website.partner_hub_action_error', {
        'title': _('We could not submit your order'),
        'notice': _('Please review the selected products and quantities, or contact our team for help. Your cart has been kept. No payment was requested by this action.'),
        'back_url': '/shop/cart', 'back_label': _('Review Cart'),
    }, status=422)
