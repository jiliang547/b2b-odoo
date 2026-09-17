from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestContactRequestSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.salesperson = mail_new_test_user(
            cls.env,
            login="contact-request-salesperson",
            groups="base.group_user,b2b_core.group_b2b_operator",
        )
        cls.website.salesperson_id = cls.salesperson
        cls.company = cls.env["res.partner"].create({
            "name": "Contact Request Company", "is_company": True,
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Contact Request User",
            "parent_id": cls.company.id,
            "email": "contact-request@example.test",
        })
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="contact-request-portal",
            groups="base.group_portal",
            partner_id=cls.contact.id,
        )
        cls.contact_request = cls.env["b2b.contact.request"].create({
            "request_type": "company_change",
            "subject": "Update company record",
            "contact_name": cls.contact.name,
            "email": cls.contact.email,
            "company_name": cls.company.name,
            "message": "Please review our updated registered address.",
            "partner_id": cls.contact.id,
            "website_id": cls.website.id,
        })

    def test_portal_reads_own_company_request_and_is_subscribed(self):
        values = self.contact_request.with_user(self.portal_user).read(["name"])
        self.assertEqual(values[0]["name"], self.contact_request.name)
        self.assertIn(self.contact, self.contact_request.message_partner_ids)

    def test_new_request_is_assigned_and_schedules_sales_activity(self):
        self.assertEqual(self.contact_request.assigned_user_id, self.salesperson)
        self.assertIn(
            self.salesperson.partner_id,
            self.contact_request.message_partner_ids,
        )
        self.assertTrue(
            self.contact_request.activity_ids.filtered(
                lambda activity: activity.user_id == self.salesperson
            )
        )

    def test_salesperson_without_b2b_access_is_not_assigned(self):
        non_operator = mail_new_test_user(
            self.env,
            login="contact-request-non-operator",
            groups="base.group_user",
        )
        self.website.salesperson_id = non_operator
        contact_request = self.env["b2b.contact.request"].create({
            "request_type": "sales",
            "subject": "Access-safe assignment",
            "contact_name": self.contact.name,
            "email": self.contact.email,
            "message": "Please assign this to an operator.",
            "partner_id": self.contact.id,
            "website_id": self.website.id,
        })
        self.assertNotEqual(contact_request.assigned_user_id, non_operator)
        self.assertTrue(
            contact_request.assigned_user_id.has_group(
                "b2b_core.group_b2b_operator"
            )
        )

    def test_portal_customer_can_reply_on_own_request(self):
        message = self.contact_request.with_user(self.portal_user).message_post(
            body="Customer follow-up",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertEqual(message.author_id, self.contact)
        self.assertFalse(message.is_internal)

    def test_staff_reply_uses_native_unread_notification_until_opened(self):
        self.assertEqual(
            self.env["b2b.contact.request"]
            .with_user(self.portal_user)
            .get_portal_unread_message_count(),
            0,
        )
        reply = self.contact_request.with_user(self.salesperson).message_post(
            body="Your pricing request has been reviewed.",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        notification = self.env["mail.notification"].sudo().search([
            ("mail_message_id", "=", reply.id),
            ("res_partner_id", "=", self.contact.id),
        ])
        self.assertTrue(notification)
        self.assertFalse(notification.is_read)
        self.assertEqual(
            self.env["b2b.contact.request"]
            .with_user(self.portal_user)
            .get_portal_unread_message_count(),
            1,
        )

        reply.with_user(self.portal_user).set_message_done()
        self.assertTrue(notification.is_read)
        self.assertEqual(
            self.env["b2b.contact.request"]
            .with_user(self.portal_user)
            .get_portal_unread_message_count(),
            0,
        )

    def test_guest_acknowledgement_targets_submitted_email(self):
        guest_request = self.env["b2b.contact.request"].create({
            "request_type": "sales",
            "subject": "Guest pricing inquiry",
            "contact_name": "Guest Buyer",
            "email": "guest-buyer@example.test",
            "message": "Please provide pricing.",
            "website_id": self.website.id,
        })
        acknowledgement = guest_request.message_ids.filtered(
            lambda message: message.outgoing_email_to
            == "guest-buyer@example.test"
        )[:1]
        self.assertTrue(acknowledgement)
        self.assertFalse(guest_request.partner_id)

    def test_portal_cannot_read_another_company_request(self):
        other_company = self.env["res.partner"].create({
            "name": "Other Contact Company", "is_company": True,
        })
        other_contact = self.env["res.partner"].create({
            "name": "Other Contact", "parent_id": other_company.id,
            "email": "other-contact@example.test",
        })
        other_user = mail_new_test_user(
            self.env,
            login="other-contact-request-portal",
            groups="base.group_portal",
            partner_id=other_contact.id,
        )
        with self.assertRaises(AccessError):
            self.contact_request.with_user(other_user).read(["name"])

    def test_public_user_has_no_model_access(self):
        with self.assertRaises(AccessError):
            self.contact_request.with_user(self.env.ref("base.public_user")).read(["name"])

    def test_duplicate_open_company_request_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["b2b.contact.request"].create({
                "request_type": "company_change",
                "subject": "Duplicate company request",
                "contact_name": self.contact.name,
                "email": self.contact.email,
                "message": "This request must not create a duplicate review item.",
                "partner_id": self.contact.id,
                "website_id": self.website.id,
            })

    def test_request_company_follows_contact_commercial_partner(self):
        standalone = self.env["res.partner"].create({
            "name": "Standalone Portal Contact",
            "email": "standalone-company-request@example.test",
        })
        company_request = self.env["b2b.contact.request"].create({
            "request_type": "company_change",
            "subject": "Company setup request",
            "contact_name": standalone.name,
            "email": standalone.email,
            "message": "Please link this account to its verified company.",
            "partner_id": standalone.id,
            "website_id": self.website.id,
        })
        self.assertEqual(company_request.commercial_partner_id, standalone)

        new_company = self.env["res.partner"].create({
            "name": "Verified Standalone Company",
            "is_company": True,
        })
        standalone.parent_id = new_company
        self.assertEqual(company_request.commercial_partner_id, new_company)
