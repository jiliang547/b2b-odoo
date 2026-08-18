from werkzeug.exceptions import NotFound

from odoo import _
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class PartnerHubPortal(CustomerPortal):
    def _sample_domain(self):
        company = request.env.user.partner_id.commercial_partner_id
        return [("commercial_partner_id", "=", company.id)]

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        company = request.env.user.partner_id.commercial_partner_id
        sale_domain = [
            ("partner_id", "child_of", company.id),
            ("state", "in", ("sale", "done")),
        ]
        quotation_domain = [
            ("partner_id", "child_of", company.id),
            ("state", "in", ("draft", "sent")),
        ]
        ticket_domain = [("partner_id", "child_of", company.id)]
        Sample = request.env["b2b.sample.request"]
        Order = request.env["sale.order"]
        Ticket = request.env["helpdesk.ticket"]
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
        values.update({
            "sample_count": Sample.search_count(self._sample_domain()),
            "order_count": Order.search_count(sale_domain) if can_read_orders else 0,
            "quotation_count": (
                Order.search_count(quotation_domain) if can_read_orders else 0
            ),
            "ticket_count": Ticket.search_count(ticket_domain) if can_read_tickets else 0,
            "recent_orders": recent_orders,
            "recent_samples": Sample.search(
                self._sample_domain(), order="create_date desc", limit=2
            ),
            "recent_tickets": recent_tickets,
        })
        return values

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
        return request.render("b2b_website.portal_sample_request", values)
