from lxml import html

from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerServiceIntakeHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({
            "name": "Service intake HTTP customer",
            "email": "service-intake@example.test",
            "b2b_approved": True,
        })
        cls.portal_user = mail_new_test_user(
            cls.env, login="service-intake-http", password="Service-Intake-2026!",
            groups="base.group_portal", partner_id=cls.customer.id,
        )
        cls.product = cls.env["product.product"].create({
            "name": "Service intake HTTP product", "sale_ok": True,
        })
        # A historical confirmed-order fixture, without confirmation/ERP side effects.
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.customer.id, "state": "sale",
            "order_line": [Command.create({
                "product_id": cls.product.id, "product_uom_qty": 1, "price_unit": 100,
            })],
        })

    def _form(self):
        self.authenticate(self.portal_user.login, "Service-Intake-2026!")
        response = self.url_open("/service")
        self.assertEqual(response.status_code, 200)
        return html.fromstring(response.content)

    def _payload(self, form):
        payload = {
            "csrf_token": form.xpath("//input[@name='csrf_token']/@value")[0],
            "submission_token": form.xpath("//input[@name='submission_token']/@value")[0],
            "order_id": str(self.order.id), "product_id": str(self.product.id),
            "model_number": "SUPPORT-HTTP-2026", "description": "Help with configuration.",
            "contact_name": "Service intake tester", "company_name": "Test customer",
            "email": self.customer.email, "phone": "+1 202 555 0100",
            "request_type": "support",
        }
        return payload

    def _tickets(self):
        return self.env["helpdesk.ticket"].search([("b2b_sale_order_id", "=", self.order.id)])

    def test_only_technical_support_is_rendered_and_checked(self):
        form = self._form()
        options = form.xpath("//input[@name='request_type']")
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0].get("value"), "support")
        self.assertIsNotNone(options[0].get("checked"))
        self.assertEqual(options[0].getparent().text_content().strip(), "Technical Support")

    def test_support_submission_creates_one_existing_helpdesk_ticket(self):
        payload = self._payload(self._form())
        response = self.url_open("/service", data=payload)
        self.assertEqual(response.status_code, 200)
        tickets = self._tickets()
        self.assertEqual(len(tickets), 1)
        self.assertEqual(tickets.b2b_request_type, "support")
        self.assertEqual(tickets.partner_id, self.customer)
        self.assertEqual(tickets.b2b_product_id, self.product)
        self.assertEqual(tickets.b2b_service_route, "assessment")
        self.url_open("/service", data=payload)
        self.assertEqual(len(self._tickets()), 1)

    def test_missing_type_defaults_to_support(self):
        payload = self._payload(self._form())
        payload.pop("request_type")
        response = self.url_open("/service", data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._tickets().b2b_request_type, "support")

    def test_hidden_types_cannot_be_forged_into_website_intake(self):
        payload = self._payload(self._form())
        for request_type in ("repair", "replacement", "", "unsupported"):
            with self.subTest(request_type=request_type):
                response = self.url_open("/service", data=dict(payload, request_type=request_type))
                self.assertEqual(response.status_code, 200)
                self.assertIn("Please submit a technical support request.", response.text)
                self.assertFalse(self._tickets())
                options = html.fromstring(response.content).xpath("//input[@name='request_type']")
                self.assertEqual(len(options), 1)
                self.assertEqual(options[0].get("value"), "support")
                self.assertIsNotNone(options[0].get("checked"))
