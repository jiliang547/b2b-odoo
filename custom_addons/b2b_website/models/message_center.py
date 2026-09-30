from odoo import _, api, fields, models
from odoo.exceptions import AccessError
from odoo.tools import html2plaintext


MESSAGE_CENTER_MODELS = (
    "b2b.contact.request",
    "sale.order",
    "b2b.sample.request",
    "helpdesk.ticket",
    "b2b.order.change.request",
)

MESSAGE_CENTER_MODEL_LABELS = {
    "b2b.contact.request": "Contact Request",
    "sale.order": "Order",
    "b2b.sample.request": "Sample Request",
    "helpdesk.ticket": "Support Ticket",
    "b2b.order.change.request": "Order Change",
}


class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _b2b_message_center_is_public_comment(self, message, msg_vals=None):
        msg_vals = msg_vals or {}
        model = msg_vals.get("model") or message.model or self._name
        message_type = msg_vals.get("message_type") or message.message_type
        is_internal = msg_vals.get("is_internal", message.is_internal)
        subtype_internal = bool(message.subtype_id and message.subtype_id.internal)
        return (
            model in MESSAGE_CENTER_MODELS
            and message_type in ("comment", "email")
            and not is_internal
            and not subtype_internal
        )

    def _b2b_message_center_partners(self):
        """Return the customer and responsible staff for the current record."""
        self.ensure_one()
        customer = self.env["res.partner"]
        staff = self.env["res.partner"]
        website = self.env["website"]

        if self._name == "b2b.contact.request":
            customer = self.partner_id
            staff = self.assigned_user_id.partner_id
            website = self.website_id
        elif self._name == "sale.order":
            customer = self.partner_id
            staff = self.user_id.partner_id
            website = self.website_id
        elif self._name == "b2b.sample.request":
            customer = self.contact_id
            staff = self.reviewer_id.partner_id
            website = self.website_id
        elif self._name == "helpdesk.ticket":
            customer = self.partner_id
            staff = self.user_id.partner_id
            website = getattr(self, "website_id", website)
        elif self._name == "b2b.order.change.request":
            customer = self.partner_id
            staff = self.assigned_user_id.partner_id
            website = self.website_id

        if not staff:
            salesperson = website.salesperson_id.filtered(
                lambda user: user.active and not user.share
            ) if website and "salesperson_id" in website._fields else self.env["res.users"]
            if salesperson:
                staff = salesperson[:1].partner_id
            else:
                operator_group = self.env.ref("b2b_core.group_b2b_operator")
                operator = self.env["res.users"].sudo().search([
                    ("active", "=", True),
                    ("share", "=", False),
                    ("all_group_ids", "in", operator_group.ids),
                ], order="id", limit=1)
                staff = operator.partner_id
        return customer | staff

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        if self and self._b2b_message_center_is_public_comment(message, msg_vals):
            for record in self:
                partners = record.sudo()._b2b_message_center_partners()
                if partners:
                    record.sudo().message_subscribe(partner_ids=partners.ids)
        recipients = super()._notify_get_recipients(
            message, msg_vals=msg_vals, **kwargs
        )
        if self and self._b2b_message_center_is_public_comment(message, msg_vals):
            # A public human reply is a business conversation. Email it even
            # when an internal user's Discuss preference is "Inbox". The same
            # native notification is kept unread for Message Center below.
            for recipient in recipients:
                if recipient.get("email_normalized"):
                    recipient["notif"] = "email"
        return recipients

    def _notify_thread(self, message, msg_vals=False, **kwargs):
        recipients = super()._notify_thread(
            message, msg_vals=msg_vals, **kwargs
        )
        if self and self._b2b_message_center_is_public_comment(message, msg_vals):
            self.env["b2b.message.thread"].sudo()._sync_from_message(message)
            if not self.env.context.get("b2b_skip_portal_unread"):
                recipient_ids = [
                    recipient["id"]
                    for recipient in recipients
                    if recipient.get("id")
                ]
                if recipient_ids:
                    self.env["mail.notification"].sudo().search([
                        ("mail_message_id", "=", message.id),
                        ("res_partner_id", "in", recipient_ids),
                    ]).write({"is_read": False, "read_date": False})
        return recipients


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
            thread.last_author_name = thread.last_author_id.sudo().name or _("System")

    @api.model
    def _source_values(self, source):
        partner = self.env["res.partner"]
        website = self.env["website"]
        assigned_user = self.env["res.users"]
        company = self.env["res.company"]
        subject = source.display_name

        if source._name == "b2b.contact.request":
            partner = source.partner_id
            website = source.website_id
            assigned_user = source.assigned_user_id
            subject = source.subject or source.display_name
            # Company-profile reviews are a shared operations queue, not a
            # sale by the website's legal entity. Portal ownership is unchanged.
            company = (self.env["res.company"] if source.request_type == "company_change"
                       else source.website_id.company_id)
        elif source._name == "sale.order":
            partner = source.partner_id
            website = source.website_id
            assigned_user = source.user_id
            subject = source.name
            company = source.company_id
        elif source._name == "b2b.sample.request":
            partner = source.contact_id
            website = source.website_id
            assigned_user = source.reviewer_id
            subject = source.name
            company = source.website_id.company_id
        elif source._name == "helpdesk.ticket":
            partner = source.partner_id
            website = getattr(source, "website_id", website)
            assigned_user = source.user_id
            subject = source.name
            company = source.company_id
        elif source._name == "b2b.order.change.request":
            partner = source.partner_id
            website = source.website_id
            assigned_user = source.assigned_user_id
            subject = source.name
            company = source.order_id.company_id

        return {
            "source_model": source._name,
            "res_id": source.id,
            "name": source.display_name,
            "subject": subject,
            "source_type": MESSAGE_CENTER_MODEL_LABELS[source._name],
            "partner_id": partner.id,
            "commercial_partner_id": partner.commercial_partner_id.id,
            "website_id": website.id,
            "company_id": company.id,
            "assigned_user_id": assigned_user.id,
        }

    @api.model
    def _sync_from_message(self, message):
        if (
            message.model not in MESSAGE_CENTER_MODELS
            or not message.res_id
            or message.message_type not in ("comment", "email")
            or message.is_internal
            or message.subtype_id.internal
        ):
            return self.browse()
        source = self.env[message.model].sudo().browse(message.res_id).exists()
        if not source:
            return self.browse()
        values = self._source_values(source)
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
            thread.write(values)
            return thread
        return self.sudo().create(values)

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
        partner = partner or self.env.user.partner_id
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
