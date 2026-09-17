import uuid

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class B2BContactRequest(models.Model):
    _name = "b2b.contact.request"
    _description = "B2B Contact Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    # Portal customers can reply through the native portal chatter while the
    # company record rule remains the ownership boundary.
    _mail_post_access = "read"

    name = fields.Char(default=lambda self: _("New"), readonly=True, copy=False, index=True)
    access_token = fields.Char(default=lambda self: str(uuid.uuid4()), readonly=True, copy=False, index=True)
    request_type = fields.Selection(
        [
            ("sales", "Sales Inquiry"),
            ("technical", "Technical Support"),
            ("sample", "Sample Request"),
            ("partnership", "Partnership"),
            ("company_change", "Company Change"),
            ("user_change", "Company User Change"),
            ("other", "Other"),
        ],
        required=True,
        default="sales",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        required=True,
        default="new",
        tracking=True,
    )
    subject = fields.Char(required=True)
    contact_name = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char()
    company_name = fields.Char()
    message = fields.Text(required=True)
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    commercial_partner_id = fields.Many2one(
        "res.partner",
        related="partner_id.commercial_partner_id",
        store=True,
        index=True,
        readonly=True,
    )
    website_id = fields.Many2one("website", required=True, ondelete="restrict")
    source_url = fields.Char()
    assigned_user_id = fields.Many2one("res.users", tracking=True)

    requested_company_name = fields.Char()
    requested_vat = fields.Char(string="Requested Tax ID")
    requested_email = fields.Char()
    requested_phone = fields.Char()
    requested_street = fields.Char()
    requested_street2 = fields.Char()
    requested_city = fields.Char()
    requested_zip = fields.Char()
    requested_country_id = fields.Many2one("res.country")

    _access_token_unique = models.Constraint(
        "UNIQUE (access_token)", "Contact request access tokens must be unique."
    )

    @api.model
    def _default_assigned_user(self, website):
        operator_group = self.env.ref("b2b_core.group_b2b_operator")
        salesperson = website.salesperson_id.filtered(
            lambda user: (
                user.active
                and not user.share
                and operator_group in user.all_group_ids
            )
        )
        if salesperson:
            return salesperson
        return self.env["res.users"].sudo().search(
            [
                ("active", "=", True),
                ("share", "=", False),
                ("all_group_ids", "in", operator_group.ids),
            ],
            order="id",
            limit=1,
        )

    @api.model_create_multi
    def create(self, vals_list):
        pending_partners = set()
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code(
                    "b2b.contact.request"
                ) or _("New")
            partner = self.env["res.partner"].browse(vals.get("partner_id")).exists()
            if (
                partner
                and vals.get("request_type") == "company_change"
                and vals.get("state", "new") in ("new", "in_progress")
            ):
                if partner.id in pending_partners or self.search_count([
                    ("partner_id", "=", partner.id),
                    ("request_type", "=", "company_change"),
                    ("state", "in", ("new", "in_progress")),
                ], limit=1):
                    raise ValidationError(_(
                        "A company setup or change request is already under review."
                    ))
                pending_partners.add(partner.id)
            if not vals.get("assigned_user_id"):
                website = self.env["website"].browse(vals.get("website_id")).exists()
                assigned_user = self._default_assigned_user(website)
                if assigned_user:
                    vals["assigned_user_id"] = assigned_user.id
        records = super().create(vals_list)
        for record in records:
            followers = record.partner_id | record.assigned_user_id.partner_id
            if followers:
                record.message_subscribe(partner_ids=followers.ids)
            # The acknowledgement is part of the submission response, not a
            # new staff reply that should light up the portal notification.
            record.with_context(b2b_skip_portal_unread=True)._post_customer_message(
                _(
                    "Your inquiry %(request)s has been received. Our team will "
                    "reply in this conversation.",
                    request=record.name,
                )
            )
            if record.assigned_user_id:
                record.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=record.assigned_user_id.id,
                    summary=_("Respond to %(request)s", request=record.name),
                    note=_(
                        "New %(request_type)s from %(contact)s: %(subject)s",
                        request_type=dict(record._fields["request_type"].selection).get(
                            record.request_type
                        ),
                        contact=record.contact_name,
                        subject=record.subject,
                    ),
                )
        return records

    def message_post(self, **kwargs):
        message = super().message_post(**kwargs)
        if self.env.context.get("b2b_skip_portal_unread"):
            return message

        # Odoo forces portal users to receive chatter notifications by email.
        # Email notifications are normally created as already read because the
        # backend has no portal reading surface. Partner Hub does have one, so
        # keep the native mail.notification record unread until that customer
        # opens the inquiry. Email delivery itself remains unchanged.
        for record in self:
            customer = record.partner_id
            if (
                customer
                and not message.is_internal
                and message.message_type != "user_notification"
                and message.author_id != customer
            ):
                notification = self.env["mail.notification"].sudo().search([
                    ("mail_message_id", "=", message.id),
                    ("res_partner_id", "=", customer.id),
                ])
                notification.write({"is_read": False, "read_date": False})
        return message

    @api.model
    def get_portal_unread_message_count(self):
        """Count native unread notifications on inquiries visible to the user."""
        if self.env.user._is_public():
            return 0
        notifications = self.env["mail.notification"].sudo().search([
            ("res_partner_id", "=", self.env.user.partner_id.id),
            ("is_read", "=", False),
            ("mail_message_id.model", "=", self._name),
            ("mail_message_id.message_type", "!=", "user_notification"),
        ])
        if not notifications:
            return 0
        candidate_ids = notifications.mail_message_id.mapped("res_id")
        visible_request_ids = set(self.search([("id", "in", candidate_ids)]).ids)
        return sum(
            notification.mail_message_id.res_id in visible_request_ids
            for notification in notifications
        )

    def write(self, vals):
        if any(
            field_name in vals
            for field_name in ("partner_id", "request_type", "state")
        ):
            for record in self:
                partner_id = vals.get("partner_id", record.partner_id.id)
                request_type = vals.get("request_type", record.request_type)
                state = vals.get("state", record.state)
                was_same_open_request = (
                    record.partner_id.id == partner_id
                    and record.request_type == "company_change"
                    and record.state in ("new", "in_progress")
                )
                if (
                    partner_id
                    and request_type == "company_change"
                    and state in ("new", "in_progress")
                    and not was_same_open_request
                    and self.search_count([
                        ("id", "!=", record.id),
                        ("partner_id", "=", partner_id),
                        ("request_type", "=", "company_change"),
                        ("state", "in", ("new", "in_progress")),
                    ], limit=1)
                ):
                    raise ValidationError(_(
                        "A company setup or change request is already under review."
                    ))
        result = super().write(vals)
        if "assigned_user_id" in vals:
            for record in self.filtered("assigned_user_id"):
                record.message_subscribe(
                    partner_ids=record.assigned_user_id.partner_id.ids
                )
        return result

    def _post_customer_message(self, body):
        """Post a public reply and deliver it to portal users or guest email.

        Registered contacts receive follower notifications. Public inquiries
        deliberately stay partner-less, so Odoo 19's native outgoing-email
        recipient is used without creating spam contacts in master data.
        """
        for record in self:
            record.message_post(
                body=body,
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
                outgoing_email_to=record.email if not record.partner_id else False,
            )

    def _complete_assignment_activities(self, feedback):
        todo_type = self.env.ref("mail.mail_activity_data_todo")
        for record in self:
            activities = record.activity_ids.filtered(
                lambda activity: activity.activity_type_id == todo_type
            )
            if activities:
                activities.action_feedback(feedback=feedback)

    def action_start(self):
        self._complete_assignment_activities(
            _("Contact request processing started.")
        )
        self.write({"state": "in_progress", "assigned_user_id": self.env.user.id})
        self._post_customer_message(
            _("Your inquiry is now being reviewed by our team.")
        )

    def action_resolve(self):
        self.write({"state": "resolved"})
        self._complete_assignment_activities(_("Contact request resolved."))
        self._post_customer_message(
            _("Your inquiry has been marked as resolved. Reply here if you need more help.")
        )

    def action_close(self):
        self.write({"state": "closed"})
        self._complete_assignment_activities(_("Contact request closed."))
        self._post_customer_message(_("Your inquiry has been closed."))
