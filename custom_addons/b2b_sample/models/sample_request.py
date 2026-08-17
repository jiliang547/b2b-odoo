import math
import uuid

from odoo import _, api, fields, models, tools
from odoo.exceptions import AccessError, UserError, ValidationError


_STATE_TRANSITION_TOKEN = object()


class B2BSampleRequest(models.Model):
    _name = "b2b.sample.request"
    _description = "B2B Sample Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: _("New"), readonly=True, copy=False, index=True)
    request_uuid = fields.Char(default=lambda self: str(uuid.uuid4()), readonly=True, copy=False, index=True)
    partner_id = fields.Many2one("res.partner", required=True, index=True, tracking=True)
    commercial_partner_id = fields.Many2one(
        "res.partner", required=True, index=True, readonly=True
    )
    contact_id = fields.Many2one("res.partner", required=True, index=True)
    contact_name = fields.Char(required=True)
    company_name = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char(required=True)
    shipping_partner_id = fields.Many2one("res.partner")
    shipping_address = fields.Text(required=True)
    reason = fields.Text(required=True)
    notes = fields.Text()
    line_ids = fields.One2many(
        "b2b.sample.request.line", "request_id", string="Sample Products", copy=True
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("erp_pending", "ERP Pending"),
            ("erp_synced", "ERP Synced"),
            ("erp_failed", "ERP Failed"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        index=True,
        tracking=True,
        copy=False,
    )
    reviewer_id = fields.Many2one(
        "res.users", readonly=True, tracking=True, copy=False,
        groups="b2b_core.group_b2b_operator",
    )
    review_date = fields.Datetime(
        readonly=True, copy=False, groups="b2b_core.group_b2b_operator"
    )
    rejection_reason = fields.Text(copy=False)
    erp_reference = fields.Char(readonly=True, copy=False, index=True)
    erp_last_error = fields.Text(
        readonly=True, copy=False, groups="b2b_core.group_b2b_operator"
    )
    erp_job_ids = fields.One2many(
        "b2b.integration.job", compute="_compute_erp_jobs", string="ERP Jobs",
        groups="b2b_core.group_b2b_operator",
    )
    erp_job_count = fields.Integer(
        compute="_compute_erp_jobs", groups="b2b_core.group_b2b_operator"
    )

    _request_uuid_unique = models.Constraint(
        "UNIQUE (request_uuid)", "Sample request UUIDs must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        portal_request = not self.env.user._is_internal()
        if self.env.user._is_public():
            raise AccessError(_("Please sign in before requesting a sample."))
        current_contact = self.env.user.partner_id
        current_company = current_contact.commercial_partner_id
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                # Portal users are intentionally not granted generic sequence
                # access. Elevate only this fixed server-owned sequence lookup.
                vals["name"] = (
                    self.env["ir.sequence"].sudo().next_by_code("b2b.sample.request")
                    or _("New")
                )
            if portal_request:
                vals.update({
                    "partner_id": current_company.id,
                    "commercial_partner_id": current_company.id,
                    "contact_id": current_contact.id,
                    "state": "submitted",
                })
                self._validate_portal_values(vals, current_company)
            else:
                if (
                    vals.get("state", "draft") != "draft"
                    and self.env.context.get("b2b_state_transition") is not _STATE_TRANSITION_TOKEN
                    and not self.env.su
                ):
                    raise AccessError(_("New internal sample requests must start in Draft."))
                partner = self.env["res.partner"].browse(vals.get("partner_id")).exists()
                vals["commercial_partner_id"] = partner.commercial_partner_id.id
                vals.setdefault("contact_id", partner.id)
        # The request payload and ownership have been fully validated above.
        # Elevation is limited to creation so nested sample lines do not need a
        # generic portal create ACL that could be abused through direct RPC.
        create_self = self.sudo() if portal_request else self
        records = super(B2BSampleRequest, create_self).create(vals_list)
        if any(not record.line_ids for record in records):
            raise ValidationError(_("A sample request requires at least one product."))
        return records.with_user(self.env.user) if portal_request else records

    @api.model
    def _validate_portal_values(self, vals, company):
        website = self.env["website"].get_current_website()
        if website.b2b_require_approved_sample and not company.b2b_approved:
            raise AccessError(_("Your Partner Hub account is not approved for sample requests."))
        for field_name, maximum in {
            "contact_name": 160,
            "company_name": 200,
            "email": 254,
            "phone": 64,
            "shipping_address": 2000,
            "reason": 4000,
            "notes": 4000,
        }.items():
            value = vals.get(field_name)
            if field_name not in ("notes",) and not value:
                raise ValidationError(_("Please complete all required sample request fields."))
            if value and len(value) > maximum:
                raise ValidationError(_("A sample request field exceeds the allowed length."))
        if vals.get("email") and not tools.single_email_re.match(vals["email"]):
            raise ValidationError(_("Please enter a valid email address."))
        shipping_partner = self.env["res.partner"].browse(vals.get("shipping_partner_id")).exists()
        if shipping_partner and shipping_partner.commercial_partner_id != company:
            raise AccessError(_("The selected shipping address is not available to your company."))
        for command in vals.get("line_ids", []):
            if command[0] != 0:
                raise ValidationError(_("Unsupported sample request line operation."))
            product = self.env["product.product"].browse(command[2].get("product_id")).exists()
            quantity = command[2].get("quantity", 0)
            if not product or not isinstance(quantity, (int, float)) or not math.isfinite(quantity) or not 0 < quantity <= 10000:
                raise ValidationError(_("Each sample line requires a valid product and quantity."))
            if not self.env["b2b.product.service"].is_visible(product.product_tmpl_id):
                raise AccessError(_("A selected product is not available to your account."))

    def write(self, vals):
        if "state" in vals and self.env.context.get("b2b_state_transition") is not _STATE_TRANSITION_TOKEN:
            raise UserError(_("Use the sample workflow actions to change state."))
        if not self.env.user._is_internal() and set(vals) - {"notes"}:
            raise AccessError(_("Portal users cannot modify a submitted sample request."))
        return super().write(vals)

    def _transition(self, allowed_from, target, extra=None):
        invalid = self.filtered(lambda record: record.state not in allowed_from)
        if invalid:
            raise UserError(_("This sample request cannot move to the requested state."))
        values = {"state": target}
        values.update(extra or {})
        return self.with_context(b2b_state_transition=_STATE_TRANSITION_TOKEN).write(values)

    def action_submit(self):
        for request in self:
            if not request.line_ids:
                raise ValidationError(_("A sample request requires at least one product."))
        return self._transition({"draft"}, "submitted")

    def action_start_review(self):
        if not self.env.user.has_group("b2b_core.group_b2b_operator"):
            raise AccessError(_("You are not allowed to review sample requests."))
        return self._transition(
            {"submitted"},
            "under_review",
            {"reviewer_id": self.env.user.id, "review_date": fields.Datetime.now()},
        )

    def action_approve(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can approve sample requests."))
        for request in self:
            request._transition(
                {"submitted", "under_review"},
                "approved",
                {"reviewer_id": self.env.user.id, "review_date": fields.Datetime.now()},
            )
            job = self.env["b2b.integration.job"].enqueue(
                "sample_request",
                request,
                "sample_request:%s" % request.request_uuid,
                request_summary={
                    "request": request.name,
                    "customer": request.commercial_partner_id.display_name,
                    "line_count": len(request.line_ids),
                },
            )
            request._transition({"approved"}, "erp_pending")
            request.message_post(body=_("ERP integration job %s was created.", job.display_name))
        return True

    def action_reject(self):
        if not self.env.user.has_group("b2b_core.group_b2b_manager"):
            raise AccessError(_("Only a B2B Manager can reject sample requests."))
        return self._transition(
            {"submitted", "under_review"},
            "rejected",
            {"reviewer_id": self.env.user.id, "review_date": fields.Datetime.now()},
        )

    def action_cancel(self):
        return self._transition({"draft", "submitted", "under_review"}, "cancelled")

    def action_retry_erp(self):
        if not self.env.user.has_group("b2b_erp_connector.group_b2b_integration_manager"):
            raise AccessError(_("You are not allowed to retry ERP synchronization."))
        for request in self:
            if request.state != "erp_failed":
                raise UserError(_("Only ERP-failed sample requests can be retried."))
            job = request.erp_job_ids.filtered(lambda item: item.state in ("failed", "dead"))[:1]
            if not job:
                raise UserError(_("No failed ERP job is available."))
            job.action_retry()
            request._transition({"erp_failed"}, "erp_pending", {"erp_last_error": False})
        return True

    def _b2b_on_erp_job_success(self, job, result):
        for request in self:
            request._transition(
                {"erp_pending", "erp_failed"},
                "erp_synced",
                {
                    "erp_reference": str(result.get("reference") or "")[:128],
                    "erp_last_error": False,
                },
            )

    def _b2b_on_erp_job_failure(self, job, error):
        for request in self.filtered(lambda record: record.state == "erp_pending"):
            request._transition(
                {"erp_pending"}, "erp_failed", {"erp_last_error": str(error)[:2000]}
            )

    def _compute_erp_jobs(self):
        Job = self.env["b2b.integration.job"]
        jobs = Job.search([
            ("reference_model", "=", self._name),
            ("reference_id", "in", self.ids),
        ])
        jobs_by_request = {}
        for job in jobs:
            jobs_by_request.setdefault(job.reference_id, Job)
            jobs_by_request[job.reference_id] |= job
        for request in self:
            request_jobs = jobs_by_request.get(request.id, Job)
            request.erp_job_ids = request_jobs
            request.erp_job_count = len(request_jobs)

    def action_view_erp_jobs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "b2b_erp_connector.action_b2b_integration_jobs"
        )
        action["domain"] = [
            ("reference_model", "=", self._name),
            ("reference_id", "=", self.id),
        ]
        return action


class B2BSampleRequestLine(models.Model):
    _name = "b2b.sample.request.line"
    _description = "B2B Sample Request Line"
    _order = "id"

    request_id = fields.Many2one(
        "b2b.sample.request", required=True, ondelete="cascade", index=True
    )
    commercial_partner_id = fields.Many2one(
        related="request_id.commercial_partner_id", store=True, index=True
    )
    product_id = fields.Many2one("product.product", required=True, ondelete="restrict")
    quantity = fields.Float(required=True, default=1.0)
    uom_id = fields.Many2one(
        "uom.uom", required=True, default=lambda self: self.env.ref("uom.product_uom_unit")
    )
    notes = fields.Char()

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.uom_id = self.product_id.uom_id

    @api.constrains("quantity")
    def _check_quantity(self):
        if any(
            not math.isfinite(line.quantity) or not 0 < line.quantity <= 10000
            for line in self
        ):
            raise ValidationError(_("Sample quantities must be between 0 and 10,000."))
