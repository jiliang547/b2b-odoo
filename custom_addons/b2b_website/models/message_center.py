from odoo import _, api, fields, models, Command, SUPERUSER_ID
from odoo.exceptions import AccessError, ConcurrencyError, ValidationError
from odoo.tools import html2plaintext, email_normalize
from psycopg2 import IntegrityError
from .customer_message_policy import CUSTOMER_MESSAGE_SOURCES, customer_context


MESSAGE_CENTER_MODELS = tuple(CUSTOMER_MESSAGE_SOURCES)
MESSAGE_CENTER_MODEL_LABELS = {name: values[0] for name, values in CUSTOMER_MESSAGE_SOURCES.items()}


def public_comment(message, msg_vals=None):
    values = msg_vals or {}
    return (values.get("message_type", message.message_type) in ("comment", "email")
            and not values.get("is_internal", message.is_internal)
            and bool(message.subtype_id) and not message.subtype_id.internal)


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def write(self, vals):
        result = super().write(vals)
        ownership_fields = {"partner_id", "contact_id", "order_id", "website_id", "company_id", "parent_id", "is_company", "company_type", "b2b_selling_company_id"}
        if self.env.registry.ready and self._name in MESSAGE_CENTER_MODELS and ownership_fields.intersection(vals):
            threads = self.env["b2b.message.thread"].sudo().search([
                ("source_model", "=", self._name), ("res_id", "in", self.ids)])
            if self._name == "res.partner" and {"parent_id", "is_company", "company_type", "b2b_selling_company_id"}.intersection(vals):
                threads |= self.env["b2b.message.thread"].sudo().search([
                    ("partner_id", "child_of", self.ids)])
            for thread in threads:
                source = self.env[thread.source_model].sudo().browse(thread.res_id).exists()
                values = thread._source_values(source) if source else None
                if not values or values["commercial_partner_id"] != thread.commercial_partner_id.id:
                    # Do not transfer the old customer's conversation/preview
                    # when a business record is reassigned to another customer.
                    thread.unlink()
                else:
                    thread.write(values)
        return result

    def _b2b_message_center_is_public_comment(self, message, msg_vals=None):
        return self._name in MESSAGE_CENTER_MODELS and public_comment(message, msg_vals)

    def _b2b_customer_message_context(self):
        self.ensure_one()
        if self.env.uid == SUPERUSER_ID and self.env.context.get("install_demo"):
            # Native demo bootstrap is not a customer conversation. Do not
            # impose commercial ownership on Odoo's demonstration records.
            # A portal request carrying the same context flag cannot bypass it.
            return None
        return customer_context(self)

    def _mail_get_operation_for_mail_message_operation(self, operation):
        access = super()._mail_get_operation_for_mail_message_operation(operation)
        user = self.env.user
        if operation == "create" and self._name in MESSAGE_CENTER_MODELS and not user._is_internal() and not user._is_public():
            for source in self:
                context = source.sudo()._b2b_customer_message_context()
                if context and context["partner"].commercial_partner_id == user.partner_id.commercial_partner_id:
                    # Comment permission is not business-record write access.
                    # The native controller still checks the source read ACL,
                    # record rule and message/attachment permissions normally.
                    access[source] = "read"
        return access

    def _b2b_post_customer_message(self, body, **kwargs):
        """Explicit customer events use the same native transport as human replies."""
        self.ensure_one()
        values = dict(kwargs, body=body, message_type="comment", subtype_xmlid="mail.mt_comment")
        if self.env.su and self.env.user.share and not values.get("author_id"):
            # Payment callbacks/polling retain the visitor's uid under sudo.
            # Automatic status events are system messages, not customer replies
            # (which always supply their authenticated author explicitly).
            values["author_id"] = self.env.ref("base.partner_root").id
        return self.message_post(**values)

    def _b2b_message_center_partners(self):
        context = self.sudo()._b2b_customer_message_context()
        return context["recipients"] if context else self.env["res.partner"]

    def _message_get_suggested_recipients_batch(self, *args, **kwargs):
        suggested = super()._message_get_suggested_recipients_batch(*args, **kwargs)
        if self._name not in MESSAGE_CENTER_MODELS:
            return suggested
        for source in self:
            context = source.sudo()._b2b_customer_message_context()
            if not context or not context["partner"]:
                continue
            owner = context["partner"].commercial_partner_id
            customers = context["recipients"].filtered(lambda partner: partner.partner_share and partner.email_normalized)
            rows = [{"partner_id": partner.id, "email": partner.email_normalized,
                     "name": partner.name, "create_values": {}} for partner in customers]
            rows += suggested.get(source.id, [])
            clean, seen = [], set()
            for row in rows:
                partner = self.env['res.partner'].sudo().browse(row.get('partner_id')).exists()
                email = (row.get('email') or '').lower()
                if not email or email in seen:
                    continue
                if not partner or (partner.partner_share and partner.commercial_partner_id != owner):
                    continue
                if not partner.partner_share and context["company"] and not partner.user_ids.filtered(
                        lambda user: user.active and context["company"] in user.company_ids):
                    continue
                clean.append(row)
                seen.add(email)
            # Reuse Odoo's composer, but do not ask staff to invent an email
            # for a company when its actual portal contact already has one.
            suggested[source.id] = clean
        return suggested

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        public = self and self._b2b_message_center_is_public_comment(message, msg_vals)
        context = self.sudo()._b2b_customer_message_context() if public else None
        author = message.author_id.sudo()
        foreign_author = bool(context and context["partner"] and author.partner_share
                              and author.commercial_partner_id != context["partner"].commercial_partner_id)
        if foreign_author:
            raise ValidationError(_("This conversation belongs to a different customer."))
        if context and not foreign_author:
            owner = context["partner"].commercial_partner_id
            guest = self._name == "b2b.contact.request" and not owner
            guest_email = (email_normalize(self.sudo().email or "") or "") if guest else None
            outsiders = message.partner_ids.sudo().filtered(
                lambda partner: partner.partner_share and (
                    (owner and partner.commercial_partner_id != owner)
                    or (guest and partner.email_normalized != guest_email)))
            if outsiders:
                raise ValidationError(_("A customer conversation cannot be sent to another customer's contacts."))
            self.sudo().message_subscribe(partner_ids=context["recipients"].ids)
            if self.env.su and self.env.user.share and author == self.env.ref("base.partner_root"):
                # Native mail treats the active request user as the real
                # author, even when a system event has an explicit author.
                # A payment callback must still notify that customer.
                kwargs["notify_author"] = True
        recipients = super()._notify_get_recipients(message, msg_vals=msg_vals, **kwargs)
        internal = bool(message.is_internal or message.subtype_id.internal)
        result, seen, mailboxes = [], set(), set()
        for recipient in sorted(recipients, key=lambda item: not bool(item.get("uid"))):
            partner = self.env["res.partner"].sudo().browse(recipient.get("id")).exists()
            staff = bool(partner and not partner.partner_share)
            # Odoo notes/technical logs must never leak through an explicit
            # external mention or stale follower, including non-B2B models.
            if (internal or foreign_author) and not staff:
                continue
            if context and not foreign_author:
                owner = context["partner"].commercial_partner_id
                if partner and not staff and owner and partner.commercial_partner_id != owner:
                    continue
                if partner and not staff and guest and partner.email_normalized != guest_email:
                    continue
                if staff and context["company"] and not partner.user_ids.filtered(
                        lambda user: user.active and not user.share and context["company"] in user.company_ids):
                    continue
                if not partner:
                    allowed = {value.lower() for value in context["recipients"].mapped("email_normalized") if value}
                    if self._name == "b2b.contact.request" and not context["partner"]:
                        allowed.add(guest_email)
                    if (recipient.get("email_normalized") or "").lower() not in allowed:
                        continue
                recipient["notif"] = "email" if recipient.get("email_normalized") else "inbox"
                mailbox = (recipient.get("email_normalized") or "").lower()
                if mailbox and mailbox in mailboxes and not recipient.get("uid"):
                    continue  # Company and its portal contact share one mailbox.
                if mailbox:
                    mailboxes.add(mailbox)
            key = recipient.get("id") or recipient.get("email_normalized")
            if key and key not in seen:
                result.append(recipient)
                seen.add(key)
        return result

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        if self and self._b2b_message_center_is_public_comment(message, msg_vals):
            context = self.sudo()._b2b_customer_message_context()
            if context and context["partner"] and context["partner"] not in message.partner_ids:
                # Preserve the intended customer on the native message itself,
                # including customers without email. A later record/customer
                # reassignment must not transfer this conversation's history.
                message.sudo().write({"partner_ids": [Command.link(context["partner"].id)]})
        # Index once before native notification layout generation. Transport,
        # mail queue/retries, attachments and delivery status remain native.
        thread = self.env["b2b.message.thread"].sudo()._sync_from_message(message)
        recipients = super()._notify_thread(message, msg_vals=msg_vals, **kwargs)
        if thread and not self.env.context.get("b2b_skip_portal_unread"):
            ids = [recipient["id"] for recipient in recipients if recipient.get("id")]
            if ids:
                self.env["mail.notification"].sudo().search([
                    ("mail_message_id", "=", message.id), ("res_partner_id", "in", ids),
                ]).write({"is_read": False, "read_date": False})
        return recipients

    def _notify_get_action_link(self, link_type, **kwargs):
        if link_type == "view" and len(self) == 1 and self._name in MESSAGE_CENTER_MODELS:
            if CUSTOMER_MESSAGE_SOURCES[self._name][1] and isinstance(self, self.env.registry['portal.mixin']):
                # Keep native quotation/payment and service-document email
                # actions. Message Center itself still opens the conversation.
                return super()._notify_get_action_link(link_type, **kwargs)
            thread = self.env["b2b.message.thread"].sudo().search([
                ("source_model", "=", self._name), ("res_id", "=", self.id),
            ], limit=1)
            if thread:
                portal_users = self.env["res.users"].sudo().search_count([
                    ("active", "=", True), ("share", "=", True),
                    ("partner_id.commercial_partner_id", "=", thread.commercial_partner_id.id),
                ], limit=1) if thread.commercial_partner_id else 0
                if portal_users:
                    return self.get_base_url() + thread.portal_url()
                # Preserve native token-based quotation/invoice links when a
                # contact has not yet been invited to the customer portal.
        return super()._notify_get_action_link(link_type, **kwargs)


class B2BMessageThread(models.Model):
    _name = "b2b.message.thread"
    _description = "Partner Hub Message Thread"
    _order = "last_message_at desc, id desc"

    source_model = fields.Selection(
        [(model, label) for model, label in MESSAGE_CENTER_MODEL_LABELS.items()],
        required=True,
        index=True,
        readonly=True,
    )
    res_id = fields.Integer(required=True, index=True, readonly=True)
    name = fields.Char(required=True, index=True, readonly=True)
    subject = fields.Char(index=True, readonly=True)
    source_type = fields.Char(readonly=True)
    partner_id = fields.Many2one("res.partner", index=True, readonly=True)
    commercial_partner_id = fields.Many2one("res.partner", index=True, readonly=True)
    website_id = fields.Many2one("website", index=True, readonly=True)
    company_id = fields.Many2one("res.company", index=True, readonly=True)
    assigned_user_id = fields.Many2one("res.users", index=True, readonly=True)
    last_message_id = fields.Many2one(
        "mail.message", required=True, index=True, readonly=True, ondelete="cascade"
    )
    last_message_at = fields.Datetime(required=True, index=True, readonly=True)
    last_author_id = fields.Many2one("res.partner", readonly=True)
    last_author_name = fields.Char(compute="_compute_last_author_name", compute_sudo=False)
    last_message_preview = fields.Char(readonly=True)
    is_unread = fields.Boolean(compute="_compute_is_unread", string="Unread")

    _source_unique = models.Constraint(
        "UNIQUE(source_model, res_id)",
        "Only one Message Center thread may represent a business record.",
    )

    @api.depends("last_author_id", "last_author_id.name")
    def _compute_last_author_name(self):
        # Author labels are public conversation metadata, not permission to
        # browse the internal address book. Check the thread before elevating
        # only the name lookup; never sudo the portal's thread search.
        self.check_access("read")
        for thread in self:
            author = thread.last_author_id.sudo()
            thread.last_author_name = (_("Our team") if author == self.env.ref("base.partner_root")
                                       else author.name or _("Our team"))

    @api.model
    def _source_values(self, source):
        context = source._b2b_customer_message_context()
        if not context:
            return None
        partner = context["partner"]
        related = context["related"]
        name = source.display_name
        if related:
            name = "%s / %s" % (name, related.display_name)
        return {
            "source_model": source._name, "res_id": source.id,
            "name": name, "subject": (source.subject if source._name == "b2b.contact.request" else name),
            "source_type": context["label"], "partner_id": partner.id,
            "commercial_partner_id": partner.commercial_partner_id.id,
            "website_id": context["website"].id, "company_id": context["company"].id,
            "assigned_user_id": context["staff"].id,
        }

    @api.model
    def _sync_from_message(self, message):
        if (
            message.model not in MESSAGE_CENTER_MODELS
            or not message.res_id
            or not public_comment(message)
        ):
            return self.browse()
        source = self.env[message.model].sudo().browse(message.res_id).exists()
        if not source:
            return self.browse()
        values = self._source_values(source)
        if not values:
            return self.browse()
        author = message.author_id.sudo()
        if author.partner_share and values["commercial_partner_id"] and author.commercial_partner_id.id != values["commercial_partner_id"]:
            return self.browse()
        external = (message.partner_ids | message.notification_ids.res_partner_id).sudo().filtered("partner_share")
        if external and values["commercial_partner_id"] and any(
                partner.commercial_partner_id.id != values["commercial_partner_id"] for partner in external):
            return self.browse()
        values.update({
            "last_message_id": message.id,
            "last_message_at": message.date,
            "last_author_id": message.author_id.id,
            "last_message_preview": html2plaintext(message.body or "").strip()[:240],
        })
        thread = self.sudo().search([
            ("source_model", "=", message.model),
            ("res_id", "=", message.res_id),
        ], limit=1)
        if thread:
            if (thread.last_message_at, thread.last_message_id.id) <= (message.date, message.id):
                thread.write(values)
            return thread
        try:
            with self.env.cr.savepoint():
                return self.sudo().create(values)
        except IntegrityError as error:
            # Simultaneous native messages still produce one conversation.
            thread = self.sudo().search([("source_model", "=", message.model), ("res_id", "=", message.res_id)], limit=1)
            if not thread:
                if (error.diag.constraint_name or "").endswith("source_unique"):
                    # Under repeatable-read the winner may not yet be visible.
                    # Let Odoo retry the whole transaction, not a second email.
                    raise ConcurrencyError("Concurrent customer conversation creation") from error
                raise
            return self.sudo()._sync_from_message(message)

    @api.model
    def _notification_domain(self, partner=None):
        partner = partner or self.env.user.partner_id
        return [
            ("res_partner_id", "=", partner.id),
            ("is_read", "=", False),
            ("mail_message_id.model", "in", MESSAGE_CENTER_MODELS),
            ("mail_message_id.message_type", "in", ("comment", "email")),
            ("mail_message_id.is_internal", "=", False),
            ("mail_message_id.subtype_id.internal", "=", False),
            ("mail_message_id.subtype_id", "!=", False),
        ]

    def _compute_is_unread(self):
        by_source = {
            (notification.mail_message_id.model, notification.mail_message_id.res_id)
            for notification in self.env["mail.notification"].sudo().search(
                self._notification_domain()
            )
        }
        for thread in self:
            thread.is_unread = (thread.source_model, thread.res_id) in by_source

    @api.model
    def get_portal_unread_message_count(self):
        if self.env.user._is_public():
            return 0
        notifications = self.env["mail.notification"].sudo().search(
            self._notification_domain()
        )
        candidate_sources = {
            (item.mail_message_id.model, item.mail_message_id.res_id)
            for item in notifications
        }
        if not candidate_sources:
            return 0
        visible = self.search([
            ("source_model", "in", list({item[0] for item in candidate_sources})),
            ("res_id", "in", list({item[1] for item in candidate_sources})),
        ])
        return sum(
            (thread.source_model, thread.res_id) in candidate_sources
            for thread in visible
        )

    @api.model
    def get_backend_unread_message_count(self):
        return self.get_portal_unread_message_count()

    def action_mark_read(self, partner=None):
        self.check_access("read")
        partner = partner or self.env.user.partner_id
        if not self.env.user._is_internal() and partner != self.env.user.partner_id:
            raise AccessError(_("You can only change your own message read state."))
        for thread in self:
            self.env["mail.notification"].sudo().search([
                ("res_partner_id", "=", partner.id),
                ("is_read", "=", False),
                ("mail_message_id.model", "=", thread.source_model),
                ("mail_message_id.res_id", "=", thread.res_id),
            ]).write({"is_read": True, "read_date": fields.Datetime.now()})
        return True

    def action_open_source(self):
        self.ensure_one()
        self.action_mark_read()
        source = self.env[self.source_model].browse(self.res_id).exists()
        if not source:
            return {"type": "ir.actions.act_window_close"}
        try:
            source.check_access("read")
        except AccessError:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("Conversation unavailable"),
                    "message": _(
                        "Select the record's company in the company switcher, "
                        "or ask an administrator to grant company access."
                    ),
                    "type": "warning",
                    "sticky": False,
                },
            }
        return {
            "type": "ir.actions.act_window",
            "name": self.subject,
            "res_model": self.source_model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    def portal_url(self):
        self.ensure_one()
        return "/my/messages/%s/open" % self.id

    def _customer_source(self):
        """Authorize the *current* owner, not merely a stale index snapshot."""
        self.ensure_one()
        source = self.env[self.source_model].sudo().browse(self.res_id).exists()
        context = source._b2b_customer_message_context() if source else None
        if not context:
            raise AccessError(_("This conversation is unavailable."))
        user = self.env.user
        if user._is_internal():
            source.with_user(user).check_access("read")
        elif (not self.commercial_partner_id
              or self.commercial_partner_id != user.partner_id.commercial_partner_id
              or context["partner"].commercial_partner_id != self.commercial_partner_id
              or context["company"] != self.company_id):
            raise AccessError(_("This conversation belongs to a different customer."))
        return source, context

    def _customer_messages(self):
        source, context = self._customer_source()
        owner = context["partner"].commercial_partner_id
        messages = self.env["mail.message"].sudo().search([
            ("model", "=", source._name), ("res_id", "=", source.id),
            ("message_type", "in", ("comment", "email")), ("is_internal", "=", False),
            ("subtype_id", "!=", False), ("subtype_id.internal", "=", False),
        ], order="date asc, id asc")
        def visible(message):
            author = message.author_id
            if author.partner_share and owner and author.commercial_partner_id != owner:
                return False
            external = (message.partner_ids | message.notification_ids.res_partner_id).filtered("partner_share")
            return not owner or not any(partner.commercial_partner_id != owner for partner in external)
        return messages.filtered(visible)

    @api.model
    def _backfill_customer_messages(self):
        """Index historical public conversations only; never resend old mail."""
        last_id = 0
        while True:
            messages = self.env["mail.message"].sudo().search([
                ("id", ">", last_id), ("model", "in", MESSAGE_CENTER_MODELS),
                ("message_type", "in", ("comment", "email")),
                ("is_internal", "=", False), ("subtype_id", "!=", False),
                ("subtype_id.internal", "=", False),
            ], order="id", limit=500)
            if not messages:
                break
            for message in messages:
                self._sync_from_message(message)
            last_id = messages[-1].id
        return True
