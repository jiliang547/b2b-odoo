import uuid

from psycopg2 import IntegrityError

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class B2BWebSubmission(models.Model):
    """Server-side idempotency ledger for Partner Hub mutation forms."""

    _name = "b2b.web.submission"
    _description = "B2B Website Submission"
    _order = "create_date desc, id desc"

    token = fields.Char(required=True, readonly=True, copy=False, index=True)
    operation = fields.Char(required=True, readonly=True, copy=False, index=True)
    user_id = fields.Many2one(
        "res.users", required=True, readonly=True, copy=False, ondelete="cascade"
    )
    website_id = fields.Many2one(
        "website", required=True, readonly=True, copy=False, ondelete="cascade"
    )
    state = fields.Selection(
        [("processing", "Processing"), ("completed", "Completed")],
        required=True,
        default="processing",
        readonly=True,
        copy=False,
        index=True,
    )
    response_url = fields.Char(readonly=True, copy=False)
    result_model = fields.Char(readonly=True, copy=False)
    result_id = fields.Integer(readonly=True, copy=False)
    completed_at = fields.Datetime(readonly=True, copy=False)

    _token_unique = models.Constraint(
        "UNIQUE (token)", "A website submission token can only be processed once."
    )

    @api.model
    def new_token(self):
        return str(uuid.uuid4())

    @api.model
    def _normalize_token(self, token):
        try:
            normalized = str(uuid.UUID(str(token or "")))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError(_("This form has expired. Please reload it and try again."))
        if normalized != str(token or "").lower():
            raise ValidationError(_("This form has expired. Please reload it and try again."))
        return normalized

    @api.model
    def claim(self, token, operation, user, website):
        """Claim a token atomically, returning ``(submission, is_new)``.

        The database constraint is authoritative. It also protects against two
        requests arriving before either browser response has completed.
        """
        normalized = self._normalize_token(token)
        submission = self.sudo().search([("token", "=", normalized)], limit=1)
        if submission:
            submission._validate_claim(operation, user, website)
            return submission, False
        values = {
            "token": normalized,
            "operation": operation,
            "user_id": user.id,
            "website_id": website.id,
        }
        try:
            with self.env.cr.savepoint():
                submission = self.sudo().create(values)
            return submission, True
        except IntegrityError:
            submission = self.sudo().search([("token", "=", normalized)], limit=1)
        if not submission:
            raise ValidationError(_("The request could not be safely submitted. Please try again."))
        submission._validate_claim(operation, user, website)
        return submission, False

    def _validate_claim(self, operation, user, website):
        self.ensure_one()
        if (
            self.operation != operation
            or self.user_id != user
            or self.website_id != website
        ):
            raise ValidationError(_("This submission token is not valid for this form."))

    def complete(self, response_url, result=None):
        self.ensure_one()
        values = {
            "state": "completed",
            "response_url": response_url,
            "completed_at": fields.Datetime.now(),
        }
        if result:
            result.ensure_one()
            values.update({"result_model": result._name, "result_id": result.id})
        self.sudo().write(values)
        return response_url

    @api.autovacuum
    def _gc_completed_submissions(self):
        cutoff = fields.Datetime.subtract(fields.Datetime.now(), days=90)
        self.sudo().search([
            ("state", "=", "completed"),
            ("completed_at", "<", cutoff),
        ]).unlink()
