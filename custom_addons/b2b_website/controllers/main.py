import math
from urllib.parse import urlparse

from markupsafe import Markup, escape
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from odoo import Command, _, fields, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.http import request, route
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.addons.website.controllers.main import Website as WebsiteController


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_UPLOADS = 5
ALLOWED_UPLOADS = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}


class PartnerHubWebsite(WebsiteController):
    def _website(self):
        return request.website

    def _service(self):
        return request.env["b2b.product.service"]

    def _sample_allowed(self):
        if request.env.user._is_public():
            return False
        company = request.env.user.partner_id.commercial_partner_id
        return (
            not request.website.b2b_require_approved_sample
            or company.b2b_approved
        )

    def _safe_int(self, value):
        try:
            value = int(value or 0)
            return value if value > 0 else False
        except (TypeError, ValueError):
            return False

    def _submission_token(self, form=None):
        token = (form or {}).get("submission_token")
        return token or request.env["b2b.web.submission"].sudo().new_token()

    def _claim_submission(self, form, operation):
        return request.env["b2b.web.submission"].sudo().claim(
            self._submission_token(form),
            operation,
            request.env.user,
            request.website,
        )

    def _completed_submission_redirect(self, submission):
        if submission.state != "completed" or not submission.response_url:
            raise ValidationError(
                _("This request is already being processed. Please check your account shortly.")
            )
        return request.redirect(submission.response_url, code=303)

    def _contact_values(self, form=None, error=None):
        company = request.env.company.sudo()
        partner = company.partner_id
        form = dict(form or {})
        if not request.env.user._is_public():
            contact = request.env.user.partner_id
            commercial = contact.commercial_partner_id
            form.setdefault("contact_name", contact.name or "")
            form.setdefault("email", contact.email or commercial.email or "")
            form.setdefault("phone", contact.phone or commercial.phone or "")
            form.setdefault("company_name", commercial.name or "")
        return {
            "form": form,
            "submission_token": self._submission_token(form),
            "error": error,
            "request_types": request.env["b2b.contact.request"]._fields[
                "request_type"
            ].selection,
            "company_contact": {
                "name": company.name,
                "email": company.email or "sales@luckytone.com",
                "phone": company.phone or "",
                "address": partner.contact_address
                or "Contact us for our current office address.",
            },
            "page_name": "partner_contact",
        }

    def _clean_contact_form(self, form, allowed_types=None):
        limits = {
            "contact_name": 160,
            "email": 254,
            "phone": 64,
            "company_name": 200,
            "subject": 200,
            "message": 5000,
        }
        values = {
            key: (form.get(key) or "").strip()[:maximum]
            for key, maximum in limits.items()
        }
        required = ("contact_name", "email", "subject", "message")
        if any(not values[key] for key in required):
            raise ValidationError(_("Please complete all required fields."))
        if not tools.single_email_re.match(values["email"]):
            raise ValidationError(_("Please enter a valid email address."))
        request_type = (form.get("request_type") or "sales").strip()
        allowed_types = allowed_types or {
            item[0]
            for item in request.env["b2b.contact.request"]._fields[
                "request_type"
            ].selection
        }
        if request_type not in allowed_types:
            raise ValidationError(_("Please select a valid request type."))
        values["request_type"] = request_type
        return values

    def _catalog_domain(self, query):
        domain = self._service().visible_domain(website=self._website())
        search = (query.get("search") or "").strip()[:120]
        if search:
            domain = Domain.AND([
                domain,
                Domain.OR([
                    [("name", "ilike", search)],
                    [("default_code", "ilike", search)],
                    [("b2b_model_number", "ilike", search)],
                    [("description_sale", "ilike", search)],
                ]),
            ])
        filters = {
            "brand": "b2b_brand_id",
            "tag": "product_tag_ids",
            "application": "b2b_application_ids",
        }
        category = self._safe_int(query.get("category"))
        if category:
            domain = Domain.AND([domain, [("public_categ_ids", "child_of", category)]])
        for parameter, field_name in filters.items():
            value = self._safe_int(query.get(parameter))
            if value:
                domain = Domain.AND([domain, [(field_name, "in", [value])]])
        return domain

    def _catalog_values(self, products, **extra):
        Product = request.env["product.template"].sudo()
        visible = self._service().visible_domain(website=self._website())
        values = {
            "products": products,
            "prices": self._service().price_payload(products, website=self._website()),
            "price_state": self._service().price_state(website=self._website()),
            "categories": request.env["product.public.category"].sudo().search(
                [("product_tmpl_ids", "any", visible)], order="name"
            ),
            "brands": request.env["b2b.product.brand"].sudo().search([
                ("active", "=", True), ("product_ids", "any", visible)
            ], order="sequence, name"),
            "tags": request.env["product.tag"].sudo().search([
                ("product_template_ids", "any", visible)
            ], order="name"),
            "applications": request.env["b2b.product.application"].sudo().search([
                ("active", "=", True), ("product_ids", "any", visible)
            ], order="sequence, name"),
            "product_model": Product,
        }
        values.update(extra)
        return values

    def _visible_products(self, limit=200):
        return request.env["product.template"].sudo().search(
            self._service().visible_domain(website=self._website()),
            limit=limit,
            order="website_sequence, name",
        )

    def _category_rows(self, parent_id=False, brand=False):
        """Return only branches that contain products visible to this visitor."""
        visible = self._service().visible_domain(website=self._website())
        if brand:
            visible = Domain.AND([visible, [("b2b_brand_id", "=", brand.id)]])
        categories = request.env["product.public.category"].sudo().search(
            [
                ("parent_id", "=", parent_id or False),
                ("website_id", "in", [False, request.website.id]),
            ],
            order="sequence, name, id",
        )
        Product = request.env["product.template"].sudo()
        rows = []
        for category in categories:
            category_domain = Domain.AND([
                visible,
                [("public_categ_ids", "child_of", category.id)],
            ])
            representative = Product.search(
                category_domain, limit=1, order="website_sequence, name, id"
            )
            if not representative:
                continue
            child_domain = Domain.AND([
                visible,
                [("public_categ_ids", "child_of", category.child_id.ids)],
            ]) if category.child_id else Domain("id", "=", 0)
            rows.append({
                "record": category,
                "id": category.id,
                "name": category.name,
                "has_children": bool(
                    category.child_id
                    and Product.search_count(child_domain, limit=1)
                ),
                "image_url": (
                    f"/web/image/product.public.category/{category.id}/cover_image"
                    if category.cover_image
                    else f"/web/image/product.template/{representative.id}/image_512"
                ),
            })
        return rows

    def _configured_home_products(self, section, limit=10):
        lines = request.env["b2b.homepage.product"].sudo().search([
            ("website_id", "=", request.website.id),
            ("section", "=", section),
            ("active", "=", True),
        ], order="sequence, id")
        visible_ids = set(request.env["product.template"].sudo().search(
            Domain.AND([
                self._service().visible_domain(website=self._website()),
                [("id", "in", lines.product_tmpl_id.ids)],
            ])
        ).ids)
        ordered = request.env["product.template"].sudo()
        for line in lines:
            if line.product_tmpl_id.id in visible_ids:
                ordered |= line.product_tmpl_id
            if len(ordered) >= limit:
                break
        return ordered

    def _recommended_products(self, defaults, limit=10):
        if request.env.user._is_public():
            return defaults[:limit]
        company = request.env.user.partner_id.commercial_partner_id
        seeds = request.env["product.template"].sudo()
        recent_orders = request.env["sale.order"].sudo().search([
            ("partner_id", "child_of", company.id),
            ("state", "=", "sale"),
        ], order="date_order desc, id desc", limit=10)
        for order in recent_orders:
            for line in order.order_line:
                if line.display_type or not line.product_id:
                    continue
                template = line.product_id.product_tmpl_id
                if template not in seeds:
                    seeds |= template
                if len(seeds) >= 10:
                    break
            if len(seeds) >= 10:
                break

        visitor_ids = request.env["website.visitor"].sudo().search([
            ("partner_id", "child_of", company.id),
        ]).ids
        if visitor_ids:
            tracks = request.env["website.track"].sudo().search([
                ("visitor_id", "in", visitor_ids),
                ("b2b_product_tmpl_id", "!=", False),
            ], order="visit_datetime desc, id desc", limit=10)
            for template in tracks.b2b_product_tmpl_id:
                if template not in seeds:
                    seeds |= template

        candidates = request.env["product.template"].sudo()
        for seed in seeds[:10]:
            for optional in seed.optional_product_ids:
                if optional != seed and optional not in candidates:
                    candidates |= optional

        visible_ids = set(request.env["product.template"].sudo().search(
            Domain.AND([
                self._service().visible_domain(website=self._website()),
                [("id", "in", candidates.ids)],
            ]),
            order="website_sequence, name, id",
        ).ids)
        result = request.env["product.template"].sudo()
        for product in candidates:
            if product.id in visible_ids:
                result |= product
            if len(result) >= limit:
                return result
        for product in defaults:
            if product not in result:
                result |= product
            if len(result) >= limit:
                break
        return result

    def _track_product_view(self, product):
        visitor = request.env["website.visitor"].sudo()._get_visitor_from_request(
            force_create=True
        )
        if not visitor:
            return
        Track = request.env["website.track"].sudo()
        recent = Track.search_count([
            ("visitor_id", "=", visitor.id),
            ("b2b_product_tmpl_id", "=", product.id),
            ("visit_datetime", ">=", fields.Datetime.subtract(fields.Datetime.now(), minutes=30)),
        ], limit=1)
        if not recent:
            Track.create({
                "visitor_id": visitor.id,
                "url": request.httprequest.url,
                "b2b_product_tmpl_id": product.id,
            })

    @route("/about", type="http", auth="public", website=True, sitemap=True)
    def about(self, **kwargs):
        return request.render("b2b_website.partner_about", {"page_name": "partner_about"})

    @route("/solutions", type="http", auth="public", website=True, sitemap=True)
    def solutions(self, **kwargs):
        return request.render(
            "b2b_website.partner_solutions",
            {"page_name": "partner_solutions"},
        )

    @route("/privacy", type="http", auth="public", website=True, sitemap=True)
    def privacy(self, **kwargs):
        return request.render(
            "b2b_website.partner_privacy",
            {"page_name": "partner_privacy"},
        )

    @route("/contact", type="http", auth="public", website=True, sitemap=True)
    def contact(self, **kwargs):
        return request.render("b2b_website.partner_contact", self._contact_values())

    @route("/contactus", type="http", auth="public", website=True, sitemap=False)
    def contactus_alias(self, **kwargs):
        return request.redirect("/contact", code=301)

    @route(
        "/contact/submit", type="http", auth="public", website=True,
        methods=["POST"], csrf=True,
    )
    def contact_submit(self, **form):
        if form.get("website"):
            raise NotFound()
        try:
            values = self._clean_contact_form(form)
            submission, is_new = self._claim_submission(form, "contact_request")
            if not is_new:
                return self._completed_submission_redirect(submission)
            partner = (
                request.env.user.partner_id
                if not request.env.user._is_public()
                else request.env["res.partner"]
            )
            values.update({
                "partner_id": partner.id,
                "website_id": request.website.id,
                "source_url": request.httprequest.referrer or "/contact",
            })
            contact_request = request.env["b2b.contact.request"].sudo().create(values)
            response_url = "/contact/thanks?token=%s" % contact_request.access_token
            submission.complete(response_url, contact_request)
        except ValidationError as error:
            return request.render(
                "b2b_website.partner_contact",
                self._contact_values(form=form, error=error.args[0]),
            )
        return request.redirect(response_url, code=303)

    @route("/contact/thanks", type="http", auth="public", website=True, sitemap=False)
    def contact_thanks(self, token=None, **kwargs):
        contact_request = request.env["b2b.contact.request"].sudo().search(
            [("access_token", "=", (token or "")[:64])], limit=1
        )
        if not contact_request:
            raise NotFound()
        return request.render(
            "b2b_website.contact_request_thanks",
            {"contact_request": contact_request, "no_index": True},
        )

    @route("/partner-application", type="http", auth="public", website=True, sitemap=True)
    def partner_application(self, **kwargs):
        return request.render(
            "b2b_website.partner_application",
            self._partner_application_values(),
        )

    def _partner_application_values(self, form=None, error=None):
        return {
            "form": dict(form or {}),
            "error": error,
            "submission_token": self._submission_token(form),
            "page_name": "partner_application",
        }

    @route(
        "/partner-application/submit", type="http", auth="public", website=True,
        methods=["POST"], csrf=True,
    )
    def partner_application_submit(self, **form):
        try:
            website_url = (form.get("company_website") or "").strip()[:500]
            if website_url and urlparse(website_url).scheme not in ("http", "https"):
                raise ValidationError(_("Please enter a complete company website URL."))
            details = {
                "Country / region": (form.get("country_region") or "").strip()[:160],
                "Company website": website_url,
                "Business type": (form.get("business_type") or "").strip()[:120],
                "Role / title": (form.get("job_title") or "").strip()[:160],
                "Markets and project types": (form.get("description") or "").strip()[:5000],
            }
            if not details["Country / region"] or not details["Business type"] or not details["Markets and project types"]:
                raise ValidationError(_("Please complete all required partnership fields."))
            if any(not (form.get(field_name) or "").strip() for field_name in (
                "company_name", "contact_name", "email", "phone"
            )) or form.get("consent") != "1":
                raise ValidationError(_("Please complete all required fields and confirm the declaration."))
            values = self._clean_contact_form({
                "contact_name": form.get("contact_name"),
                "email": form.get("email"),
                "phone": form.get("phone"),
                "company_name": form.get("company_name"),
                "subject": _("Partner Hub application"),
                "message": "\n".join("%s: %s" % item for item in details.items()),
                "request_type": "partnership",
            })
            submission, is_new = self._claim_submission(form, "partner_application")
            if not is_new:
                return self._completed_submission_redirect(submission)
            partner = (
                request.env.user.partner_id
                if not request.env.user._is_public()
                else request.env["res.partner"]
            )
            values.update({
                "partner_id": partner.id,
                "website_id": request.website.id,
                "source_url": "/partner-application",
            })
            application = request.env["b2b.contact.request"].sudo().create(values)
            response_url = "/contact/thanks?token=%s" % application.access_token
            submission.complete(response_url, application)
        except ValidationError as error:
            return request.render(
                "b2b_website.partner_application",
                self._partner_application_values(form=form, error=error.args[0]),
            )
        return request.redirect(response_url, code=303)

    @route("/products/compare", type="http", auth="public", website=True, sitemap=False)
    def product_compare(self, **query):
        raw_ids = (query.get("ids") or "").split(",")
        ids = [value for value in (self._safe_int(item) for item in raw_ids) if value][:4]
        domain = Domain.AND([
            self._service().visible_domain(website=self._website()),
            [("id", "in", ids)],
        ])
        products = request.env["product.template"].sudo().search(domain)
        products = products.sorted(key=lambda item: ids.index(item.id) if item.id in ids else 99)
        if not products:
            products = self._visible_products(limit=3)
        return request.render(
            "b2b_website.product_comparison",
            self._catalog_values(
                products,
                page_name="partner_product_compare",
            ),
        )

    def _resource_format(self, document):
        if document.type == "url":
            path = urlparse(document.url or "").path
            extension = path.rsplit(".", 1)[-1] if "." in path else "LINK"
        else:
            extension = (document.mimetype or "").split("/")[-1]
        aliases = {
            "application/pdf": "PDF",
            "pdf": "PDF",
            "zip": "ZIP",
            "x-zip-compressed": "ZIP",
            "step": "STEP",
            "stp": "STEP",
        }
        return aliases.get(extension.casefold(), extension.upper() or "FILE")

    def _resource_rows(self, search="", category=False, file_type=""):
        rows = []
        needle = search.casefold().strip()[:120]
        for product in self._visible_products(limit=200):
            for document in self._service().allowed_documents(
                product, website=self._website()
            ):
                resource_format = self._resource_format(document)
                primary_category = product.public_categ_ids[:1]
                haystack = " ".join(filter(None, [
                    document.name,
                    document.b2b_version,
                    document.b2b_language,
                    product.name,
                    product.b2b_model_number,
                    primary_category.name,
                    resource_format,
                ])).casefold()
                category_matches = not category or category in product.public_categ_ids.ids
                type_matches = not file_type or resource_format == file_type
                if (not needle or needle in haystack) and category_matches and type_matches:
                    rows.append({
                        "document": document,
                        "product": product,
                        "category": primary_category,
                        "format": resource_format,
                    })
        return rows

    @route("/resources", type="http", auth="public", website=True, sitemap=True)
    def resources(self, **query):
        search = (query.get("search") or "").strip()[:120]
        category = self._safe_int(query.get("category"))
        file_type = (query.get("file_type") or "").strip().upper()[:12]
        if file_type not in {"", "PDF", "ZIP", "STEP", "LINK", "FILE"}:
            file_type = ""
        all_rows = self._resource_rows()
        rows = self._resource_rows(
            search=search,
            category=category,
            file_type=file_type,
        )
        resource_categories = request.env["product.public.category"].browse(
            sorted({item.id for row in all_rows for item in row["product"].public_categ_ids})
        ).sorted("name")
        resource_formats = sorted({row["format"] for row in all_rows})
        return request.render(
            "b2b_website.resource_center",
            {
                "resources": rows,
                "search": search,
                "resource_category": category,
                "resource_type": file_type,
                "resource_categories": resource_categories,
                "resource_formats": resource_formats,
                "resource_total": len(all_rows),
                "resource_pdf_total": sum(row["format"] == "PDF" for row in all_rows),
                "resource_category_total": len(resource_categories),
                "resource_product_total": len({row["product"].id for row in all_rows}),
                "page_name": "partner_resources",
            },
        )

    @route("/resources/<int:document_id>", type="http", auth="public", website=True)
    def resource_detail(self, document_id, **kwargs):
        document = request.env["product.document"].sudo().browse(document_id).exists()
        if not document or not self._service().document_is_allowed(
            document, website=self._website()
        ):
            raise NotFound()
        return request.render(
            "b2b_website.resource_detail",
            {
                "document": document,
                "product": self._service().product_from_document(document),
                "page_name": "partner_resource_detail",
                "no_index": True,
            },
        )

    @route("/samples", type="http", auth="user", website=True, sitemap=False)
    def sample_center(self, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        Sample = request.env["b2b.sample.request"]
        domain = [("commercial_partner_id", "=", company.id)]
        samples = Sample.search(domain, limit=5, order="create_date desc")
        return request.render(
            "b2b_website.sample_center",
            {
                "samples": samples,
                "sample_total": Sample.search_count(domain),
                "sample_open": Sample.search_count(Domain.AND([domain, [("state", "in", ("submitted", "under_review", "approved"))]])),
                "sample_approved": Sample.search_count(Domain.AND([domain, [("state", "in", ("approved", "erp_pending"))]])),
                "sample_completed": Sample.search_count(Domain.AND([domain, [("state", "=", "erp_synced")]])),
                "sample_pending": Sample.search_count(Domain.AND([domain, [("state", "in", ("draft", "submitted", "under_review"))]])),
                "page_name": "sample_center",
                "no_index": True,
            },
        )

    @route("/service-center", type="http", auth="user", website=True, sitemap=False)
    def service_center(self, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        Ticket = request.env["helpdesk.ticket"]
        domain = [("partner_id", "child_of", company.id)]
        tickets = Ticket.search(domain, limit=8, order="create_date desc")
        open_domain = Domain.AND([domain, [("stage_id.fold", "=", False)]])
        closed_domain = Domain.AND([domain, [("stage_id.fold", "=", True)]])
        return request.render(
            "b2b_website.service_center",
            {
                "tickets": tickets,
                "ticket_total": Ticket.search_count(domain),
                "ticket_open": Ticket.search_count(open_domain),
                "ticket_in_progress": Ticket.search_count(Domain.AND([open_domain, [("user_id", "!=", False)]])),
                "ticket_resolved": Ticket.search_count(closed_domain),
                "ticket_unassigned": Ticket.search_count(Domain.AND([open_domain, [("user_id", "=", False)]])),
                "page_name": "service_center",
                "no_index": True,
            },
        )

    @route("/my/company", type="http", auth="user", website=True, sitemap=False)
    def company_profile(self, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        change_requests = request.env["b2b.contact.request"].search(
            [
                ("commercial_partner_id", "=", company.id),
                ("request_type", "in", ("company_change", "user_change")),
            ],
            order="create_date desc",
            limit=5,
        )
        return request.render(
            "b2b_website.company_profile",
            {
                "company": company,
                "change_requests": change_requests,
                "page_name": "company_profile",
                "no_index": True,
            },
        )

    def _company_change_values(self, form=None, error=None):
        request_kind = (form or {}).get("request_type") or request.params.get(
            "type", "company_change"
        )
        if request_kind not in ("company_change", "user_change"):
            request_kind = "company_change"
        return {
            "company": request.env.user.partner_id.commercial_partner_id,
            "countries": request.env["res.country"].sudo().search([], order="name"),
            "request_kind": request_kind,
            "form": dict(form or {}),
            "submission_token": self._submission_token(form),
            "error": error,
            "page_name": "company_profile",
            "no_index": True,
        }

    @route(
        "/my/company/change", type="http", auth="user", website=True,
        methods=["GET", "POST"], sitemap=False,
    )
    def company_change(self, **form):
        if request.httprequest.method == "GET":
            return request.render(
                "b2b_website.company_change_form",
                self._company_change_values(form=form),
            )
        company = request.env.user.partner_id.commercial_partner_id
        contact = request.env.user.partner_id
        try:
            base_values = self._clean_contact_form(
                {
                    **form,
                    "contact_name": contact.name,
                    "email": contact.email or company.email,
                    "phone": contact.phone or company.phone,
                    "company_name": company.name,
                    "subject": _("Company account change request"),
                },
                allowed_types={"company_change", "user_change"},
            )
            country = request.env["res.country"].sudo().browse(
                self._safe_int(form.get("requested_country_id"))
            ).exists()
            requested_email = (form.get("requested_email") or "").strip()[:254]
            if requested_email and not tools.single_email_re.match(requested_email):
                raise ValidationError(_("Please enter a valid requested business email."))
            base_values.update({
                "partner_id": contact.id,
                "website_id": request.website.id,
                "source_url": "/my/company/change",
                "requested_company_name": (form.get("requested_company_name") or "").strip()[:200],
                "requested_vat": (form.get("requested_vat") or "").strip()[:128],
                "requested_email": requested_email,
                "requested_phone": (form.get("requested_phone") or "").strip()[:64],
                "requested_street": (form.get("requested_street") or "").strip()[:200],
                "requested_street2": (form.get("requested_street2") or "").strip()[:200],
                "requested_city": (form.get("requested_city") or "").strip()[:128],
                "requested_zip": (form.get("requested_zip") or "").strip()[:32],
                "requested_country_id": country.id,
            })
            submission, is_new = self._claim_submission(form, "company_change")
            if not is_new:
                return self._completed_submission_redirect(submission)
            change_request = request.env["b2b.contact.request"].sudo().create(base_values)
            response_url = "/my/company?change_submitted=%s" % change_request.name
            submission.complete(response_url, change_request)
        except ValidationError as error:
            return request.render(
                "b2b_website.company_change_form",
                self._company_change_values(form=form, error=error.args[0]),
            )
        return request.redirect(response_url, code=303)

    @route("/my/company/users", type="http", auth="user", website=True, sitemap=False)
    def company_users(self, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        contacts = request.env["res.partner"].search([
            ("id", "child_of", company.id),
            ("is_company", "=", False),
        ], order="name")
        return request.render(
            "b2b_website.company_users",
            {
                "company": company,
                "contacts": contacts,
                "page_name": "company_users",
                "no_index": True,
            },
        )

    @route(["/", "/partner-home"], type="http", auth="public", website=True, sitemap=True)
    def index(self, **kwargs):
        domain = self._service().visible_domain(website=self._website())
        fallback = request.env["product.template"].sudo().search(
            domain, limit=10, order="website_sequence, name, id"
        )
        default_recommended = self._configured_home_products("recommended") or fallback
        recommended = self._recommended_products(default_recommended)
        special = self._configured_home_products("special")
        best_sellers = self._configured_home_products("best_seller")
        all_featured = recommended | special | best_sellers
        return request.render(
            "b2b_website.partner_hub_homepage",
            self._catalog_values(
                all_featured,
                recommended_products=recommended,
                special_products=special,
                best_seller_products=best_sellers,
                featured_prices=self._service().price_payload(
                    all_featured, website=self._website()
                ),
                featured_procurement={
                    product.id: self._service().procurement_info(
                        product.product_variant_id,
                        pricelist=request.pricelist,
                        website=self._website(),
                    )
                    for product in all_featured
                },
                root_categories=self._category_rows(),
                homepage_brands=request.env["b2b.product.brand"].sudo().search([
                    ("active", "=", True),
                    ("website_published", "=", True),
                    ("product_ids", "any", domain),
                ], order="sequence, name, id"),
                catalog_total=request.env["product.template"].sudo().search_count(domain),
                page_name="partner_home",
            ),
        )

    @route("/b2b/categories", type="jsonrpc", auth="public", website=True)
    def category_children(self, parent_id=False, brand_id=False):
        parent_id = self._safe_int(parent_id)
        brand_id = self._safe_int(brand_id)
        brand = request.env["b2b.product.brand"].sudo().browse(brand_id).exists()
        if brand and (not brand.active or not brand.website_published):
            brand = request.env["b2b.product.brand"]
        rows = self._category_rows(parent_id=parent_id, brand=brand)
        parent = request.env["product.public.category"].sudo().browse(parent_id).exists()
        breadcrumbs = []
        if parent:
            breadcrumbs = [
                {"id": category.id, "name": category.name}
                for category in parent.parents_and_self
            ]
        return {
            "categories": [{key: row[key] for key in ("id", "name", "has_children", "image_url")} for row in rows],
            "breadcrumbs": breadcrumbs,
        }

    @route(
        '/brands/<model("b2b.product.brand"):brand>',
        type="http", auth="public", website=True, sitemap=True,
    )
    def brand_detail(self, brand, **kwargs):
        if not brand.active or not brand.website_published:
            raise NotFound()
        domain = Domain.AND([
            self._service().visible_domain(website=self._website()),
            [("b2b_brand_id", "=", brand.id)],
        ])
        products = request.env["product.template"].sudo().search(
            domain, limit=4, order="website_sequence, name, id"
        )
        return request.render("b2b_website.brand_detail", {
            "brand": brand,
            "brand_categories": self._category_rows(brand=brand),
            "brand_products": products,
            "brand_prices": self._service().price_payload(products, website=self._website()),
            "brand_focus": [item.strip() for item in (brand.product_focus or "").splitlines() if item.strip()],
            "brand_advantages": [item.strip() for item in (brand.advantages or "").splitlines() if item.strip()],
            "page_name": "partner_brand",
        })

    @route("/repair-service", type="http", auth="public", website=True, sitemap=True)
    def repair_service_page(self, **kwargs):
        return request.render("b2b_website.repair_service_page", {
            "page_name": "repair_service",
        })

    @route("/warranty", type="http", auth="public", website=True, sitemap=True)
    def warranty_page(self, **kwargs):
        return request.render("b2b_website.warranty_page", {
            "page_name": "warranty",
        })

    @route(["/products", "/products/page/<int:page>"], type="http", auth="public", website=True, sitemap=True)
    def products(self, page=1, **query):
        page = max(page, 1)
        domain = self._catalog_domain(query)
        Product = request.env["product.template"].sudo()
        total = Product.search_count(domain)
        step = 24
        url_args = {
            key: query.get(key)
            for key in ("search", "category", "brand", "tag", "application", "sort")
            if query.get(key)
        }
        pager = portal_pager(
            url="/products", total=total, page=page, step=step, url_args=url_args
        )
        sort = query.get("sort") if query.get("sort") in {
            "featured", "name", "name_desc", "newest"
        } else "featured"
        sort_orders = {
            "featured": "website_sequence, name",
            "name": "name",
            "name_desc": "name desc",
            "newest": "create_date desc, name",
        }
        products = Product.search(
            domain,
            limit=step,
            offset=pager["offset"],
            order=sort_orders[sort],
        )
        return request.render(
            "b2b_website.product_catalog",
            self._catalog_values(
                products,
                active_filter_count=sum(
                    bool(query.get(key))
                    for key in ("category", "brand", "tag", "application")
                ),
                pager=pager,
                total=total,
                query=query,
                sort=sort,
                page_name="partner_products",
            ),
        )

    @route(
        '/products/<model("product.template"):product>',
        type="http", auth="public", website=True, sitemap=True,
        handle_params_access_error=lambda error, **kwargs: NotFound.code,
    )
    def product_detail(self, product, **kwargs):
        service = self._service()
        if not service.is_visible(product, website=self._website()):
            raise NotFound()
        self._track_product_view(product)
        variant = product.product_variant_id
        price_state = service.price_state(website=self._website())
        procurement = service.procurement_info(
            variant,
            pricelist=request.pricelist,
            website=self._website(),
        )
        if price_state == "visible":
            combination_info = product.with_context(
                website_sale_stock_get_quantity=True
            )._get_combination_info(
                product_id=variant.id,
                add_qty=procurement["minimum_quantity"],
                uom_id=variant.uom_id.id,
            )
            procurement = service.procurement_info(
                variant,
                pricelist=request.pricelist,
                website=self._website(),
                combination_info=combination_info,
            )
            price = {
                "state": "visible",
                "price": combination_info["price"],
                "currency": combination_info["currency"],
                "uom_name": procurement["uom_name"],
            }
        else:
            price = {"state": price_state}
        media = product.product_template_image_ids
        related = product.alternative_product_ids.filtered_domain(
            service.visible_domain(website=self._website())
        )[:4]
        values = {
            "product": product,
            "variant": variant,
            "media": media,
            "resources": service.allowed_documents(product, website=self._website()),
            "price": price,
            "procurement": procurement,
            "related": related,
            "related_prices": service.price_payload(related, website=self._website()),
            "sample_allowed": self._sample_allowed(),
            "no_index": product.b2b_visibility_mode != "all",
            "page_name": "partner_product_detail",
        }
        return request.render("b2b_website.product_detail", values)

    @route("/products/resource/<int:document_id>", type="http", auth="public", website=True)
    def product_resource(self, document_id, **kwargs):
        document = request.env["product.document"].sudo().browse(document_id).exists()
        if not document or not self._service().document_is_allowed(
            document, website=self._website()
        ):
            raise NotFound()
        if document.type == "url":
            parsed = urlparse(document.url or "")
            if parsed.scheme not in ("http", "https"):
                raise NotFound()
            return request.redirect(document.url, local=False)
        stream = request.env["ir.binary"]._get_stream_from(document.ir_attachment_id)
        return stream.get_response(as_attachment=True)

    def _sample_defaults(self, product=False):
        contact = request.env.user.partner_id
        company = contact.commercial_partner_id
        templates = request.env["product.template"].sudo().search(
            self._service().visible_domain(website=self._website()),
            limit=200,
            order="name",
        )
        return {
            "product": product,
            "sample_products": templates.product_variant_ids,
            "contact_name": contact.name or "",
            "company_name": company.name or "",
            "email": contact.email or company.email or "",
            "phone": contact.phone or company.phone or "",
            "shipping_address": contact.contact_address or company.contact_address or "",
            "shipping_partners": request.env["res.partner"].search([
                ("id", "child_of", company.id), ("type", "=", "delivery")
            ]),
            "submission_token": self._submission_token(request.params),
        }

    @route("/sample/request", type="http", auth="user", website=True, methods=["GET", "POST"])
    def sample_request(self, **post):
        product_id = self._safe_int(post.get("product_id") or request.params.get("product_id"))
        product = request.env["product.product"].browse(product_id).exists()
        if product and not self._service().is_visible(product.product_tmpl_id):
            raise NotFound()
        values = self._sample_defaults(product)
        values.update({
            "post": post,
            "error": False,
            "sample_allowed": self._sample_allowed(),
            "page_name": "sample_request",
        })
        if request.httprequest.method == "POST":
            try:
                quantity = float(post.get("quantity") or 0)
                if not math.isfinite(quantity) or not 0 < quantity <= 10000:
                    raise ValidationError(_("Sample quantity must be between 0 and 10,000."))
                submission, is_new = self._claim_submission(post, "sample_request")
                if not is_new:
                    return self._completed_submission_redirect(submission)
                sample = request.env["b2b.sample.request"].create({
                    "contact_name": (post.get("contact_name") or "").strip(),
                    "company_name": (post.get("company_name") or "").strip(),
                    "email": (post.get("email") or "").strip(),
                    "phone": (post.get("phone") or "").strip(),
                    "shipping_partner_id": self._safe_int(post.get("shipping_partner_id")),
                    "shipping_address": (post.get("shipping_address") or "").strip(),
                    "reason": (post.get("reason") or "").strip(),
                    "notes": (post.get("notes") or "").strip(),
                    "line_ids": [Command.create({
                        "product_id": product.id if product else False,
                        "quantity": quantity,
                        "uom_id": product.uom_id.id if product else False,
                    })],
                })
                response_url = "/my/sample-requests/%s?submitted=1" % sample.id
                submission.complete(response_url, sample.sudo())
                return request.redirect(response_url, code=303)
            except (AccessError, UserError, ValidationError, ValueError) as error:
                values["error"] = str(error)
        return request.render("b2b_website.sample_request_form", values)

    def _owned_orders(self):
        company = request.env.user.partner_id.commercial_partner_id
        try:
            return request.env["sale.order"].search([
                ("partner_id", "child_of", company.id),
                ("state", "in", ("sale", "done")),
            ], order="date_order desc", limit=100)
        except AccessError:
            # Internal users without Sales access may still visit the public
            # Partner Hub navigation. Render the safe empty state instead of a
            # framework 403; no records are elevated or disclosed.
            return request.env["sale.order"]

    def _service_defaults(self):
        contact = request.env.user.partner_id
        company = contact.commercial_partner_id
        orders = self._owned_orders()
        # Orders were selected through the portal rule above.  Read their historic
        # lines with elevation so a product that was later unpublished or removed
        # from the customer's segment cannot make the entire service form fail.
        # Only products actually bought on those owned orders are returned.
        order_lines = orders.sudo().order_line.filtered(
            lambda line: not line.display_type and line.product_id
        )
        products = order_lines.product_id
        return {
            "orders": orders,
            "products": products,
            "contact_name": contact.name or "",
            "company_name": company.name or "",
            "email": contact.email or company.email or "",
            "phone": contact.phone or company.phone or "",
            "submission_token": self._submission_token(request.params),
        }

    def _validated_uploads(self):
        uploads = request.httprequest.files.getlist("attachments")
        uploads = [upload for upload in uploads if upload and upload.filename]
        if len(uploads) > MAX_UPLOADS:
            raise ValidationError(_("You can attach at most five files."))
        result = []
        for upload in uploads:
            filename = secure_filename(upload.filename or "")[:255]
            extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            content = upload.read(MAX_UPLOAD_SIZE + 1)
            signatures = ALLOWED_UPLOADS.get(extension)
            if not filename or not signatures or len(content) > MAX_UPLOAD_SIZE:
                raise ValidationError(_("Attachments must be PDF, PNG, JPEG, or ZIP and no larger than 10 MB."))
            if not any(content.startswith(signature) for signature in signatures):
                raise ValidationError(_("An attachment does not match its declared file type."))
            result.append((filename, content, upload.mimetype or "application/octet-stream"))
        return result

    @route("/service", type="http", auth="user", website=True, methods=["GET", "POST"])
    def service_request(self, **post):
        values = self._service_defaults()
        values.update({"post": post, "error": False, "page_name": "service_request"})
        if request.httprequest.method == "POST":
            try:
                order = request.env["sale.order"].browse(self._safe_int(post.get("order_id"))).exists()
                product = request.env["product.product"].browse(self._safe_int(post.get("product_id"))).exists()
                request_type = post.get("request_type")
                description = (post.get("description") or "").strip()
                if order not in values["orders"]:
                    raise AccessError(_("Select a product from one of your completed or confirmed orders."))
                historical_products = order.sudo().order_line.filtered(
                    lambda line: not line.display_type and line.product_id
                ).product_id
                if product.id not in historical_products.ids:
                    raise AccessError(_("Select a product from one of your completed or confirmed orders."))
                product = historical_products.filtered(lambda item: item.id == product.id)[:1]
                if request_type not in ("repair", "replacement") or not description:
                    raise ValidationError(_("Complete the request type and problem description."))
                fields_to_limit = {
                    "contact_name": 160, "company_name": 200, "email": 254,
                    "phone": 64, "model_number": 160, "serial_number": 160,
                    "description": 8000,
                }
                for key, limit in fields_to_limit.items():
                    if len(post.get(key) or "") > limit:
                        raise ValidationError(_("A service request field exceeds the allowed length."))
                if any(not (post.get(key) or "").strip() for key in (
                    "contact_name", "company_name", "email", "phone", "model_number"
                )):
                    raise ValidationError(_("Complete all required contact fields."))
                if not tools.single_email_re.match((post.get("email") or "").strip()):
                    raise ValidationError(_("Please enter a valid email address."))
                uploads = self._validated_uploads()
                team_id = self._safe_int(request.env["ir.config_parameter"].sudo().get_param(
                    "b2b_website.helpdesk_team_id"
                ))
                team = request.env["helpdesk.team"].sudo().browse(team_id).exists()
                if not team:
                    raise UserError(_("Partner service is not configured yet. Please contact us."))
                submission, is_new = self._claim_submission(post, "service_request")
                if not is_new:
                    return self._completed_submission_redirect(submission)
                safe_description = Markup("<p>%s</p><p>%s</p>") % (
                    escape(_("Submitted from Partner Hub at %s", fields.Datetime.now())),
                    escape(description).replace("\n", Markup("<br/>")),
                )
                contact = request.env.user.partner_id
                ticket = request.env["helpdesk.ticket"].sudo().create({
                    "name": _("%s request for %s", request_type.title(), product.display_name),
                    "team_id": team.id,
                    "partner_id": contact.id,
                    "description": safe_description,
                    "b2b_request_type": request_type,
                    "b2b_product_id": product.id,
                    "b2b_model_number": (post.get("model_number") or "").strip(),
                    "b2b_serial_number": (post.get("serial_number") or "").strip(),
                    "b2b_sale_order_id": order.id,
                    "sale_order_id": order.id,
                    "b2b_contact_name": (post.get("contact_name") or "").strip(),
                    "b2b_company_name": (post.get("company_name") or "").strip(),
                    "b2b_contact_phone": (post.get("phone") or "").strip(),
                    "b2b_contact_email": (post.get("email") or "").strip(),
                    "b2b_submitted_at": fields.Datetime.now(),
                })
                for filename, content, mimetype in uploads:
                    request.env["ir.attachment"].sudo().create({
                        "name": filename,
                        "raw": content,
                        "mimetype": mimetype,
                        "res_model": "helpdesk.ticket",
                        "res_id": ticket.id,
                    })
                ticket.message_subscribe(partner_ids=[contact.id])
                ticket.message_post(body=_("Service request submitted through Partner Hub."))
                response_url = "/service-center?submitted=1"
                submission.complete(response_url, ticket)
                return request.redirect(response_url, code=303)
            except (AccessError, UserError, ValidationError) as error:
                values["error"] = str(error)
        return request.render("b2b_website.service_request_form", values)

    @route("/my/orders/<int:order_id>/erp-status", type="http", auth="user", website=True)
    def order_erp_status(self, order_id, **kwargs):
        company = request.env.user.partner_id.commercial_partner_id
        # Resolve without the portal record rule so unauthorized ids return the
        # same 404 as missing ids instead of leaking existence through a 403.
        order = request.env["sale.order"].sudo().browse(order_id).exists()
        if not order or order.partner_id.commercial_partner_id != company:
            raise NotFound()
        status = False
        error = False
        try:
            status = request.env["b2b.erp.service"].get_order_status(
                order, {"commercial_partner_id": company.id}
            )
        except (UserError, ValidationError):
            error = _("ERP order tracking is temporarily unavailable. Please try again later.")
        return request.render(
            "b2b_website.order_erp_status",
            {"order": order, "status": status, "error": error, "page_name": "erp_status"},
        )
