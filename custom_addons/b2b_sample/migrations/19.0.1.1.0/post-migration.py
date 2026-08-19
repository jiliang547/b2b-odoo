from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for sample in env["b2b.sample.request"].search([]):
        if sample.contact_id and sample.contact_id not in sample.message_partner_ids:
            sample.message_subscribe(partner_ids=sample.contact_id.ids)
