import secrets
from datetime import timedelta
from urllib.parse import quote, urljoin

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class B2BRegistrationApplication(models.Model):
    _name = "b2b.registration.application"
    _description = "Partner Hub Registration Application"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(
        string="Application",
        default=lambda self: _("New"),
        readonly=True,
        copy=False,
        index=True,
    )
    state = fields.Selection(
        [
            ("awaiting_email", "Verify Email"),
            ("pending", "Partner Review"),
            ("approved", "Access Activated"),
            ("rejected", "Rejected"),
            ("expired", "Email Link Expired"),
        ],
        required=True,
        default="awaiting_email",
        tracking=True,
        index=True,
    )
    website_id = fields.Many2one(
        "website", required=True, ondelete="restrict", index=True
    )
    user_id = fields.Many2one(
        "res.users", required=True, ondelete="restrict", index=True
    )
    partner_id = fields.Many2one(
        "res.partner", required=True, ondelete="restrict", index=True
    )

    full_name = fields.Char(tracking=True)
    job_title = fields.Char()
    company_name = fields.Char(tracking=True)
    country_id = fields.Many2one("res.country")
    business_email = fields.Char(tracking=True, index=True)
    company_phone = fields.Char()
    mobile = fields.Char(string="Mobile / WhatsApp")
    customer_type_id = fields.Many2one(
        "b2b.customer.type", string="Business Type", tracking=True
    )
    company_website = fields.Char()
    product_interest_id = fields.Many2one(
        "res.partner.category", string="Products of Interest"
    )

    terms_accepted_at = fields.Datetime(readonly=True)
    terms_version = fields.Char(readonly=True, default="2026-09")
    email_verified_at = fields.Datetime(readonly=True, copy=False)
    verification_sent_at = fields.Datetime(readonly=True, copy=False)
    verification_expires_at = fields.Datetime(readonly=True, copy=False)
    verification_token = fields.Char(
        readonly=True,
        copy=False,
        index=True,
        groups="b2b_core.group_b2b_manager",
    )

    company_resolution = fields.Selection(
        [("existing", "Link Existing Company"), ("create", "Create New Company")],
        string="Company Resolution",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.partner",
        string="Resolved Company",
        domain="[('is_company', '=', True)]",
        tracking=True,
    )
    approved_at = fields.Datetime(readonly=True, copy=False)
    approved_by_id = fields.Many2one("res.users", readonly=True, copy=False)
    rejection_reason = fields.Text(tracking=True)

    _user_unique = models.Constraint(
        "UNIQUE (user_id)", "A portal user can only have one registration application."
    )
    _verification_token_unique = models.Constraint(
        "UNIQUE (verification_token)", "Verification links must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code(
                    "b2b.registration.application"
                ) or _("New")
        return super().create(vals_list)

    @api.constrains("partner_id", "user_id")
    def _check_user_partner(self):
        for application in self:
            if application.user_id.partner_id != application.partner_id:
                raise ValidationError(_("The registration user and contact must match."))

    @api.constrains("company_id")
    def _check_company(self):
        for application in self.filtered("company_id"):
            if not application.company_id.is_company:
                raise ValidationError(_("Select a company record, not an individual contact."))

    def _check_manager(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can decide registration applications."))

    def _new_verification_token(self):
        self.ensure_one()
        token = secrets.token_urlsafe(32)
        now = fields.Datetime.now()
        self.sudo().write({
            "state": "awaiting_email",
            "verification_token": token,
            "verification_sent_at": now,
            "verification_expires_at": now + timedelta(hours=24),
        })
        return token

    def get_verification_url(self):
        self.ensure_one()
        if not self.verification_token:
            return False
        return urljoin(
            self.get_base_url(),
            "/web/signup/verify?token=%s" % quote(self.verification_token),
        )

    def action_send_verification_email(self):
        self.ensure_one()
        if self.state not in ("awaiting_email", "expired"):
            raise UserError(_("This email address has already been verified."))
        if (
            self.verification_sent_at
            and fields.Datetime.now() < self.verification_sent_at + timedelta(seconds=60)
        ):
            raise UserError(_("Please wait one minute before requesting another email."))
        self._new_verification_token()
        if not self.env.context.get("b2b_skip_registration_email"):
            template = self.env.ref(
                "b2b_website.mail_template_registration_verify",
                raise_if_not_found=False,
            )
            if template:
                template.sudo().send_mail(self.id, force_send=True)
        return True

    @api.model
    def verify_email_token(self, token):
        if not token:
            return self.browse(), "invalid"
        application = self.sudo().search(
            [("verification_token", "=", token), ("state", "in", ("awaiting_email", "expired"))],
            limit=1,
        )
        if not application:
            return self.browse(), "invalid"
        if (
            not application.verification_expires_at
            or fields.Datetime.now() > application.verification_expires_at
        ):
            application.write({"state": "expired"})
            return application, "expired"
        application.user_id.with_context(active_test=False).sudo().write({"active": True})
        application.write({
            "state": "pending",
            "email_verified_at": fields.Datetime.now(),
            "verification_token": False,
            "verification_expires_at": False,
        })
        manager_group = self.env.ref("b2b_core.group_b2b_manager")
        manager = self.env["res.users"].sudo().search([
            ("active", "=", True),
            ("share", "=", False),
            ("all_group_ids", "in", manager_group.ids),
        ], order="id", limit=1)
        if manager:
            application.activity_schedule(
                "mail.mail_activity_data_todo",
                user_id=manager.id,
                summary=_("Review new Partner Hub registration"),
            )
        return application, "verified"

    def _write_contact_details(self):
        self.ensure_one()
        values = {
            "name": self.full_name,
            "function": self.job_title,
            "email": self.business_email,
            "b2b_mobile_whatsapp": self.mobile,
            "country_id": self.country_id.id,
        }
        if self.product_interest_id:
            values["b2b_product_interest_id"] = self.product_interest_id.id
        self.partner_id.sudo().write(values)

    def _resolve_company(self):
        self.ensure_one()
        if self.company_resolution == "existing":
            company = self.company_id.exists()
            if not company:
                raise UserError(_("Select the existing company for this applicant."))
            # Registration data may fill blanks but never silently overwrite an
            # existing company's master data or pricing classification.
            missing_values = {}
            if not company.phone and self.company_phone:
                missing_values["phone"] = self.company_phone
            if not company.website and self.company_website:
                missing_values["website"] = self.company_website
            if not company.country_id and self.country_id:
                missing_values["country_id"] = self.country_id.id
            if not company.b2b_customer_type_id and self.customer_type_id:
                missing_values["b2b_customer_type_id"] = self.customer_type_id.id
            if missing_values:
                company.write(missing_values)
            return company
        if self.company_resolution == "create":
            return self.env["res.partner"].create({
                "name": self.company_name,
                "is_company": True,
                "company_type": "company",
                "phone": self.company_phone,
                "website": self.company_website,
                "country_id": self.country_id.id,
                "b2b_customer_type_id": self.customer_type_id.id,
            })
        raise UserError(_("Choose whether to link an existing company or create one."))

    def action_approve(self):
        self.ensure_one()
        self._check_manager()
        if self.state not in ("pending", "rejected"):
            raise UserError(_("Only verified registrations can be approved."))
        if not all((
            self.full_name,
            self.job_title,
            self.company_name,
            self.country_id,
            self.business_email,
            self.mobile,
            self.customer_type_id,
        )):
            raise UserError(_("Complete all required registration fields before approval."))
        self._write_contact_details()
        company = self._resolve_company()
        self.partner_id.write({
            "parent_id": company.id,
            "company_type": "person",
            "type": "contact",
        })
        company.action_b2b_approve()
        self.activity_ids.action_done()
        self.write({
            "state": "approved",
            "company_id": company.id,
            "approved_at": fields.Datetime.now(),
            "approved_by_id": self.env.user.id,
            "rejection_reason": False,
        })
        if not self.env.context.get("b2b_skip_registration_email"):
            template = self.env.ref(
                "b2b_website.mail_template_registration_approved",
                raise_if_not_found=False,
            )
            if template:
                template.sudo().send_mail(self.id, force_send=True)
        return True

    def action_reject(self):
        self.ensure_one()
        self._check_manager()
        if self.state != "pending":
            raise UserError(_("Only registrations under review can be rejected."))
        if not (self.rejection_reason or "").strip():
            raise UserError(_("Enter a rejection reason before rejecting the application."))
        self.activity_ids.action_done()
        self.write({"state": "rejected"})
        if not self.env.context.get("b2b_skip_registration_email"):
            template = self.env.ref(
                "b2b_website.mail_template_registration_rejected",
                raise_if_not_found=False,
            )
            if template:
                template.sudo().send_mail(self.id, force_send=True)
        return True

    def action_return_to_review(self):
        self.ensure_one()
        self._check_manager()
        if self.state != "rejected":
            raise UserError(_("Only rejected registrations can return to review."))
        self.write({"state": "pending"})
        return True
