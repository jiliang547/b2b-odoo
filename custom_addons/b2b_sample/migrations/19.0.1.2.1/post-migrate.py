from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env["sale.order"].search([
        ("b2b_sample_request_id", "!=", False),
        ("b2b_sample_request_id.state", "=", "quotation"),
        ("state", "in", ["sale", "done"]),
    ])._b2b_sync_sample_state()
