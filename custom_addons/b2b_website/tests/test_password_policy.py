import re
from unittest.mock import patch
from uuid import uuid4

from odoo.addons.mail.models.mail_template import MailTemplate
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import UserError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerPasswordPolicy(TransactionCase):
    def setUp(self):
        super().setUp()
        self.users = self.env["res.users"]
        self.params = self.env["ir.config_parameter"].sudo()
        self.params.set_param("auth_password_policy.minlength", 8)
        self.portal = mail_new_test_user(self.env, login="password-policy-customer",
            password="Portal2026!", groups="base.group_portal")

    def test_native_policy_is_installed_and_preserves_stricter_setting(self):
        module = self.env["ir.module.module"].search([("name", "=", "auth_password_policy")])
        self.assertEqual(module.state, "installed")
        self.params.set_param("auth_password_policy.minlength", 12)
        self.users._b2b_initialize_password_policy()
        self.assertEqual(self.users._b2b_password_policy()["minlength"], 12)
        self.assertIn("12 characters", self.users._b2b_password_policy()["message"])

    def test_upgrade_sets_native_minimum_and_is_idempotent(self):
        self.params.set_param("auth_password_policy.minlength", 0)
        self.users._b2b_initialize_password_policy()
        self.users._b2b_initialize_password_policy()
        self.assertEqual(self.users.get_password_policy()["minlength"], 8)

    def test_portal_rejects_short_letters_numbers_and_symbols_only(self):
        for password in ("Abc1234", "abcdefgh", "12345678", "!!!!!!!!", "abc!!!!!", "１２３４５６７８"):
            with self.subTest(password=password), self.assertRaises(UserError), self.cr.savepoint():
                self.portal.write({"password": password})

    def test_portal_accepts_symbols_uppercase_and_long_passwords(self):
        for password in ("abcd1234", "ABCD1234", "Ab12!@#$", " long password 123! ", "a1" + "x" * 100):
            with self.subTest(password=password):
                self.portal.write({"password": password})
                info = self.portal.with_user(self.portal)._check_credentials(
                    {"type": "password", "password": password}, {"interactive": True})
                self.assertEqual(info["uid"], self.portal.id)

    def test_portal_floor_remains_eight_if_native_setting_is_lowered(self):
        self.params.set_param("auth_password_policy.minlength", 0)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.portal.write({"password": "Ab12345"})

    def test_native_higher_minimum_is_enforced(self):
        self.params.set_param("auth_password_policy.minlength", 12)
        with self.assertRaises(UserError), self.cr.savepoint():
            self.portal.write({"password": "abcd1234"})

    def test_internal_user_only_receives_native_minimum(self):
        internal = mail_new_test_user(self.env, login="policy-internal", password="abcdefgh")
        internal.write({"password": "ijklmnop"})
        with self.assertRaises(UserError), self.cr.savepoint():
            internal.write({"password": "abcdefg"})

    def test_mixed_batch_cannot_bypass_portal_policy(self):
        internal = mail_new_test_user(self.env, login="policy-batch-internal", password="abcdefgh")
        with self.assertRaises(UserError), self.cr.savepoint():
            (self.portal | internal).write({"password": "abcdefgh"})

    def test_existing_weak_password_still_authenticates(self):
        # Simulates an existing hash in an isolated test, not a live user reset.
        self.portal._set_encrypted_password(self.portal.id, self.portal._crypt_context().hash("legacy"))
        info = self.portal.with_user(self.portal)._check_credentials(
            {"type": "password", "password": "legacy"}, {"interactive": True})
        self.assertEqual(info["uid"], self.portal.id)
        self.portal.write({"name": "Legacy account remains usable"})


@tagged("post_install", "-at_install")
class TestPartnerPasswordHttp(HttpCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param("auth_password_policy.minlength", 8)
        self.customer_type = self.env["b2b.customer.type"].create({"name": "Password HTTP Test"})
        self.authenticate(None, None)

    def _csrf(self, path):
        page = self.url_open(path)
        self.assertEqual(page.status_code, 200)
        return re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)

    def _submit(self, path, values):
        values["csrf_token"] = self._csrf(path)
        with patch.object(self.env.registry["ir.http"], "_verify_request_recaptcha_token", return_value=None), \
             patch.object(MailTemplate, "send_mail", autospec=True, return_value=1):
            return self.url_open(path, data=values)

    def _payload(self, password):
        return {
            "login": "policy-%s@example.test" % uuid4().hex,
            "name": "Password Test", "job_title": "Buyer", "company_name": "Password Test Company",
            "country_id": str(self.env.ref("base.us").id), "mobile": "+12025550199",
            "company_phone": "", "customer_type_id": str(self.customer_type.id), "terms": "1",
            "password": password, "confirm_password": password,
        }

    def test_signup_server_rejects_weak_password_without_creating_records(self):
        for password in ("Abc1234", "abcdefgh", "12345678", ""):
            with self.subTest(password=password):
                values = self._payload(password)
                response = self._submit("/web/signup", values)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="password_error"', response.text)
                self.assertIn("characters", response.text)
                self.assertNotIn("Oops! Something went wrong", response.text)
                self.assertFalse(self.env["res.users"].with_context(active_test=False).search([("login", "=", values["login"])]))
                self.assertFalse(self.env["b2b.registration.application"].search([("business_email", "=", values["login"])]))

    def test_minimum_eight_signup_creates_pending_email_application(self):
        values = self._payload("abcd1234")
        response = self._submit("/web/signup", values)
        self.assertIn("Check your email to verify your account", response.text)
        application = self.env["b2b.registration.application"].search([("business_email", "=", values["login"])])
        self.assertEqual(application.state, "awaiting_email")
        self.assertFalse(application.user_id.with_context(active_test=False).active)

    def test_password_confirmation_error_is_inline_and_no_password_is_echoed(self):
        values = self._payload("UniqueSecret123!")
        values["confirm_password"] = "Different123!"
        response = self._submit("/web/signup", values)
        self.assertIn("Passwords do not match", response.text)
        self.assertNotIn(values["password"], response.text)
        self.assertNotIn(values["confirm_password"], response.text)

    def _token_user(self, portal=True, signup_type="reset"):
        user = mail_new_test_user(self.env, login="token-%s@example.test" % uuid4().hex,
            password="Original123!", groups="base.group_portal" if portal else "base.group_user")
        user.partner_id.signup_prepare(signup_type=signup_type)
        return user, user.partner_id._generate_signup_token()

    def test_reset_rejection_preserves_token_then_valid_password_succeeds(self):
        user, token = self._token_user()
        path = "/web/reset_password?token=%s" % token
        values = {"token": token, "password": "abcdefgh", "confirm_password": "abcdefgh"}
        rejected = self._submit(path, values)
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("including a letter and a number", rejected.text)
        user.partner_id.invalidate_recordset()
        self.assertEqual(user.partner_id.signup_type, "reset")
        accepted = self._submit(path, {"token": token, "password": "Reset123", "confirm_password": "Reset123"})
        self.assertIn("Your password has been reset successfully", accepted.text)

    def test_invited_portal_account_uses_the_same_rules(self):
        user, token = self._token_user(signup_type="signup")
        path = "/web/signup?token=%s" % token
        page = self.url_open(path)
        self.assertIn('data-lt-letter-number="1"', page.text)
        rejected = self._submit(path, {"token": token, "login": user.login, "name": user.name,
            "password": "12345678", "confirm_password": "12345678"})
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("including a letter and a number", rejected.text)
        user.partner_id.invalidate_recordset()
        self.assertEqual(user.partner_id.signup_type, "signup")
        accepted = self._submit(path, {"token": token, "login": user.login, "name": user.name,
            "password": "Invite123", "confirm_password": "Invite123"})
        self.assertEqual(accepted.status_code, 200)
        self.assertNotIn("Oops! Something went wrong", accepted.text)
        user.partner_id.invalidate_recordset()
        self.assertFalse(user.partner_id.signup_type)

    def test_internal_invitation_does_not_add_composition_requirement(self):
        _user, token = self._token_user(portal=False, signup_type="signup")
        page = self.url_open("/web/signup?token=%s" % token)
        self.assertIn('data-lt-letter-number="0"', page.text)
        self.assertNotIn("including a letter and a number", page.text)

    def test_native_configuration_is_reflected_in_frontend(self):
        self.env["ir.config_parameter"].sudo().set_param("auth_password_policy.minlength", 12)
        page = self.url_open("/web/signup")
        self.assertIn('data-lt-password-policy="12"', page.text)
        self.assertIn("Use at least 12 characters", page.text)

    def test_invalid_reset_token_stays_on_branded_page(self):
        response = self.url_open("/web/reset_password?token=password-test-invalid-token")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Reset your password", response.text)
        self.assertIn("Invalid signup token", response.text)
        self.assertNotIn("Oops! Something went wrong", response.text)
