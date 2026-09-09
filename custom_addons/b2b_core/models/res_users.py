from odoo import api, fields, models, tools
from odoo.fields import Domain


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _b2b_normalize_email_login(self, login):
        """Return Odoo's canonical form for email logins only."""
        if not isinstance(login, str):
            return login
        stripped = login.strip()
        return tools.email_normalize(stripped) or login

    @api.model_create_multi
    def create(self, vals_list):
        normalized_vals_list = []
        for vals in vals_list:
            vals = dict(vals)
            if "login" in vals:
                vals["login"] = self._b2b_normalize_email_login(vals["login"])
            normalized_vals_list.append(vals)
        return super().create(normalized_vals_list)

    def write(self, vals):
        if "login" in vals:
            vals = dict(vals)
            vals["login"] = self._b2b_normalize_email_login(vals["login"])
        return super().write(vals)

    @api.model
    def _get_login_domain(self, login):
        normalized = (
            tools.email_normalize(login.strip())
            if isinstance(login, str)
            else False
        )
        if normalized:
            return Domain(
                "login",
                "=ilike",
                tools.escape_psql(normalized),
            )
        return super()._get_login_domain(login)

    b2b_partner_approved = fields.Boolean(
        related="partner_id.commercial_partner_id.b2b_approved",
        string="Partner Hub Company Approved",
        readonly=True,
    )
    b2b_partner_segment_ids = fields.Many2many(
        related="partner_id.commercial_partner_id.b2b_segment_ids",
        string="Partner Hub Company Segments",
        readonly=True,
    )
