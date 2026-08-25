from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Give portal users personal contacts while retaining their company parent."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    portal_group = env.ref("base.group_portal")
    users = env["res.users"].with_context(active_test=False).search([
        ("all_group_ids", "in", portal_group.id),
        ("partner_id.is_company", "=", True),
    ])
    for user in users:
        company = user.partner_id
        contact = env["res.partner"].create({
            "name": user.name or company.name,
            "parent_id": company.id,
            "type": "contact",
            "email": user.email or company.email,
            "phone": company.phone,
            "lang": user.lang or company.lang,
            "company_id": company.company_id.id,
        })
        user.partner_id = contact
