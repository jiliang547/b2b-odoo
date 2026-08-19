from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import SampleCase


@tagged("post_install", "-at_install")
class TestSampleSecurity(SampleCase):
    def test_portal_create_forces_ownership_and_submitted_state(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        self.assertEqual(sample.commercial_partner_id, self.company)
        self.assertEqual(sample.contact_id, self.contact)
        self.assertEqual(sample.state, "submitted")
        self.assertIn(self.contact, sample.sudo().message_partner_ids)

    def test_portal_can_post_public_message_on_own_sample(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        message = sample.with_user(self.portal_user).message_post(
            body="Please confirm the requested delivery date.",
            message_type="comment",
            subtype_xmlid="mail.mt_comment",
        )
        self.assertEqual(message.author_id, self.contact)

    def test_portal_cannot_create_detached_line_through_rpc_model(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        with self.assertRaises(AccessError):
            self.env["b2b.sample.request.line"].with_user(self.portal_user).create({
                "request_id": sample.id,
                "product_id": self.product.id,
                "quantity": 2,
                "uom_id": self.product.uom_id.id,
            })

    def test_cross_company_sample_is_not_readable(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        other_company = self.env["res.partner"].create({"name": "Other Co", "is_company": True})
        other_contact = self.env["res.partner"].create({
            "name": "Other Contact", "parent_id": other_company.id, "email": "other@example.com"
        })
        other_user = mail_new_test_user(
            self.env, login="sample-other", groups="base.group_portal", partner_id=other_contact.id
        )
        with self.assertRaises(AccessError):
            sample.with_user(other_user).read(["name"])
