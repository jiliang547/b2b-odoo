from lxml import html
from unittest.mock import patch

from odoo import Command
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.website_sale.models.sale_order import SaleOrder as NativeWebsiteOrder
from odoo.addons.b2b_website.controllers.checkout_delivery import PartnerCheckoutDelivery
from odoo.addons.b2b_website.controllers.website_sale import PartnerHubWebsiteSale
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestManualFreight(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].search([], limit=1)
        cls.website.b2b_manual_freight = True
        cls.partner = cls.env["res.partner"].create({"name": "Manual freight customer", "b2b_approved": True})
        cls.usd = cls.env.ref("base.USD")
        cls.usd.active = True
        cls.pricelist = cls.env["product.pricelist"].create({"name": "Manual freight USD", "currency_id": cls.usd.id})
        cls.product = cls.env["product.product"].create({"name": "Manual freight speaker", "type": "consu", "list_price": 20000, "taxes_id": [Command.clear()]})
        cls.freight = cls.env["product.product"].create({"name": "Manual freight charge", "type": "service", "list_price": 0, "taxes_id": [Command.clear()]})
        cls.website.b2b_freight_product_id = cls.freight
        cls.carrier = cls.env["delivery.carrier"].create({"name": "Manual freight native carrier",
            "product_id": cls.freight.id, "delivery_type": "fixed", "fixed_price": 0,
            "is_published": True})

    def _order(self, **extra):
        return self.env["sale.order"].create({"partner_id": self.partner.id, "website_id": self.website.id,
            "pricelist_id": self.pricelist.id,
            "order_line": [Command.create({"product_id": self.product.id, "product_uom_qty": 1,
                "price_unit": 20000, "tax_ids": [Command.clear()]})], **extra})

    def _add_freight(self, order, amount=600):
        return self.env["sale.order.line"].create({"order_id": order.id, "product_id": self.freight.id,
            "product_uom_qty": 1, "price_unit": amount, "tax_ids": [Command.clear()]})

    def test_physical_products_keep_delivery_address_and_type(self):
        order = self._order()
        self.assertTrue(order._b2b_uses_manual_freight())
        self.assertTrue(order._has_deliverable_products())
        self.assertFalse(order.only_services)
        self.assertEqual(order.partner_shipping_id, self.partner)

    def test_checkout_never_auto_selects_or_adds_carrier_line(self):
        order = self._order()
        self.assertFalse(order._get_preferred_delivery_method(self.carrier))
        order._set_delivery_method(self.carrier, rate={"success": True, "price": 0})
        self.assertFalse(order.carrier_id)
        self.assertFalse(order.order_line.filtered("is_delivery"))
        self.assertEqual(order.amount_total, 20000)

    def test_carrier_based_express_wallet_does_not_bypass_regular_checkout(self):
        self.assertFalse(self._order()._allow_express_checkout())

    def test_native_backend_shipping_still_works_and_is_not_repriced(self):
        order = self._order()
        order.set_delivery_line(self.carrier, 600)
        self.assertEqual(order.amount_delivery, 600)
        with MockRequest(self.env, website=self.website, sale_order_id=order.id):
            order._verify_cart_after_update()
        self.assertEqual(order.amount_delivery, 600)
        self.assertEqual(order.order_line.filtered("is_delivery").price_unit, 600)

    def test_operator_adds_native_freight_line_and_native_totals(self):
        order = self._order()
        freight = self._add_freight(order)
        self.assertTrue(freight.is_delivery)
        self.assertFalse(order.carrier_id)
        self.assertEqual(order.amount_delivery, 600)
        self.assertEqual(order.amount_total, 20600)
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")
        order._recompute_prices()
        self.assertEqual(freight.price_unit, 600)

    def test_quantity_and_address_changes_preserve_manual_amount(self):
        order = self._order()
        freight = self._add_freight(order)
        order.set_delivery_line(self.carrier, 600)
        order.order_line.filtered(lambda l: not l.is_delivery).product_uom_qty = 2
        address = self.partner.copy({"name": "Alternate shipping address"})
        with MockRequest(self.env, website=self.website, sale_order_id=order.id):
            order._update_address(address.id, ["partner_shipping_id"])
            order._verify_cart_after_update()
        self.assertEqual(order.amount_delivery, 600)
        self.assertEqual(order._b2b_checkout_delivery_terms(), "FOB GUANGZHOU")

    def test_payment_without_carrier_keeps_native_cart_validation(self):
        order = self._order()
        order._check_cart_is_ready_to_be_paid()
        with patch.object(NativeWebsiteOrder, "_is_cart_ready", return_value=False):
            with self.assertRaisesRegex(ValidationError, "cart is not ready"):
                order._check_cart_is_ready_to_be_paid()

    def test_other_native_validation_errors_are_never_suppressed(self):
        order = self._order()
        with patch.object(NativeWebsiteOrder, "_check_cart_is_ready_to_be_paid",
                          side_effect=ValidationError("Stock or payment is unavailable")):
            with self.assertRaisesRegex(ValidationError, "Stock or payment"):
                order._check_cart_is_ready_to_be_paid()

    def test_native_stock_availability_still_blocks_payment(self):
        if "allow_out_of_stock_order" not in self.product._fields:
            self.skipTest("Optional website_sale_stock is not installed")
        self.product.write({"is_storable": True, "allow_out_of_stock_order": False})
        order = self._order()
        with self.assertRaises(ValidationError) as error:
            order._check_cart_is_ready_to_be_paid()
        self.assertNotEqual(str(error.exception), "No shipping method is selected.")

    def test_automatic_mode_retains_native_freight_and_payment_validation(self):
        self.website.b2b_manual_freight = False
        order = self._order()
        with self.assertRaisesRegex(ValidationError, "No shipping method"):
            order._check_cart_is_ready_to_be_paid()
        order._set_delivery_method(self.carrier, rate={"success": True, "price": 0})
        self.assertEqual(order.carrier_id, self.carrier)
        self.assertEqual(len(order.order_line.filtered("is_delivery")), 1)

    def test_no_carrier_payment_errors_are_removed_only_in_manual_mode(self):
        order = self._order()
        with MockRequest(self.env, website=self.website), patch.object(NativeWebsiteOrder, "_get_delivery_methods", return_value=self.env["delivery.carrier"]):
            self.assertEqual(PartnerHubWebsiteSale()._get_shop_payment_errors(order), [])
            self.website.b2b_manual_freight = False
            self.assertTrue(PartnerHubWebsiteSale()._get_shop_payment_errors(order))

    def test_carrier_rpc_cannot_add_or_overwrite_manual_freight(self):
        order = self._order()
        freight = self._add_freight(order)
        with MockRequest(self.env, website=self.website, sale_order_id=order.id) as req:
            req.cart = order
            controller = PartnerCheckoutDelivery()
            result = controller.shop_set_delivery_method.__wrapped__(controller, str(self.carrier.id))
            rate = controller.shop_get_delivery_rate.__wrapped__(controller, self.carrier.id)
        self.assertTrue(result["success"])
        self.assertEqual(rate, result)
        self.assertEqual(freight.price_unit, 600)
        self.assertFalse(order.carrier_id)
        self.assertEqual(order._b2b_checkout_delivery_terms(), "EXW GUANGZHOU")

    def test_old_zero_line_removed_only_from_unpaid_active_draft(self):
        order = self._order()
        order.set_delivery_line(self.carrier, 0)
        order._b2b_clear_legacy_free_delivery()
        self.assertFalse(order.order_line.filtered("is_delivery"))
        self.assertFalse(order.carrier_id)
        for values in ({"state": "sent"}, {"b2b_is_change_revision": True}):
            with self.subTest(values=values):
                historical = self._order(**values)
                historical.set_delivery_line(self.carrier, 0)
                historical._b2b_clear_legacy_free_delivery()
                self.assertEqual(len(historical.order_line.filtered("is_delivery")), 1)

    def test_cleanup_preserves_priced_freight(self):
        order = self._order()
        self._add_freight(order)
        order._b2b_clear_legacy_free_delivery()
        self.assertEqual(order.amount_delivery, 600)

    def test_configured_freight_must_be_shared_service(self):
        with self.assertRaisesRegex(ValidationError, "shared, saleable service"):
            self.website.b2b_freight_product_id = self.product

    def test_changing_product_does_not_leave_goods_classified_as_freight(self):
        order = self._order()
        line = self._add_freight(order)
        line.product_id = self.product
        self.assertFalse(line.is_delivery)

    def test_revision_values_preserve_native_freight_flag(self):
        line = self._add_freight(self._order())
        values = self.env["b2b.order.change.request"]._revision_line_values(line)
        self.assertTrue(values["is_delivery"])

    def test_rendered_checkout_keeps_form_and_address_refresh_without_carrier_radios(self):
        order = self._order()
        with MockRequest(self.env, website=self.website, sale_order_id=order.id):
            page = self.env["ir.ui.view"]._render_template("website_sale.delivery_form", {
                "order": order, "delivery_methods": self.carrier, "selected_dm_id": False,
            })
        parsed = html.fromstring(page)
        self.assertEqual(len(parsed.xpath("//form[@id='o_delivery_form']")), 1)
        self.assertFalse(parsed.xpath("//input[@name='o_delivery_radio']"))
        self.assertIn("EXW GUANGZHOU", parsed.text_content())
        self.assertNotIn("Free", parsed.text_content())

    def test_cart_total_has_no_empty_delivery_row_but_shows_manual_amount(self):
        order = self._order()
        for freight in (False, True):
            if freight:
                self._add_freight(order)
            with MockRequest(self.env, website=self.website, sale_order_id=order.id):
                page = self.env["ir.ui.view"]._render_template("website_sale.total", {"website_sale_order": order})
            parsed = html.fromstring(page)
            rows = parsed.xpath("//tr[@name='o_order_delivery']")
            self.assertEqual(bool(rows), freight)
            if freight:
                self.assertIn("600", rows[0].text_content())
