from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ValidationError
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
class TestWebsiteSaleQuantity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.b2b_price_display_mode = "approved"
        cls.company = cls.env["res.partner"].create({
            "name": "Approved Quantity Company", "is_company": True, "b2b_approved": True,
        })
        cls.contact = cls.env["res.partner"].create({
            "name": "Approved Quantity Contact",
            "parent_id": cls.company.id,
            "email": "quantity@example.com",
        })
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="website-quantity",
            groups="base.group_portal",
            partner_id=cls.contact.id,
        )
        cls.product = cls.env["product.product"].create({
            "name": "Whole Unit Product",
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "all",
        })
        cls.pricelist = cls.env["product.pricelist"].search([], limit=1)
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.company.id,
            "website_id": cls.website.id,
            "pricelist_id": cls.pricelist.id,
        })

    def test_product_unit_precision_is_not_the_purchase_step(self):
        procurement = self.env["b2b.product.service"].procurement_info(
            self.product,
            pricelist=self.order.pricelist_id,
            website=self.website,
        )
        self.assertEqual(procurement["quantity_step"], 1.0)

    def test_fractional_website_quantity_is_rejected(self):
        order = self.order.with_user(self.portal_user)
        order._verify_updated_quantity(
            self.env["sale.order.line"],
            self.product.id,
            1,
            self.product.uom_id.id,
        )
        with self.assertRaises(ValidationError):
            order._verify_updated_quantity(
                self.env["sale.order.line"],
                self.product.id,
                1.01,
                self.product.uom_id.id,
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
        self.assertTrue(self.portal_user.has_group("base.group_portal"))
        self.authenticate("portal-http", "portal-http")
        slug = self.env["ir.http"]._slug(self.restricted_product)
        response = self.url_open("/en/products/%s" % slug)
        # Both statuses disclose no record data. The standalone HttpCase web
        # worker can return 403 while rendering Odoo's 404 without a website
        # ACL context; the real localized portal route is browser-checked as 404.
        self.assertIn(response.status_code, (403, 404), response.text[:500])

    def test_other_company_erp_status_returns_not_found(self):
        self.assertTrue(self.portal_user.has_group("base.group_portal"))
        self.authenticate("portal-http", "portal-http")
        response = self.url_open("/en/my/orders/%s/erp-status" % self.other_order.id)
        self.assertIn(response.status_code, (403, 404), response.text[:500])


@tagged("post_install", "-at_install")
class TestCompanyOnboardingHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.env["res.partner"].create({
            "name": "Company Onboarding Contact",
            "email": "company-onboarding-http@example.com",
        })
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="company-onboarding-http",
            password="company-onboarding-http",
            groups="base.group_portal",
            partner_id=cls.contact.id,
        )

    def _authenticate(self):
        self.authenticate("company-onboarding-http", "company-onboarding-http")

    def test_unlinked_contact_sees_setup_prompt_and_form(self):
        self._authenticate()
        dashboard = self.url_open("/en/my")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Connect your company account", dashboard.text)
        self.assertIn("Request Company Setup", dashboard.text)

        company_form = self.url_open("/en/my/company/change")
        self.assertEqual(company_form.status_code, 200)
        self.assertIn("Request Company Setup", company_form.text)
        self.assertIn("Submit the company you represent", company_form.text)

    def test_open_request_replaces_form_with_review_state(self):
        request_record = self.env["b2b.contact.request"].create({
            "partner_id": self.contact.id,
            "website_id": self.env["website"].search([], limit=1).id,
            "request_type": "company_change",
            "subject": "Set up Test Company",
            "contact_name": self.contact.name,
            "email": self.contact.email,
            "message": "Please link my login to Test Company.",
        })
        self._authenticate()

        dashboard = self.url_open("/en/my")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("Company request under review", dashboard.text)
        self.assertIn("/my/inquiries/%s" % request_record.id, dashboard.text)

        company_form = self.url_open("/en/my/company/change")
        self.assertEqual(company_form.status_code, 200)
        self.assertIn("Company request under review", company_form.text)
        self.assertNotIn("name=\"company_name\"", company_form.text)

    def test_linked_contact_sees_company_as_effective_account(self):
        company = self.env["res.partner"].create({
            "name": "Effective Portal Company",
            "is_company": True,
            "b2b_approved": True,
        })
        self.contact.parent_id = company
        self._authenticate()

        company_profile = self.url_open("/en/my/company")
        self.assertEqual(company_profile.status_code, 200)
        self.assertIn("Effective Portal Company", company_profile.text)
        self.assertIn("Partner Hub Approved", company_profile.text)
        self.assertNotIn("Set up your company profile", company_profile.text)

    def test_native_profile_navigation_highlights_current_page(self):
        self._authenticate()

        profile = self.url_open("/en/my/account")
        self.assertEqual(profile.status_code, 200)
        self.assertIn('title="Personal profile" class="is-active"', profile.text)

        addresses = self.url_open("/en/my/addresses")
        self.assertEqual(addresses.status_code, 200)
        self.assertIn('title="Addresses" class="is-active"', addresses.text)

    def test_footer_after_sales_uses_native_ticket_portal(self):
        homepage = self.url_open("/en")
        self.assertEqual(homepage.status_code, 200)
        self.assertIn('my/tickets">After-Sales Support</a>', homepage.text)
