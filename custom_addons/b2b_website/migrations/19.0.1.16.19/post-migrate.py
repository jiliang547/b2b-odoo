from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for thread in env["b2b.message.thread"].sudo().search([]):
        thread._sync_from_message(thread.last_message_id)
