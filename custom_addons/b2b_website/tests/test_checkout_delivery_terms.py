from lxml import html

from odoo import Command, fields
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale.controllers.delivery import Delivery
from odoo.tests import TransactionCase, tagged
from odoo.addons.b2b_website.controllers.checkout_delivery import PartnerCheckoutDelivery


@tagged("post_install", "-at_install")
class TestCheckoutDeliveryTerms(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.usd = cls.env.ref("base.USD")
        cls.usd.active = True
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.b2b_manual_freight = False
        cls.customer = cls.env["res.partner"].create({"name": "Checkout terms customer", "b2b_approved": True})
        cls.pricelist = cls.env["product.pricelist"].create({"name": "Checkout terms USD", "currency_id": cls.usd.id})
        cls.product = cls.env["product.product"].create({"name": "Checkout terms speaker", "type": "consu"})
        cls.freight = cls.env["product.product"].create({"name": "Checkout terms freight", "type": "service"})
        cls.carrier = cls.env["delivery.carrier"].create({
            "name": "Checkout terms carrier", "delivery_type": "fixed", "fixed_price": 1000,
            "product_id": cls.freight.id, "is_published": True,
        })

    def _order(self, amount, **extra):
        return self.env["sale.order"].create({
            "partner_id": self.customer.id, "website_id": self.website.id,
            "pricelist_id": self.pricelist.id,
            "order_line": [Command.create({"product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": amount, "tax_ids": [Command.clear()]})],
            **extra,
        })

    def test_strict_usd_threshold_and_cent_precision(self):
        for amount, label in ((0, "EXW"), (19999.99, "EXW"), (20000, "EXW"), (20000.01, "FOB"), (25000, "FOB")):
            with self.subTest(amount=amount):
                self.assertEqual(self._order(amount)._b2b_checkout_delivery_terms(), label + " GUANGZHOU")

    def test_taxes_and_native_delivery_do_not_change_goods_threshold(self):
        order = self._order(19999)
        tax = self.env["account.tax"].create({"name": "Checkout terms tax", "amount": 13,
            "amount_type": "percent", "type_tax_use": "sale", "company_id": order.company_id.id})
        order.order_line.tax_ids = tax
        order.order_line = [Command.create({"product_id": self.freight.id,
            "product_uom_qty": 1, "price_unit": 1000, "is_delivery": True, "tax_ids": [Command.clear()]})]
        self.assertGreater(order.amount_total, 20000)
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")

    def test_native_delivery_product_recognizes_manually_added_freight(self):
        order = self._order(20000)
        order.order_line = [Command.create({"product_id": self.freight.id,
            "product_uom_qty": 1, "price_unit": 2000, "tax_ids": [Command.clear()]})]
        self.assertFalse(order.order_line.filtered(lambda line: line.product_id == self.freight).is_delivery)
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")

    def test_ordinary_service_products_are_not_misclassified_as_freight(self):
        order = self._order(20000)
        service = self.env["product.product"].create({"name": "Installation guidance", "type": "service"})
        order.order_line = [Command.create({"product_id": service.id,
            "product_uom_qty": 1, "price_unit": 1, "tax_ids": [Command.clear()]})]
        self.assertEqual(order._b2b_checkout_delivery_terms(), "FOB GUANGZHOU")

    def test_discounts_and_multiple_products_use_native_net_subtotals(self):
        order = self._order(25000)
        order.order_line.discount = 20
        order.order_line = [Command.create({"display_type": "line_note", "name": "Ignored note"})]
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")
        order.order_line = [Command.create({"product_id": self.product.id,
            "product_uom_qty": 1, "price_unit": 0.01, "tax_ids": [Command.clear()]})]
        self.assertEqual(order._b2b_checkout_delivery_terms(), "FOB GUANGZHOU")

    def test_non_usd_uses_native_order_company_and_order_date_rates(self):
        currency = self.env["res.currency"].create({"name": "UXT", "symbol": "UX", "rounding": 0.01})
        company = self.env["res.company"].create({"name": "Checkout terms exchange company", "currency_id": self.usd.id})
        self.env["res.currency.rate"].create([
            {"currency_id": self.usd.id, "company_id": company.id, "name": "2026-10-10", "rate": 1},
            {"currency_id": currency.id, "company_id": company.id, "name": "2026-10-10", "rate": 6.3},
            {"currency_id": currency.id, "company_id": company.id, "name": "2026-10-12", "rate": 7},
        ])
        pricelist = self.pricelist.copy({"name": "Checkout terms foreign currency", "currency_id": currency.id,
            "company_id": company.id, "website_id": False})
        order = self.env["sale.order"].with_company(company).create({
            "partner_id": self.customer.id, "pricelist_id": pricelist.id, "date_order": "2026-10-10 12:00:00",
            "order_line": [Command.create({"product_id": self.product.id,
                "product_uom_qty": 1, "price_unit": 126000, "tax_ids": [Command.clear()]})],
        })
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")
        order.order_line.price_unit = 126006.3
        self.assertEqual(order.with_company(self.env.company)._b2b_checkout_delivery_terms(), "FOB GUANGZHOU")

    def test_display_helper_does_not_write_order_amounts_carrier_or_incoterm(self):
        order = self._order(21000)
        before = order.read(["amount_total", "amount_untaxed", "amount_tax", "carrier_id", "incoterm", "write_date"])
        self.assertEqual(order._b2b_checkout_delivery_terms(), "FOB GUANGZHOU")
        self.assertEqual(order.read(["amount_total", "amount_untaxed", "amount_tax", "carrier_id", "incoterm", "write_date"]), before)

    def test_native_summary_values_only_add_a_display_label(self):
        order = self._order(20000)
        with MockRequest(self.env, website=self.website, sale_order_id=order.id):
            native = Delivery()._order_summary_values(order)
            result = PartnerCheckoutDelivery()._order_summary_values(order)
        label = result.pop("b2b_delivery_terms")
        self.assertEqual(label, "EXW GUANGZHOU")
        self.assertEqual(result, native)

    def test_native_rate_rpc_keeps_actual_freight_and_adds_current_goods_label(self):
        order = self._order(20000)
        with MockRequest(self.env, website=self.website, sale_order_id=order.id) as mock_request:
            mock_request.cart = order
            native = Delivery().shop_get_delivery_rate(self.carrier.id)
            # Inherited @route() metadata is merged by the HTTP dispatcher;
            # exercise the controller body directly in this unit-level mock.
            controller = PartnerCheckoutDelivery()
            result = controller.shop_get_delivery_rate.__wrapped__(controller, self.carrier.id)
        self.assertTrue(result["success"])
        self.assertEqual(result.pop("b2b_delivery_terms"), "EXW GUANGZHOU")
        self.assertEqual(result, native)

    def test_non_website_summary_retains_native_behavior(self):
        order = self._order(21000, website_id=False)
        with MockRequest(self.env, website=self.website):
            self.assertEqual(PartnerCheckoutDelivery()._order_summary_values(order),
                Delivery()._order_summary_values(order))

    def test_rendered_delivery_badge_is_ready_before_native_rpc_refresh(self):
        for amount, expected in ((20000, "EXW GUANGZHOU"), (20000.01, "FOB GUANGZHOU")):
            with self.subTest(amount=amount):
                order = self._order(amount)
                with MockRequest(self.env, website=self.website, sale_order_id=order.id):
                    page = self.env["ir.ui.view"]._render_template("website_sale.delivery_method", {
                        "dm": self.carrier, "is_selected": True, "order": order,
                    })
                badge = html.fromstring(page).xpath("//span[@data-lt-delivery-terms]")[0]
                self.assertEqual(badge.get("data-lt-delivery-terms"), expected)
                self.assertEqual(badge.text_content().strip(), expected)
