from werkzeug.exceptions import NotFound

from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class PartnerHubPortal(CustomerPortal):
    def _parse_form_data(self, form_data):
        """Portal contacts may edit themselves, never commercial master data."""
        personal_data = dict(form_data)
        personal_data.pop("company_name", None)
        personal_data.pop("vat", None)
        return super()._parse_form_data(personal_data)

    def _create_or_update_address(self, partner_sudo, **form_data):
        if (
            partner_sudo
            and partner_sudo.is_company
            and partner_sudo == request.env.user.partner_id.commercial_partner_id
        ):
            return partner_sudo, {
                "messages": [_("Company master data can only be changed by authorized staff.")],
                "invalid_fields": ["name"],
            }
        form_data.pop("company_name", None)
        form_data.pop("vat", None)
        return super()._create_or_update_address(partner_sudo, **form_data)

    def _website_payment_order_ids(self, partner):
        """Return attempted website orders within the current portal company.

        Portal users deliberately cannot read ``sale.order.transaction_ids``.
        Resolve that native relation in sudo within the commercial partner and
        website boundary, then let the normal portal record rules filter the
        resulting order IDs in the actual list query.
        """
        return request.env["sale.order"].sudo().search([
            ("partner_id", "child_of", [partner.commercial_partner_id.id]),
            ("website_id", "!=", False),
            ("transaction_ids", "!=", False),
        ]).ids

    def _prepare_orders_domain(self, partner):
        """Include website checkout attempts in the customer's order history.

        Odoo normally separates quotations (``sent``) from confirmed orders
        (``sale``).  A failed website payment can leave the linked order in
        ``draft`` though, which makes the still-valid checkout disappear from
        both native lists.  Keep the native sale and payment states and only
        broaden the portal domain for website orders that have a transaction.
        """
        attempted_order_ids = self._website_payment_order_ids(partner)
        return [
            ("partner_id", "child_of", [partner.commercial_partner_id.id]),
            "|",
            ("state", "=", "sale"),
            ("id", "in", attempted_order_ids),
        ]

    def _prepare_quotations_domain(self, partner):
        """Keep unattempted quotations in Quotes and avoid duplicate rows."""
        attempted_order_ids = self._website_payment_order_ids(partner)
        return [
            ("partner_id", "child_of", [partner.commercial_partner_id.id]),
            ("state", "=", "sent"),
            ("id", "not in", attempted_order_ids),
        ]

    def _sample_domain(self):
        company = request.env.user.partner_id.commercial_partner_id
        return [("commercial_partner_id", "=", company.id)]

    def _inquiry_domain(self):
        company = request.env.user.partner_id.commercial_partner_id
        return [("commercial_partner_id", "=", company.id)]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        company = request.env.user.partner_id.commercial_partner_id
        sale_domain = self._prepare_orders_domain(request.env.user.partner_id)
        quotation_domain = self._prepare_quotations_domain(request.env.user.partner_id)
        ticket_domain = [("partner_id", "child_of", company.id)]
        Sample = request.env["b2b.sample.request"]
        Order = request.env["sale.order"]
        Ticket = request.env["helpdesk.ticket"]
        Inquiry = request.env["b2b.contact.request"]
        can_read_orders = Order.has_access("read")
        can_read_tickets = Ticket.has_access("read")
        recent_orders = (
            Order.search(sale_domain, order="date_order desc", limit=3).sudo()
            if can_read_orders else Order
        )
        recent_tickets = (
            Ticket.search(ticket_domain, order="create_date desc", limit=2).sudo()
            if can_read_tickets else Ticket
        )

        # The Figma dashboard is backed exclusively by records visible to the
        # current portal user; no demo counters or sudoed records are exposed.
        dashboard_values = {
            "sample_count": Sample.search_count(self._sample_domain()),
            "inquiry_count": Inquiry.search_count(self._inquiry_domain()),
            "order_count": Order.search_count(sale_domain) if can_read_orders else 0,
            "quotation_count": (
                Order.search_count(quotation_domain) if can_read_orders else 0
            ),
            "ticket_count": Ticket.search_count(ticket_domain) if can_read_tickets else 0,
            "recent_orders": recent_orders,
            "recent_samples": Sample.search(
                self._sample_domain(), order="create_date desc", limit=2
            ),
            "recent_inquiries": Inquiry.search(
                self._inquiry_domain(), order="create_date desc", limit=2
            ),
            "recent_tickets": recent_tickets,
        }
        # Native /my/counters expects the response to contain only requested
        # placeholders. Returning dashboard-only keys makes Odoo's own counter
        # interaction address DOM nodes that do not exist.
        if counters:
            values.update({key: value for key, value in dashboard_values.items() if key in counters})
        else:
            values.update(dashboard_values)
        return values

    @route(
        ["/my/inquiries", "/my/inquiries/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_inquiries(self, page=1, **kwargs):
        Inquiry = request.env["b2b.contact.request"]
        domain = self._inquiry_domain()
        search = (kwargs.get("search") or "").strip()[:120]
        state = (kwargs.get("state") or "").strip()
        if search:
            domain += [
                "|", "|",
                ("name", "ilike", search),
                ("subject", "ilike", search),
                ("message", "ilike", search),
            ]
        allowed_states = dict(Inquiry._fields["state"].selection)
        if state in allowed_states:
            domain.append(("state", "=", state))
        total = Inquiry.search_count(domain)
        pager = portal_pager(
            url="/my/inquiries",
            url_args={"search": search, "state": state},
            total=total,
            page=max(page, 1),
            step=20,
        )
        inquiries = Inquiry.search(
            domain, order="create_date desc", limit=20, offset=pager["offset"]
        )
        request.session["my_inquiries_history"] = inquiries.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            "inquiries": inquiries,
            "pager": pager,
            "page_name": "inquiries",
            "default_url": "/my/inquiries",
            "search": search,
            "selected_state": state,
            "inquiry_states": allowed_states,
            "inquiry_total": total,
        })
        return request.render("b2b_website.portal_my_inquiries", values)

    @route("/my/inquiries/<int:inquiry_id>", type="http", auth="user", website=True)
    def portal_inquiry(self, inquiry_id, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        inquiry_sudo = request.env["b2b.contact.request"].sudo().browse(
            inquiry_id
        ).exists()
        if not inquiry_sudo or inquiry_sudo.commercial_partner_id != company:
            raise NotFound()
        inquiry = request.env["b2b.contact.request"].browse(inquiry_id)
        # Mark this conversation read before rendering so the shared header
        # badge immediately reflects the Odoo notification state.
        inquiry.message_ids.set_message_done()
        values = self._prepare_portal_layout_values()
        values.update({
            "inquiry": inquiry,
            "page_name": "inquiry_detail",
        })
        values = self._get_page_view_values(
            inquiry,
            access_token=None,
            values=values,
            session_history="my_inquiries_history",
            no_breadcrumbs=False,
            **kwargs,
        )
        return request.render("b2b_website.portal_inquiry", values)

    @route(
        ["/my/sample-requests", "/my/sample-requests/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_sample_requests(self, page=1, **kwargs):
        Sample = request.env["b2b.sample.request"]
        domain = self._sample_domain()
        search = (kwargs.get("search") or "").strip()
        state = (kwargs.get("state") or "").strip()
        if search:
            domain += [
                "|",
                ("name", "ilike", search),
                ("line_ids.product_id.name", "ilike", search),
            ]
        allowed_states = dict(Sample._fields["state"].selection)
        if state in allowed_states:
            domain.append(("state", "=", state))
        total = Sample.search_count(domain)
        pager = portal_pager(
            url="/my/sample-requests",
            url_args={"search": search, "state": state},
            total=total,
            page=max(page, 1),
            step=20,
        )
        samples = Sample.search(
            domain, order="create_date desc", limit=20, offset=pager["offset"]
        )
        request.session["my_sample_requests_history"] = samples.ids[:100]
        values = self._prepare_portal_layout_values()
        values.update({
            "samples": samples,
            "pager": pager,
            "page_name": "sample_requests",
            "default_url": "/my/sample-requests",
            "search": search,
            "selected_state": state,
            "sample_states": allowed_states,
            "sample_total": total,
        })
        return request.render("b2b_website.portal_my_sample_requests", values)

    @route("/my/sample-requests/<int:sample_id>", type="http", auth="user", website=True)
    def portal_sample_request(self, sample_id, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        sample = request.env["b2b.sample.request"].browse(sample_id).exists()
        if not sample or sample.commercial_partner_id != company:
            raise NotFound()
        values = self._prepare_portal_layout_values()
        values.update({
            "sample": sample,
            "page_name": "sample_request_detail",
            "submitted": kwargs.get("submitted"),
        })
        values = self._get_page_view_values(
            sample,
            access_token=None,
            values=values,
            session_history="my_sample_requests_history",
            no_breadcrumbs=False,
            **kwargs,
        )
        return request.render("b2b_website.portal_sample_request", values)
