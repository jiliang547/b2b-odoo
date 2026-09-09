from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEmailLoginNormalization(TransactionCase):
    def test_email_login_is_normalized_and_found_case_insensitively(self):
        user = mail_new_test_user(
            self.env,
            login="Partner.User@Example.TEST",
            groups="base.group_portal",
        )

        self.assertEqual(user.login, "partner.user@example.test")
        self.assertEqual(
            self.env["res.users"].search(
                self.env["res.users"]._get_login_domain(
                    "PARTNER.USER@EXAMPLE.TEST"
                ),
                limit=1,
            ),
            user,
        )

    def test_email_login_is_normalized_when_changed(self):
        user = mail_new_test_user(
            self.env,
            login="email-login-change",
            groups="base.group_portal",
        )

        user.login = "Changed.User@Example.TEST"

        self.assertEqual(user.login, "changed.user@example.test")

    def test_email_login_case_variant_cannot_be_created_twice(self):
        email = "duplicate-email-login@example.test"
        mail_new_test_user(
            self.env,
            login=email,
            groups="base.group_portal",
        )

        with self.env.cr.savepoint(), self.assertRaises(ValidationError):
            mail_new_test_user(
                self.env,
                login=email.upper(),
                groups="base.group_portal",
            )

    def test_non_email_login_keeps_native_case_sensitive_behavior(self):
        user = mail_new_test_user(
            self.env,
            login="CaseSensitivePortalUser",
            groups="base.group_portal",
        )

        self.assertEqual(user.login, "CaseSensitivePortalUser")
        self.assertFalse(
            self.env["res.users"].search(
                self.env["res.users"]._get_login_domain(
                    "casesensitiveportaluser"
                ),
                limit=1,
            )
        )
