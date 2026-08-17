import math
from urllib.parse import urlparse

from markupsafe import Markup, escape
from werkzeug.exceptions import NotFound
from werkzeug.utils import secure_filename

from odoo import Command, _, fields, tools
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain
from odoo.http import Controller, request, route
from odoo.addons.portal.controllers.portal import pager as portal_pager


MAX_UPLOAD_SIZE = 10 * 1024 * 1024
MAX_UPLOADS = 5
ALLOWED_UPLOADS = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}


class PartnerHubWebsite(Controller):
    def _website(self):
        return request.website

    def _service(self):
        return request.env["b2b.product.service"]

    def _safe_int(self, value):
        try:
            value = int(value or 0)
            return value if value > 0 else False
        except (TypeError, ValueError):
            return False

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
            "category": "public_categ_ids",
            "brand": "b2b_brand_id",
            "tag": "product_tag_ids",
            "application": "b2b_application_ids",
        }
        for parameter, field_name in filters.items():
            value = self._safe_int(query.get(parameter))
            if value:
                domain = Domain.AND([domain, [(field_name, "in", [value])]])
        return domain

    def _catalog_values(self, products, **extra):
        Product = request.env["product.template"]
        visible = self._service().visible_domain(website=self._website())
        values = {
            "products": products,
            "prices": self._service().price_payload(products, website=self._website()),
            "categories": request.env["product.public.category"].search(
                [("product_tmpl_ids", "any", visible)], order="name"
            ),
            "brands": request.env["b2b.product.brand"].sudo().search([
                ("active", "=", True), ("product_ids", "any", visible)
            ], order="sequence, name"),
            "tags": request.env["product.tag"].search([
                ("product_template_ids", "any", visible)
            ], order="name"),
            "applications": request.env["b2b.product.application"].sudo().search([
                ("active", "=", True), ("product_ids", "any", visible)
            ], order="sequence, name"),
            "product_model": Product,
        }
        values.update(extra)
        return values

    @route("/", type="http", auth="public", website=True, sitemap=True)
    def homepage(self, **kwargs):
        products = request.env["product.template"].search(
            self._service().visible_domain(website=self._website()),
            limit=6,
            order="website_sequence, name",
        )
        return request.render(
            "b2b_website.partner_hub_homepage",
            self._catalog_values(products, page_name="partner_home"),
        )

    @route(["/products", "/products/page/<int:page>"], type="http", auth="public", website=True, sitemap=True)
    def products(self, page=1, **query):
        page = max(page, 1)
        domain = self._catalog_domain(query)
        Product = request.env["product.template"]
        total = Product.search_count(domain)
        step = 24
        url_args = {
            key: query.get(key)
            for key in ("search", "category", "brand", "tag", "application")
            if query.get(key)
        }
        pager = portal_pager(
            url="/products", total=total, page=page, step=step, url_args=url_args
        )
        products = Product.search(
            domain,
            limit=step,
            offset=pager["offset"],
            order="website_sequence, name",
        )
        return request.render(
            "b2b_website.product_catalog",
            self._catalog_values(
                products,
                pager=pager,
                total=total,
                query=query,
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
        media = product.product_template_image_ids
        related = product.alternative_product_ids.filtered_domain(
            service.visible_domain(website=self._website())
        )[:4]
        values = {
            "product": product,
            "variant": product.product_variant_id,
            "media": media,
            "resources": service.allowed_documents(product, website=self._website()),
            "price": service.price_payload(product, website=self._website())[product.id],
            "related": related,
            "related_prices": service.price_payload(related, website=self._website()),
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
        templates = request.env["product.template"].search(
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
            "phone": contact.phone or contact.mobile or company.phone or "",
            "shipping_address": contact.contact_address or company.contact_address or "",
            "shipping_partners": request.env["res.partner"].search([
                ("id", "child_of", company.id), ("type", "=", "delivery")
            ]),
        }

    @route("/sample/request", type="http", auth="user", website=True, methods=["GET", "POST"])
    def sample_request(self, **post):
        product_id = self._safe_int(post.get("product_id") or request.params.get("product_id"))
        product = request.env["product.product"].browse(product_id).exists()
        if product and not self._service().is_visible(product.product_tmpl_id):
            raise NotFound()
        values = self._sample_defaults(product)
        company = request.env.user.partner_id.commercial_partner_id
        sample_allowed = (
            not request.website.b2b_require_approved_sample or company.b2b_approved
        )
        values.update({
            "post": post,
            "error": False,
            "sample_allowed": sample_allowed,
            "page_name": "sample_request",
        })
        if request.httprequest.method == "POST":
            try:
                quantity = float(post.get("quantity") or 0)
                if not math.isfinite(quantity) or not 0 < quantity <= 10000:
                    raise ValidationError(_("Sample quantity must be between 0 and 10,000."))
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
                return request.redirect("/my/sample-requests/%s?submitted=1" % sample.id)
            except (AccessError, UserError, ValidationError, ValueError) as error:
                values["error"] = str(error)
        return request.render("b2b_website.sample_request_form", values)

    def _owned_orders(self):
        company = request.env.user.partner_id.commercial_partner_id
        return request.env["sale.order"].search([
            ("partner_id", "child_of", company.id),
            ("state", "in", ("sale", "done")),
        ], order="date_order desc", limit=100)

    def _service_defaults(self):
        contact = request.env.user.partner_id
        company = contact.commercial_partner_id
        orders = self._owned_orders()
        products = orders.order_line.product_id.filtered(
            lambda item: self._service().is_visible(item.product_tmpl_id)
        )
        return {
            "orders": orders,
            "products": products,
            "contact_name": contact.name or "",
            "company_name": company.name or "",
            "email": contact.email or company.email or "",
            "phone": contact.phone or contact.mobile or company.phone or "",
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
                if order not in values["orders"] or product not in order.order_line.product_id:
                    raise AccessError(_("Select a product from one of your completed or confirmed orders."))
                if request_type not in ("repair", "replacement") or not description:
                    raise ValidationError(_("Complete the request type and problem description."))
                fields_to_limit = {
                    "contact_name": 160, "company_name": 200, "email": 254,
                    "phone": 64, "serial_number": 160, "description": 8000,
                }
                for key, limit in fields_to_limit.items():
                    if len(post.get(key) or "") > limit:
                        raise ValidationError(_("A service request field exceeds the allowed length."))
                if any(not (post.get(key) or "").strip() for key in (
                    "contact_name", "company_name", "email", "phone"
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
                    "b2b_serial_number": (post.get("serial_number") or "").strip(),
                    "b2b_sale_order_id": order.id,
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
                return request.redirect("/my?service_submitted=1")
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
