from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    # No messages, notifications or emails are copied/resubmitted.
    api.Environment(cr, SUPERUSER_ID, {})["b2b.message.thread"]._backfill_customer_messages()
