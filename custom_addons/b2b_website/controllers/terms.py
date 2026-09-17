from odoo import http
from odoo.http import request
from odoo.addons.account.controllers.terms import TermsController


def sitemap_partner_terms(env, rule, qs):
    if (not qs or qs.lower() in "/terms") and env.company._b2b_has_published_sale_terms():
        yield {"loc": "/terms"}


class PartnerTermsController(TermsController):
    @http.route(sitemap=sitemap_partner_terms)
    def terms_conditions(self, **kwargs):
        company = request.website.company_id
        available = company._b2b_has_published_sale_terms()
        return request.render(
            "b2b_website.partner_sale_terms",
            {"company": company, "terms_available": available},
            status=200 if available else 404,
        )
