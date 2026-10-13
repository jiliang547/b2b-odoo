from lxml import html

from odoo import Command
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCheckoutPaymentActions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.customer = cls.env["res.partner"].create({"name": "Payment layout customer"})
        cls.product = cls.env["product.product"].create({"name": "Payment layout speaker", "type": "consu"})

    def _order(self, policy="a", amount=100):
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id, "website_id": self.website.id,
            "b2b_collection_policy_id": self.env.ref("b2b_website.collection_policy_" + policy).id,
            "order_line": [Command.create({"product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": amount, "tax_ids": [Command.clear()]})],
        })
        order._b2b_start_collection()
        return order

    def _render(self, order, **overrides):
        values = {
            "website_sale_order": order, "website": self.website,
            "current_website_checkout_step_href": "/shop/payment",
            "show_shorter_cart_summary": False, "hide_payment_button": False,
            "previous_website_checkout_step": False, "errors": [],
            "_container_classes": "", "submit_button_label": "Pay Now",
            **overrides,
        }
        with MockRequest(self.env, website=self.website, sale_order_id=order.id):
            page = self.env["ir.ui.view"]._render_template("website_sale.navigation_buttons", values)
        return html.fromstring(page)

    def test_bank_primary_and_secondary_actions_inside_closed_native_details(self):
        page = self._render(self._order())
        bank = page.xpath("//form[@action='/shop/b2b-submit-order']")[0]
        self.assertEqual(bank.xpath("./button")[0].text_content().strip(), "Pay by Bank (TT)")
        self.assertIn("btn-primary", bank.xpath("./button")[0].get("class"))
        self.assertFalse(bank.xpath("ancestor::details"))
        details = page.xpath("//details")[0]
        self.assertIsNone(details.get("open"))
        self.assertEqual(details.xpath("./summary")[0].text_content().strip(), "More options")
        self.assertEqual(len(details.xpath(".//button[@name='o_payment_submit_button']")), 1)
        self.assertEqual(len(details.xpath(".//form[@action='/shop/submit-for-review']")), 1)
        self.assertFalse(details.xpath(".//form[@action='/shop/b2b-submit-order']"))
        self.assertNotIn("Confirm shipping and final pricing with our team before payment.", page.text_content())
        for form in (bank, details.xpath(".//form")[0]):
            self.assertEqual(form.get("method"), "post")
            self.assertTrue(form.xpath("./input[@name='csrf_token']"))
            self.assertIsNotNone(form.get("data-lt-submit-once"))

    def test_all_payment_policies_have_same_bank_label_but_keep_own_terms(self):
        for policy in ("a", "b20", "b30", "c", "d", "e"):
            with self.subTest(policy=policy):
                order = self._order(policy)
                before = order.read(["b2b_production_percent", "b2b_shipment_percent", "require_payment", "prepayment_percent", "state"])
                page = self._render(order)
                self.assertEqual(page.xpath("//form[@action='/shop/b2b-submit-order']/button")[0].text_content().strip(), "Pay by Bank (TT)")
                self.assertIn(order._b2b_customer_terms_label(), page.text_content())
                self.assertNotIn("Place Order on Agreed Terms", page.text_content())
                self.assertEqual(order.read(["b2b_production_percent", "b2b_shipment_percent", "require_payment", "prepayment_percent", "state"]), before)

    def test_native_online_button_is_not_duplicated_or_replaced(self):
        page = self._render(self._order())
        buttons = page.xpath("//button[@name='o_payment_submit_button']")
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].text_content().strip(), "Pay Now")
        self.assertEqual(buttons[0].get("type"), "submit")
        self.assertIsNotNone(buttons[0].get("disabled"))
        self.assertFalse(buttons[0].xpath("ancestor::form"))

    def test_zero_total_retains_native_confirm_order_not_bank_or_review(self):
        page = self._render(self._order(amount=0))
        native = page.xpath("//form[@action='/shop/payment/validate']")
        self.assertEqual(len(native), 1)
        self.assertEqual(native[0].xpath("./button")[0].text_content().strip(), "Confirm Order")
        self.assertFalse(page.xpath("//details | //form[@action='/shop/b2b-submit-order'] | //form[@action='/shop/submit-for-review']"))

    def test_native_hide_payment_button_also_hides_custom_actions(self):
        page = self._render(self._order(), hide_payment_button=True)
        self.assertFalse(page.xpath("//details | //button | //form"))

    def test_checkout_errors_do_not_offer_bank_or_review_bypass(self):
        page = self._render(self._order(), errors=["Checkout validation failed"])
        self.assertFalse(page.xpath("//form[@action='/shop/b2b-submit-order'] | //form[@action='/shop/submit-for-review']"))
        self.assertEqual(len(page.xpath("//button[@name='o_payment_submit_button']")), 1)
