from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env['sale.order'].search([
        ('b2b_receiving_journal_id', '!=', False),
        ('b2b_pi_bank_instructions', '=', False),
    ])
    for order in orders:
        order.b2b_pi_bank_instructions = order._b2b_pi_bank_text(order.b2b_receiving_journal_id)
