from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BProductPolicy(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.write({
            "b2b_price_display_mode": "approved",
            "b2b_guest_price_state": "login",
        })
        cls.segment = cls.env["b2b.customer.segment"].create({"name": "Dealer Test"})
        cls.company = cls.env["res.partner"].create({
            "name": "Approved Dealer",
            "is_company": True,
            "b2b_approved": True,
            "b2b_segment_ids": [Command.link(cls.segment.id)],
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Portal Contact", "parent_id": cls.company.id, "email": "dealer@example.com"
        })
        cls.portal_user = mail_new_test_user(
            cls.env, login="b2b-policy-user", groups="base.group_portal", partner_id=cls.contact.id
        )
        cls.allowed = cls.env["product.template"].create({
            "name": "Dealer Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "segments",
            "b2b_visible_segment_ids": [Command.link(cls.segment.id)],
        })
        cls.hidden = cls.env["product.template"].create({
            "name": "Hidden Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "hidden",
        })

    def test_segment_visibility_and_price_gate(self):
        service = self.env["b2b.product.service"].with_user(self.portal_user)
        self.assertTrue(service.is_visible(self.allowed, website=self.website))
        self.assertFalse(service.is_visible(self.hidden, website=self.website))
        self.assertTrue(service.can_view_price(website=self.website))

    def test_native_shop_domain_contains_policy(self):
        website = self.website.with_user(self.portal_user)
        products = self.env["product.template"].with_user(self.portal_user).search(
            website.sale_product_domain()
        )
        self.assertIn(self.allowed, products)
        self.assertNotIn(self.hidden, products)

    def test_generic_portal_orm_search_cannot_bypass_policy(self):
        products = self.env["product.template"].with_user(self.portal_user).search([])
        self.assertIn(self.allowed, products)
        self.assertNotIn(self.hidden, products)

    def test_unapproved_customer_does_not_receive_numeric_price(self):
        self.company.b2b_approved = False
        service = self.env["b2b.product.service"].with_user(self.portal_user)
        payload = service.price_payload(self.allowed, website=self.website)
        self.assertEqual(payload[self.allowed.id]["state"], "quote")
        self.assertNotIn("price", payload[self.allowed.id])

    def test_website_administrator_can_view_price_without_customer_approval(self):
        self.website.b2b_price_display_mode = "never"
        administrator = self.env.ref("base.user_admin")
        service = self.env["b2b.product.service"].with_user(administrator)
        self.assertTrue(service.can_view_price(website=self.website))
        self.assertEqual(service.price_state(website=self.website), "visible")
