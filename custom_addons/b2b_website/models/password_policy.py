import re

from odoo import _, api, models
from odoo.exceptions import UserError


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _b2b_initialize_password_policy(self):
        """Install/upgrade a native minimum without lowering a stricter setting."""
        params = self.env["ir.config_parameter"].sudo()
        if self.get_password_policy()["minlength"] < 8:
            params.set_param("auth_password_policy.minlength", 8)

    @api.model
    def _b2b_password_policy(self, portal=True):
        policy = self.get_password_policy()
        minimum = max(8, policy["minlength"]) if portal else policy["minlength"]
        return {
            "minlength": minimum,
            "letter_number": portal,
            "message": (
                _("Use at least %(minimum)d characters, including a letter and a number.", minimum=minimum)
                if portal else _("Use at least %(minimum)d characters.", minimum=minimum)
            ),
        }

    @api.model
    def _b2b_check_portal_password(self, password):
        # Keep native length validation and native hashing. The only additional
        # customer rule is an ASCII letter + digit (symbols remain allowed).
        self._check_password_policy([password])
        if (
            not password or len(password) < 8
            or not re.search(r"[A-Za-z]", password)
            or not re.search(r"[0-9]", password)
        ):
            raise UserError(self._b2b_password_policy()["message"])

    def _set_password(self):
        for user in self:
            # Clearing a password retains native semantics (no password login).
            # Internal users only receive the native minimum-length rule.
            if user.password and user._is_portal():
                self._b2b_check_portal_password(user.password)
        return super()._set_password()
