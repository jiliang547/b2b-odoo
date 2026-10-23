"""One routing/ownership policy for customer conversations, not a mail transport.

Only explicit public comments participate. Native accounting/warehouse/HR logs,
supplier conversations, login tokens and internal notes are not customer mail.
New customer-facing models opt in here instead of changing four separate lists.
"""

CUSTOMER_MESSAGE_SOURCES = {
    "b2b.contact.request": ("Contact Request", "/my/inquiries/%s"),
    "sale.order": ("Order", "/my/orders/%s"),
    "b2b.sample.request": ("Sample Request", "/my/sample-requests/%s"),
    "helpdesk.ticket": ("Support Ticket", "/my/ticket/%s"),
    "b2b.order.change.request": ("Order Change", "/my/order-changes/%s"),
    "b2b.bank.receipt": ("Bank Payment Review", None),
    "account.payment": ("Customer Payment / Refund", None),
    "account.move": ("Customer Invoice / Credit Note", None),
    "stock.picking": ("Delivery / Return", None),
    "repair.order": ("Repair", None),
    "res.partner": ("Customer Account", None),
    "b2b.registration.application": ("Partner Application", None),
}


def field(record, name, empty):
    return record[name] if name in record._fields else empty


def customer_context(source):
    """Resolve business ownership without granting access to the source model.

    Callers may sudo this metadata lookup only after authenticating the native
    message operation or checking the indexed customer's ownership.
    """
    source.ensure_one()
    env = source.env
    name = source._name
    if name not in CUSTOMER_MESSAGE_SOURCES:
        return None
    partner, staff = env["res.partner"], env["res.users"]
    website, company = env["website"], env["res.company"]
    related = None
    if name == "b2b.contact.request":
        partner, staff, website = source.partner_id, source.assigned_user_id, source.website_id
        company = company if source.request_type == "company_change" else website.company_id
    elif name == "sale.order":
        partner, staff, website, company = source.partner_id, source.user_id, source.website_id, source.company_id
    elif name == "b2b.sample.request":
        partner, staff, website = source.contact_id, source.reviewer_id, source.website_id
        company = website.company_id
    elif name == "helpdesk.ticket":
        partner, staff, company = source.partner_id, source.user_id, source.company_id
        website = field(source, "website_id", website)
    elif name in ("b2b.order.change.request", "b2b.bank.receipt"):
        related = source.order_id
        partner, website, company = related.partner_id, related.website_id, related.company_id
        staff = source.assigned_user_id if name == "b2b.order.change.request" else source.reviewed_by_id or related.user_id
    elif name == "account.payment":
        if source.partner_type != "customer":
            return None
        partner, company = source.partner_id, source.company_id
        evidence = field(source, "b2b_evidence_id", env["b2b.bank.receipt"])
        related = evidence.order_id if evidence else None
        if related:
            website, staff = related.website_id, related.user_id
    elif name == "account.move":
        if source.move_type not in ("out_invoice", "out_refund"):
            return None
        partner, company, staff = source.partner_id, source.company_id, source.invoice_user_id
        orders = source.invoice_line_ids.sale_line_ids.order_id
        related = orders[:1] if len(orders) == 1 else None
        website = related.website_id if related else website
    elif name in ("stock.picking", "repair.order"):
        ticket = field(source, "ticket_id", env["helpdesk.ticket"])
        order = field(source, "sale_id", env["sale.order"]) or field(source, "sale_order_id", env["sale.order"])
        related = ticket or order
        if not related:
            return None  # Internal transfers and unlinked warehouse/repair logs.
        parent = customer_context(related)
        if not parent or source.company_id != parent["company"]:
            return None
        partner, staff, website, company = (parent[key] for key in ("partner", "staff", "website", "company"))
        address = field(source, "partner_id", partner)
        if address and address.commercial_partner_id != partner.commercial_partner_id:
            return None
    elif name == "res.partner":
        partner = source
        users = env["res.users"].search([
            ("active", "=", True), ("share", "=", True),
            ("partner_id.commercial_partner_id", "=", source.commercial_partner_id.id),
        ], limit=1)
        if not users:
            return None  # Suppliers, employees and private address-book notes.
        company = field(source.commercial_partner_id, "b2b_selling_company_id", company)
        staff = source.user_id
    elif name == "b2b.registration.application":
        partner, website = source.partner_id, source.website_id
        # Reuse the native registration mail-company resolver, including the
        # legal seller selected by the multi-company extension after approval.
        company = source._mail_get_companies(default=website.company_id).get(source.id) or website.company_id
        staff = source.approved_by_id
    if not partner and name != "b2b.contact.request":
        return None
    if related and related._name == "sale.order" and (
        related.company_id != company or related.partner_id.commercial_partner_id != partner.commercial_partner_id
    ):
        return None
    staff = staff.filtered(lambda user: user.active and not user.share and (not company or company in user.company_ids))[:1]
    if not staff:
        candidate = partner.user_id or partner.commercial_partner_id.user_id
        if not candidate and website and "salesperson_id" in website._fields:
            candidate = website.salesperson_id
        staff = candidate.filtered(lambda user: user.active and not user.share and (not company or company in user.company_ids))[:1]
        if not staff:
            domain = [("active", "=", True), ("share", "=", False),
                      ("all_group_ids", "in", env.ref("b2b_core.group_b2b_operator").ids)]
            if company:
                domain.append(("company_ids", "in", company.ids))
            staff = env["res.users"].search(domain, order="id", limit=1)
    recipients = partner
    if partner and (partner.is_company or not partner.email):
        contacts = env["res.users"].search([
            ("active", "=", True), ("share", "=", True),
            ("partner_id.commercial_partner_id", "=", partner.commercial_partner_id.id),
        ], order="id").partner_id
        recipients = partner | contacts
    return {"partner": partner, "staff": staff, "website": website, "company": company,
            "recipients": recipients | staff.partner_id, "related": related,
            "label": CUSTOMER_MESSAGE_SOURCES[name][0], "route": CUSTOMER_MESSAGE_SOURCES[name][1]}
