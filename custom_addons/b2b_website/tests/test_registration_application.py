from datetime import timedelta
from unittest.mock import patch

from odoo import http
from odoo.addons.mail.models.mail_template import MailTemplate
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError
from odoo.fields import Datetime
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestB2BRegistrationApplication(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.country = cls.env.ref("base.us")
        cls.customer_type = cls.env["b2b.customer.type"].create({
            "name": "Registration Distributor Test",
        })
        cls.other_customer_type = cls.env["b2b.customer.type"].create({
            "name": "Registration Integrator Test",
        })
        cls.interest = cls.env.ref("b2b_website.partner_interest_commercial_audio")
        cls.manager = mail_new_test_user(
            cls.env,
            login="registration-manager",
            groups="b2b_core.group_b2b_manager",
        )
        cls.operator = mail_new_test_user(
            cls.env,
            login="registration-operator",
            groups="b2b_core.group_b2b_operator",
        )

    def _application(self, suffix="one", **overrides):
        partner = self.env["res.partner"].create({
            "name": "Pending Applicant %s" % suffix,
            "email": "registration-%s@example.test" % suffix,
        })
        user = mail_new_test_user(
            self.env,
            login="registration-%s@example.test" % suffix,
            groups="base.group_portal",
            partner_id=partner.id,
        )
        user.active = False
        values = {
            "website_id": self.website.id,
            "user_id": user.id,
            "partner_id": partner.id,
            "full_name": "Applicant %s" % suffix,
            "job_title": "Sales Manager",
            "company_name": "Applicant Company %s" % suffix,
            "country_id": self.country.id,
            "business_email": "registration-%s@example.test" % suffix,
            "company_phone": "+1 555 0100",
            "mobile": "+1 555 0199",
            "customer_type_id": self.customer_type.id,
            "company_website": "https://example.test",
            "product_interest_id": self.interest.id,
            "terms_accepted_at": Datetime.now(),
            "terms_version": "2026-09",
        }
        values.update(overrides)
        return self.env["b2b.registration.application"].create(values)

    def test_email_verification_activates_portal_user_and_queues_review(self):
        application = self._application("verify")
        token = application._new_verification_token()

        verified, status = self.env["b2b.registration.application"].verify_email_token(token)

        self.assertEqual(status, "verified")
        self.assertEqual(verified.state, "pending")
        self.assertTrue(verified.user_id.with_context(active_test=False).active)
        self.assertTrue(verified.email_verified_at)
        self.assertFalse(verified.verification_token)
        self.assertTrue(verified.activity_ids)

    def test_expired_email_link_does_not_activate_user(self):
        application = self._application("expired")
        token = application._new_verification_token()
        application.verification_expires_at = Datetime.now() - timedelta(minutes=1)

        verified, status = self.env["b2b.registration.application"].verify_email_token(token)

        self.assertEqual(verified, application)
        self.assertEqual(status, "expired")
        self.assertEqual(application.state, "expired")
        self.assertFalse(application.user_id.with_context(active_test=False).active)

    def test_empty_email_token_never_matches_an_application(self):
        application = self._application("empty-token")

        verified, status = self.env["b2b.registration.application"].verify_email_token("")

        self.assertFalse(verified)
        self.assertEqual(status, "invalid")
        self.assertFalse(application.user_id.with_context(active_test=False).active)

    def test_manager_approval_creates_company_and_writes_reviewed_data(self):
        application = self._application(
            "create", state="pending", company_resolution="create"
        )
        application.user_id.active = True

        application.with_user(self.manager).with_context(
            b2b_skip_registration_email=True
        ).action_approve()

        application.invalidate_recordset()
        company = application.company_id
        self.assertEqual(application.state, "approved")
        self.assertTrue(company.is_company)
        self.assertTrue(company.b2b_approved)
        self.assertEqual(company.b2b_customer_type_id, self.customer_type)
        self.assertEqual(application.partner_id.parent_id, company)
        self.assertEqual(application.partner_id.function, "Sales Manager")
        self.assertEqual(application.partner_id.b2b_mobile_whatsapp, "+1 555 0199")
        self.assertEqual(application.partner_id.b2b_product_interest_id, self.interest)

    def test_existing_company_values_are_not_overwritten(self):
        existing = self.env["res.partner"].create({
            "name": "Existing Registration Company",
            "is_company": True,
            "phone": "+44 existing",
            "website": "https://existing.example.test",
            "country_id": self.env.ref("base.uk").id,
            "b2b_customer_type_id": self.other_customer_type.id,
        })
        application = self._application(
            "existing",
            state="pending",
            company_resolution="existing",
            company_id=existing.id,
        )
        application.user_id.active = True

        application.with_user(self.manager).with_context(
            b2b_skip_registration_email=True
        ).action_approve()

        self.assertEqual(existing.phone, "+44 existing")
        self.assertEqual(existing.website, "https://existing.example.test")
        self.assertEqual(existing.country_id, self.env.ref("base.uk"))
        self.assertEqual(existing.b2b_customer_type_id, self.other_customer_type)
        self.assertEqual(application.partner_id.parent_id, existing)
        self.assertTrue(existing.b2b_approved)

    def test_operator_cannot_approve_registration(self):
        application = self._application(
            "permission", state="pending", company_resolution="create"
        )
        with self.assertRaises(AccessError):
            application.with_user(self.operator).action_approve()

    def test_portal_user_reads_only_own_registration(self):
        own = self._application("portal-own", state="pending")
        other = self._application("portal-other", state="pending")
        own.user_id.active = True
        other.user_id.active = True

        visible = self.env["b2b.registration.application"].with_user(own.user_id).search([])

        self.assertIn(own, visible)
        self.assertNotIn(other, visible)

    def test_unverified_registration_cannot_be_approved(self):
        application = self._application("unverified", company_resolution="create")

        with self.assertRaises(UserError):
            application.with_user(self.manager).action_approve()

        self.assertEqual(application.state, "awaiting_email")
        self.assertFalse(application.user_id.with_context(active_test=False).active)

    def test_verification_resend_is_rate_limited_and_rotates_token(self):
        application = self._application("resend")
        first_token = application.with_context(
            b2b_skip_registration_email=True
        )._new_verification_token()

        with self.assertRaises(UserError):
            application.with_context(
                b2b_skip_registration_email=True
            ).action_send_verification_email()

        application.verification_sent_at = Datetime.now() - timedelta(seconds=61)
        application.with_context(
            b2b_skip_registration_email=True
        ).action_send_verification_email()
        self.assertNotEqual(application.verification_token, first_token)

    def test_rejection_requires_reason_and_can_return_to_review(self):
        application = self._application("reject", state="pending")
        application.user_id.active = True

        with self.assertRaises(UserError):
            application.with_user(self.manager).action_reject()

        application.rejection_reason = "Company information could not be confirmed."
        application.with_user(self.manager).with_context(
            b2b_skip_registration_email=True
        ).action_reject()
        self.assertEqual(application.state, "rejected")

        application.with_user(self.manager).action_return_to_review()
        self.assertEqual(application.state, "pending")

    def test_new_company_approval_activates_customer_type_pricing(self):
        currency = self.website.company_id.currency_id
        pricelist = self.env["product.pricelist"].create({
            "name": "Registration Base Pricing Test",
            "currency_id": currency.id,
        })
        self.env["b2b.customer.type.pricelist"].create({
            "customer_type_id": self.customer_type.id,
            "website_id": self.website.id,
            "pricelist_id": pricelist.id,
        })
        application = self._application(
            "pricing", state="pending", company_resolution="create"
        )
        application.user_id.active = True

        application.with_user(self.manager).with_context(
            b2b_skip_registration_email=True
        ).action_approve()

        effective = application.company_id._b2b_get_effective_pricelist(
            self.website, currency
        )
        self.assertTrue(effective)
        self.assertEqual(application.partner_id.property_product_pricelist, effective)


@tagged("post_install", "-at_install")
class TestB2BRegistrationHttpFlow(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.customer_type = cls.env["b2b.customer.type"].create({
            "name": "HTTP Registration Distributor",
        })
        cls.manager = mail_new_test_user(
            cls.env,
            login="registration-http-manager",
            groups="b2b_core.group_b2b_manager",
        )

    def _payload(self, email, **overrides):
        payload = {
            "csrf_token": http.Request.csrf_token(self),
            "name": "HTTP Closure Applicant",
            "job_title": "Purchasing Manager",
            "company_name": "HTTP Closure Company",
            "country_id": str(self.env.ref("base.us").id),
            "login": email,
            "company_phone": "+1 555 0200",
            "mobile": "+1 555 0299",
            "customer_type_id": str(self.customer_type.id),
            "company_website": "closure.example.test",
            "product_interest_id": str(
                self.env.ref("b2b_website.partner_interest_commercial_audio").id
            ),
            "password": "Registration-Test-2026!",
            "confirm_password": "Registration-Test-2026!",
            "terms": "1",
        }
        payload.update(overrides)
        return payload

    def _submit(self, payload):
        def captcha_ok(_record, action):
            self.assertEqual(action, "signup")

        with patch.object(
            self.env.registry["ir.http"],
            "_verify_request_recaptcha_token",
            captcha_ok,
        ), patch.object(MailTemplate, "send_mail", autospec=True, return_value=1):
            return self.url_open("/en/web/signup", data=payload)

    def test_submit_verify_review_and_activate(self):
        self.authenticate(None, None)
        email = "registration-http-closure@example.test"
        response = self._submit(self._payload(email))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Check your email to verify your account", response.text)
        application = self.env["b2b.registration.application"].search([
            ("business_email", "=", email),
        ])
        self.assertTrue(application)
        self.assertEqual(application.state, "awaiting_email")
        self.assertFalse(application.user_id.with_context(active_test=False).active)
        self.assertEqual(application.company_website, "https://closure.example.test")

        verification = self.url_open(
            "/en/web/signup/verify?token=%s" % application.verification_token
        )
        self.assertEqual(verification.status_code, 200)
        self.assertIn("Email verified", verification.text)
        application.invalidate_recordset()
        self.assertEqual(application.state, "pending")
        self.assertTrue(application.user_id.with_context(active_test=False).active)
        self.assertTrue(application.activity_ids)

        application.write({"company_resolution": "create"})
        application.with_user(self.manager).with_context(
            b2b_skip_registration_email=True
        ).action_approve()

        self.assertEqual(application.state, "approved")
        self.assertEqual(application.partner_id.parent_id, application.company_id)
        self.assertTrue(application.company_id.b2b_approved)
        self.assertEqual(application.company_id.b2b_customer_type_id, self.customer_type)

    def test_terms_are_enforced_server_side(self):
        self.authenticate(None, None)
        email = "registration-http-no-terms@example.test"

        response = self._submit(self._payload(email, terms="0"))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please accept the Terms of Use and Privacy Policy", response.text)
        self.assertFalse(self.env["b2b.registration.application"].search([
            ("business_email", "=", email),
        ]))

    def test_product_interest_must_use_the_registration_category(self):
        self.authenticate(None, None)
        email = "registration-http-invalid-interest@example.test"
        unrelated = self.env["res.partner.category"].create({
            "name": "Unrelated Registration Interest",
        })

        response = self._submit(self._payload(
            email, product_interest_id=str(unrelated.id)
        ))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please select a valid product interest", response.text)
        self.assertFalse(self.env["b2b.registration.application"].search([
            ("business_email", "=", email),
        ]))

    def test_inactive_customer_type_cannot_be_submitted_directly(self):
        self.authenticate(None, None)
        email = "registration-http-inactive-type@example.test"
        inactive_type = self.env["b2b.customer.type"].create({
            "name": "Inactive HTTP Registration Type",
            "active": False,
        })

        response = self._submit(self._payload(
            email, customer_type_id=str(inactive_type.id)
        ))

        self.assertEqual(response.status_code, 200)
        self.assertIn("Please complete all required registration fields", response.text)
        self.assertFalse(self.env["b2b.registration.application"].search([
            ("business_email", "=", email),
        ]))

    def test_duplicate_email_does_not_create_another_account(self):
        self.authenticate(None, None)
        email = "registration-http-duplicate@example.test"
        mail_new_test_user(
            self.env, login=email, groups="base.group_portal", email=email
        )

        response = self._submit(self._payload(email))

        self.assertEqual(response.status_code, 200)
        self.assertIn("An account already uses this email", response.text)
        self.assertEqual(
            self.env["res.users"].sudo().with_context(active_test=False).search_count([
                ("login", "=", email),
            ]),
            1,
        )

    @mute_logger("odoo.http")
    def test_turnstile_rejection_stops_registration_before_account_creation(self):
        self.authenticate(None, None)
        email = "registration-http-turnstile-rejected@example.test"

        def reject_turnstile(_record, ip_addr, token, action=False):
            self.assertTrue(ip_addr)
            self.assertFalse(token)
            self.assertEqual(action, "signup")
            return "wrong_token"

        with patch.object(
            self.env.registry["ir.http"],
            "_verify_turnstile_token",
            reject_turnstile,
        ):
            response = self.url_open("/en/web/signup", data=self._payload(email))

        self.assertEqual(response.status_code, 422)
        self.assertIn("human validation failed", response.text)
        self.assertFalse(self.env["b2b.registration.application"].search([
            ("business_email", "=", email),
        ]))
        self.assertFalse(
            self.env["res.users"].sudo().with_context(active_test=False).search([
                ("login", "=", email),
            ])
        )
