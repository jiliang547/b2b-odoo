from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Message = env["mail.message"].sudo()
    Thread = env["b2b.message.thread"].sudo()
    models = tuple(dict(Thread._fields["source_model"].selection))
    messages = Message.search([
        ("model", "in", models),
        ("res_id", "!=", 0),
        ("message_type", "in", ("comment", "email")),
        ("is_internal", "=", False),
        ("subtype_id.internal", "=", False),
    ], order="date asc, id asc")
    for message in messages:
        Thread._sync_from_message(message)
