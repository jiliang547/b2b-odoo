"""A protected view of native public messages, not access to financial records."""
import base64

from werkzeug.exceptions import NotFound
from odoo import _, fields, http
from odoo.exceptions import AccessError, ValidationError
from odoo.http import request, content_disposition
from odoo.tools import plaintext2html
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class CustomerMessages(CustomerPortal):
    def _thread(self, thread_id):
        thread = request.env["b2b.message.thread"].sudo().browse(thread_id).exists()
        if not thread:
            raise NotFound()
        try:
            source, context = thread._customer_source()
        except AccessError:
            raise NotFound()
        return thread, source, context

    def _render_conversation(self, thread, page=1, error=None, body=""):
        source, context = thread._customer_source()
        source_url = context["route"] % source.id if context["route"] else None
        if not source_url and context["related"]:
            parent = context["related"]
            if parent._name == "sale.order":
                source_url = "/my/orders/%s" % parent.id
            elif parent._name == "helpdesk.ticket":
                source_url = "/my/ticket/%s" % parent.id
        messages = thread._customer_messages()
        try:
            page = max(int(page), 1)
        except (ValueError, TypeError):
            page = 1
        pager = portal_pager(url="/my/messages/%s" % thread.id, total=len(messages), page=page, step=30)
        # Newest page first, chronological inside the displayed page.
        selected = messages.sorted(lambda message: (message.date, message.id), reverse=True)[pager["offset"]:pager["offset"] + 30]
        thread.action_mark_read(request.env.user.partner_id)
        values = self._prepare_portal_layout_values()
        values.update({
            "page_name": "inquiry_detail", "thread": thread, "messages": selected.sorted(lambda message: (message.date, message.id)),
            "message_authors": {message.id: (_("Our team") if message.author_id == request.env.ref("base.partner_root")
                                             else message.author_id.name or _("Our team")) for message in selected},
            "pager": pager, "error": error, "reply_body": body,
            "submission_key": request.env["b2b.web.submission"].new_token(),
            "source_url": source_url,
        })
        return request.render("b2b_website.portal_customer_conversation", values)

    @http.route("/my/messages/<int:thread_id>", type="http", auth="user", website=True, methods=["GET"])
    def conversation(self, thread_id, page=1, **kwargs):
        thread, source, context = self._thread(thread_id)
        return self._render_conversation(thread, page=page)

    @http.route("/my/messages/<int:thread_id>/reply", type="http", auth="user", website=True, methods=["POST"], csrf=True)
    def reply(self, thread_id, **post):
        thread, source, context = self._thread(thread_id)
        body = (post.get("body") or "").strip()
        try:
            with request.env.cr.savepoint():
                if not body or len(body) > 8000:
                    raise ValidationError(_("Enter a message of up to 8,000 characters."))
                ledger, fresh = request.env["b2b.web.submission"].claim(
                    post.get("submission_key"), "customer-message:%s" % thread.id,
                    request.env.user, request.website,
                )
                if fresh:
                    if request.env["mail.message"].sudo().search_count([
                        ("author_id", "=", request.env.user.partner_id.id),
                        ("date", ">=", fields.Datetime.subtract(fields.Datetime.now(), days=1)),
                        ("model", "=", source._name), ("message_type", "=", "comment"),
                    ]) >= 100:
                        raise ValidationError(_("Too many messages today. Please contact our team."))
                    # Ownership is checked above; elevation allows a reply but
                    # never gives the customer read/write access to accounting.
                    message = source._b2b_post_customer_message(
                        plaintext2html(body), author_id=request.env.user.partner_id.id,
                    )
                    ledger.complete("/my/messages/%s" % thread.id, result=message)
                return request.redirect(ledger.response_url or "/my/messages/%s" % thread.id, code=303)
        except ValidationError as exc:
            return self._render_conversation(thread, error=str(exc), body=body)

    @http.route("/my/messages/<int:thread_id>/attachments/<int:message_id>/<int:attachment_id>",
                type="http", auth="user", website=True, methods=["GET"])
    def attachment(self, thread_id, message_id, attachment_id, **kwargs):
        thread, source, context = self._thread(thread_id)
        message = thread._customer_messages().filtered(lambda item: item.id == message_id)
        attachment = message.attachment_ids.filtered(lambda item: item.id == attachment_id)
        if not attachment:
            raise NotFound()
        return request.make_response(base64.b64decode(attachment.datas or b""), headers=[
            ("Content-Type", "application/octet-stream"),
            ("Content-Disposition", content_disposition(attachment.name or "attachment")),
            ("X-Content-Type-Options", "nosniff"), ("Cache-Control", "private, no-store"),
        ])
