"""Local-only fixtures for browser presentation checks; no real payment calls.

Run through the local Odoo shell. Uses the existing dedicated browser UAT contact.
"""
from odoo import Command

assert env.cr.dbname == 'b2b_v41_test_20260817', 'Local UAT database only'
partner = env['res.partner'].search([('email', '=', 'browser-order-flow@example.test')], limit=1)
assert partner and partner.commercial_partner_id.name == 'Browser Order Flow Company'
reference = 'PORTAL-PRESENTATION-UAT-20260911'
quote = env['sale.order'].search([('client_order_ref', '=', reference)], limit=1)
if not quote:
    product = env['sale.order'].browse(546).order_line.filtered(lambda l: not l.display_type and not l.is_delivery)[:1].product_id
    assert product
    quote = env['sale.order'].with_context(mail_notrack=True, tracking_disable=True).create({
        'partner_id': partner.id,
        'website_id': env.ref('website.default_website').id,
        'client_order_ref': reference,
        'require_signature': False,
        'require_payment': True,
        'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 10})],
    })
    quote.action_quotation_sent()
    paid = quote.copy({'client_order_ref': reference + '-PAID'})
    paid.action_confirm()
    env['payment.transaction'].create({
        'provider_id': env.ref('payment.payment_provider_demo').id,
        'payment_method_id': env.ref('payment_demo.payment_method_demo').id,
        'reference': reference + '-DEMO',
        'amount': paid.amount_total,
        'currency_id': paid.currency_id.id,
        'partner_id': partner.id,
        'operation': 'online_direct', 'state': 'done',
        'sale_order_ids': [Command.set(paid.ids)],
    })
    change = env['b2b.order.change.request'].create({
        'order_id': paid.id,
        'requested_changes': 'Presentation UAT only. Please increase the quantity to two units.\nKeep the product specification and delivery address unchanged.',
    })
    change.action_start_review()
    change.revision_order_id.order_line.filtered(lambda l: not l.display_type).product_uom_qty = 2
    change.action_send_proposal()
    env.cr.commit()
else:
    paid = env['sale.order'].search([('client_order_ref', '=', reference + '-PAID')], limit=1)
    change = env['b2b.order.change.request'].search([('order_id', '=', paid.id)], limit=1)
print({'quote_id': quote.id, 'quote': quote.name, 'paid_id': paid.id, 'change_id': change.id, 'change': change.name})
