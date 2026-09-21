from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    requests = env["b2b.contact.request"].search([("request_type", "=", "company_change")])
    # Existing conversations become shared without resending historical emails
    # or changing anybody's read/unread state.
    env["b2b.message.thread"].search([
        ("source_model", "=", "b2b.contact.request"),
        ("res_id", "in", requests.ids),
    ]).write({"company_id": False})
