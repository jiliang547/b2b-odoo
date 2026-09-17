import logging
import re
from datetime import timedelta

from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.addons.b2b_erp_connector.services.erp_service import B2BERPError

_logger = logging.getLogger(__name__)

REFERENCE_MODELS = {
    "sales_order": "sale.order",
    "sample_request": "b2b.sample.request",
}
_JOB_WRITE_TOKEN = object()
_PROTECTED_JOB_FIELDS = {
    "job_type", "reference_model", "reference_id", "reference_name",
    "idempotency_key", "state", "attempt_count", "next_retry_at", "started_at",
    "completed_at", "safe_request_summary", "safe_response_summary", "last_error",
}


class B2BIntegrationJob(models.Model):
    _name = "b2b.integration.job"
    _description = "B2B ERP Integration Job"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "next_retry_at, id"

    name = fields.Char(compute="_compute_name", store=True)
    job_type = fields.Selection(
        [("sales_order", "Sales Order"), ("sample_request", "Sample Request")],
        required=True,
        index=True,
        tracking=True,
    )
    reference_model = fields.Char(required=True, index=True, readonly=True)
    reference_id = fields.Integer(required=True, index=True, readonly=True)
    reference_name = fields.Char(readonly=True)
    idempotency_key = fields.Char(required=True, index=True, readonly=True, copy=False)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("processing", "Processing"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("dead", "Dead Letter"),
        ],
        required=True,
        default="pending",
        index=True,
        tracking=True,
        copy=False,
    )
    attempt_count = fields.Integer(default=0, readonly=True, copy=False)
    next_retry_at = fields.Datetime(default=fields.Datetime.now, index=True, copy=False)
    started_at = fields.Datetime(readonly=True, copy=False)
    completed_at = fields.Datetime(readonly=True, copy=False)
    safe_request_summary = fields.Json(readonly=True, copy=False)
    safe_response_summary = fields.Json(readonly=True, copy=False)
    last_error = fields.Text(readonly=True, copy=False)

    _idempotency_unique = models.Constraint(
        "UNIQUE (idempotency_key)", "An ERP idempotency key must be unique."
    )

    @api.depends("job_type", "reference_name", "idempotency_key")
    def _compute_name(self):
        labels = dict(self._fields["job_type"].selection)
        for job in self:
            job.name = "%s: %s" % (
                labels.get(job.job_type, job.job_type or _("Job")),
                job.reference_name or job.idempotency_key or _("New"),
            )

    @api.constrains("job_type", "reference_model")
    def _check_reference_model(self):
        for job in self:
            expected = REFERENCE_MODELS.get(job.job_type)
            if expected and job.reference_model != expected:
                raise ValidationError(_("The reference model does not match the ERP job type."))

    @api.model
    def enqueue(self, job_type, reference, idempotency_key, request_summary=None):
        if not self.env.user._is_internal():
            raise AccessError(_("Only internal business workflows can create ERP jobs."))
        Job = self.sudo()
        expected_model = REFERENCE_MODELS.get(job_type)
        if (
            not expected_model
            or reference._name != expected_model
            or len(reference) != 1
            or not reference.exists()
        ):
            raise ValidationError(_("Unsupported ERP job reference."))
        if not idempotency_key or len(idempotency_key) > 255:
            raise ValidationError(_("The ERP idempotency key is invalid."))
        existing = Job.search([("idempotency_key", "=", idempotency_key)], limit=1)
        if existing:
            return existing
        values = {
            "job_type": job_type,
            "reference_model": reference._name,
            "reference_id": reference.id,
            "reference_name": reference.display_name,
            "idempotency_key": idempotency_key,
            "safe_request_summary": request_summary or {},
        }
        try:
            with self.env.cr.savepoint():
                return Job.create(values)
        except IntegrityError:
            # A concurrent request inserted the same idempotency key.
            return Job.search([("idempotency_key", "=", idempotency_key)], limit=1)

    def write(self, vals):
        if (
            _PROTECTED_JOB_FIELDS.intersection(vals)
            and self.env.context.get("b2b_job_write") is not _JOB_WRITE_TOKEN
            and not self.env.su
        ):
            raise AccessError(_("ERP job state and payload fields are system-managed."))
        return super().write(vals)

    def _system_write(self, vals):
        return self.with_context(b2b_job_write=_JOB_WRITE_TOKEN).write(vals)

    def _reference(self):
        self.ensure_one()
        expected_model = REFERENCE_MODELS.get(self.job_type)
        if not expected_model or expected_model != self.reference_model or expected_model not in self.env:
            return self.env["ir.model"]
        return self.env[expected_model].sudo().browse(self.reference_id).exists()

    @api.model
    def _sanitize_error(self, error):
        message = str(error or _("Unknown ERP error"))[:2000]
        message = re.sub(r"(?i)(authorization|api[-_ ]?key|token|password)\s*[:=]\s*\S+", r"\1=[REDACTED]", message)
        message = re.sub(r"https?://[^\s]+", "[REMOTE_ENDPOINT]", message)
        return message

    def _max_attempts(self):
        value = self.env["ir.config_parameter"].sudo().get_param("b2b_erp.retry_count", "5")
        try:
            return max(1, min(int(value), 20))
        except (TypeError, ValueError):
            return 5

    def _retry_delay(self):
        self.ensure_one()
        return timedelta(minutes=min(5 * (2 ** max(self.attempt_count - 1, 0)), 24 * 60))

    def _mark_failure(self, error, retryable=True):
        self.ensure_one()
        dead = not retryable or self.attempt_count >= self._max_attempts()
        self._system_write({
            "state": "dead" if dead else "failed",
            "last_error": self._sanitize_error(error),
            "next_retry_at": False if dead else fields.Datetime.now() + self._retry_delay(),
        })
        reference = self._reference()
        callback = reference and getattr(reference, "_b2b_on_erp_job_failure", None)
        if callback:
            try:
                callback(self, self.last_error)
            except Exception:
                _logger.exception("Failure callback for B2B ERP job %s failed", self.id)

    def _process_locked(self):
        self.ensure_one()
        if self.state not in ("pending", "failed"):
            return False
        reference = self._reference()
        if not reference:
            self._system_write({"attempt_count": self.attempt_count + 1})
            self._mark_failure(_("The referenced business record no longer exists."))
            return False

        self._system_write({
            "state": "processing",
            "attempt_count": self.attempt_count + 1,
            "started_at": fields.Datetime.now(),
            "last_error": False,
        })
        try:
            result = self.env["b2b.erp.service"].dispatch_job(self, reference)
            # Defence in depth: custom adapters and test doubles cannot bypass
            # the common contract by overriding dispatch_job.
            result = self.env["b2b.erp.service"].validate_push_response(result)
            safe_result = self.env["b2b.erp.service"].safe_response_summary(result)
            self._system_write({
                "state": "success",
                "safe_response_summary": safe_result,
                "completed_at": fields.Datetime.now(),
                "next_retry_at": False,
            })
            callback = getattr(reference, "_b2b_on_erp_job_success", None)
            if callback:
                callback(self, result)
            return True
        except Exception as error:  # worker boundary: persist a safe retry state
            _logger.warning("B2B ERP job %s failed: %s", self.id, self._sanitize_error(error))
            self._mark_failure(
                error,
                retryable=not isinstance(error, B2BERPError) or error.retryable,
            )
            return False

    @api.model
    def _cron_process_pending_jobs(self, limit=50):
        if not self.env["b2b.erp.service"].is_enabled():
            return 0
        candidates = self.search([
            ("state", "in", ["pending", "failed"]),
            "|",
            ("next_retry_at", "=", False),
            ("next_retry_at", "<=", fields.Datetime.now()),
        ], limit=limit, order="next_retry_at, id")
        processed = 0
        for candidate in candidates:
            with self.env.cr.savepoint():
                locked = candidate.try_lock_for_update().filtered_domain([
                    ("state", "in", ["pending", "failed"])
                ])
                if locked and locked._process_locked():
                    processed += 1
        return processed

    def action_retry(self):
        if not self.env.user.has_group("b2b_erp_connector.group_b2b_integration_manager"):
            raise AccessError(_("You are not allowed to retry ERP jobs."))
        invalid = self.filtered(lambda job: job.state not in ("failed", "dead"))
        if invalid:
            raise UserError(_("Only failed or dead-letter jobs can be retried."))
        self._system_write({"state": "pending", "next_retry_at": fields.Datetime.now(), "last_error": False})
        return True

    def action_process_now(self):
        if not self.env.user.has_group("b2b_erp_connector.group_b2b_integration_manager"):
            raise AccessError(_("You are not allowed to process ERP jobs."))
        for job in self:
            with self.env.cr.savepoint():
                locked = job.try_lock_for_update()
                if locked:
                    locked._process_locked()
        return True
