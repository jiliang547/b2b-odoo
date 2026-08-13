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
        if not counters or "sample_count" in counters:
            values["sample_count"] = request.env["b2b.sample.request"].search_count(
                self._sample_domain()
            )
        return values

    @route(
        ["/my/sample-requests", "/my/sample-requests/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_sample_requests(self, page=1, **kwargs):
        Sample = request.env["b2b.sample.request"]
        domain = self._sample_domain()
        total = Sample.search_count(domain)
        pager = portal_pager(
            url="/my/sample-requests", total=total, page=max(page, 1), step=20
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
