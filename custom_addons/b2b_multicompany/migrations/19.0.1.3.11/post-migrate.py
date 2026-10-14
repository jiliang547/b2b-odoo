from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Partner = env['res.partner'].with_context(active_test=False, tracking_disable=True)

    # These fields identify Partner Hub commercial customers without relying
    # on their native company_id, which may contain the legacy bad value.
    customers = Partner.search([
        '|', '|',
        ('b2b_selling_company_id', '!=', False),
        ('b2b_account_brand_id', '!=', False),
        ('b2b_approved', '=', True),
    ]).mapped('commercial_partner_id')
    if not customers:
        return

    internal_company_partners = env['res.company'].with_context(active_test=False).search([]).partner_id
    shared_contacts = Partner.search([
        ('id', 'child_of', customers.ids),
        ('company_id', '!=', False),
        ('id', 'not in', internal_company_partners.ids),
    ])
    if shared_contacts:
        shared_contacts.write({'company_id': False})
