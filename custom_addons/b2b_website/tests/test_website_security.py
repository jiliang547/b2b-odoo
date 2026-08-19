from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestWebsiteOrderSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.b2b_price_display_mode = "approved"
        cls.company = cls.env["res.partner"].create({
            "name": "Unapproved Portal Company", "is_company": True, "b2b_approved": False
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Unapproved Contact", "parent_id": cls.company.id, "email": "pending@example.com"
        })
        cls.portal_user = mail_new_test_user(
            cls.env, login="website-unapproved", groups="base.group_portal", partner_id=cls.contact.id
        )
        cls.product = cls.env["product.product"].create({
            "name": "Public Information Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "all",
        })
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.company.id, "website_id": cls.website.id
        })

    def test_direct_cart_add_is_blocked_without_price_permission(self):
        with self.assertRaises(AccessError):
            self.order.with_user(self.portal_user)._prepare_order_line_values(
                self.product.id, 1, self.product.uom_id.id
            )

@tagged("post_install", "-at_install")
class TestWebsiteIDOR(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.segment = cls.env["b2b.customer.segment"].create({"name": "Private Segment"})
        cls.company = cls.env["res.partner"].create({
            "name": "Portal Company", "is_company": True, "b2b_approved": True
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Portal Person", "parent_id": cls.company.id, "email": "portal-http@example.com"
        })
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="portal-http",
            password="portal-http",
            groups="base.group_portal",
            partner_id=cls.contact.id,
        )
        cls.restricted_product = cls.env["product.template"].create({
            "name": "Restricted HTTP Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "segments",
            "b2b_visible_segment_ids": [Command.link(cls.segment.id)],
        })
        other = cls.env["res.partner"].create({"name": "Other Order Owner", "is_company": True})
        cls.other_order = cls.env["sale.order"].create({"partner_id": other.id})

    def test_restricted_product_direct_url_returns_not_found(self):
        self.authenticate("portal-http", "portal-http")
        slug = self.env["ir.http"]._slug(self.restricted_product)
        response = self.url_open("/products/%s" % slug)
        self.assertEqual(response.status_code, 404)

    def test_other_company_erp_status_returns_not_found(self):
        self.authenticate("portal-http", "portal-http")
        response = self.url_open("/my/orders/%s/erp-status" % self.other_order.id)
        self.assertEqual(response.status_code, 404)
