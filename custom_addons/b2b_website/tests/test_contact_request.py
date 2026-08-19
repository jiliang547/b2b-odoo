from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestContactRequestSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
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
