from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    """Keep portal registrations created by the former direct-signup flow visible."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    website = env["website"].search([], order="id", limit=1)
    if not website:
        return
    Application = env["b2b.registration.application"]
    portal_group = env.ref("base.group_portal")
    portal_users = env["res.users"].with_context(active_test=False).search([
        ("active", "=", True),
        ("share", "=", True),
        ("all_group_ids", "in", portal_group.ids),
        ("partner_id.commercial_partner_id.b2b_approved", "=", False),
    ])
    existing_user_ids = set(Application.search([
        ("user_id", "in", portal_users.ids),
    ]).user_id.ids)
    for user in portal_users.filtered(lambda item: item.id not in existing_user_ids):
        partner = user.partner_id
        company = partner.commercial_partner_id
        linked_company = company if company != partner else env["res.partner"]
        Application.create({
            "website_id": website.id,
            "user_id": user.id,
            "partner_id": partner.id,
            "state": "pending",
            "full_name": partner.name,
            "job_title": partner.function,
            "company_name": linked_company.name,
            "country_id": (partner.country_id or linked_company.country_id).id,
            "business_email": user.email or partner.email or user.login,
            "company_phone": linked_company.phone,
            "mobile": partner.b2b_mobile_whatsapp or partner.phone,
            "customer_type_id": linked_company.b2b_customer_type_id.id,
            "company_website": linked_company.website,
            "company_resolution": "existing" if linked_company else False,
            "company_id": linked_company.id,
            "email_verified_at": user.login_date or user.create_date,
            "terms_version": "legacy-direct-signup",
            "terms_accepted_at": False,
        })
