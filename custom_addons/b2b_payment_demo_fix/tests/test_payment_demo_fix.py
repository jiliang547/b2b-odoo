from odoo import Command
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPaymentDemoCompatibility(TransactionCase):
    def test_simplified_chinese_demo_states_are_normalized(self):
        transaction = self.env["payment.transaction"]
        expected_states = {
            "完成": "done",
            "进行中": "pending",
            "取消": "cancel",
            "错误": "error",
        }

        for localized_state, technical_state in expected_states.items():
            payment_data = transaction._b2b_normalize_demo_payment_data({
                "simulated_state": localized_state,
                "payment_details": "test",
            })
            self.assertEqual(payment_data["simulated_state"], technical_state)
            self.assertEqual(payment_data["payment_details"], "test")

    def test_technical_demo_states_are_unchanged(self):
        transaction = self.env["payment.transaction"]
        for technical_state in ("done", "pending", "cancel", "error"):
            payment_data = transaction._b2b_normalize_demo_payment_data({
                "simulated_state": technical_state,
            })
            self.assertEqual(payment_data["simulated_state"], technical_state)

    def test_localized_success_confirms_website_order(self):
        partner = self.env["res.partner"].create({
            "name": "Demo Payment Checkout Partner",
            "email": "demo-payment-checkout@example.test",
            "b2b_approved": True,
        })
        product = self.env["product.product"].create({
            "name": "Demo Payment Checkout Product",
            "list_price": 12.0,
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "all",
        })
        website = self.env.ref("website.default_website")
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "partner_invoice_id": partner.id,
            "partner_shipping_id": partner.id,
            "website_id": website.id,
            "order_line": [Command.create({
                "product_id": product.id,
                "product_uom_qty": 1.0,
                "product_uom_id": product.uom_id.id,
                "price_unit": 12.0,
            }), Command.create({
                "product_id": self.env.ref("delivery.product_product_delivery").id,
                "product_uom_qty": 1.0,
                "product_uom_id": self.env.ref("delivery.product_product_delivery").uom_id.id,
                "price_unit": 0.0,
                "is_delivery": True,
            })],
        })
        provider = self.env.ref("payment.payment_provider_demo")
        payment_method = self.env.ref("payment_demo.payment_method_demo")
        transaction = self.env["payment.transaction"].create({
            "provider_id": provider.id,
            "payment_method_id": payment_method.id,
            "reference": "B2B-DEMO-PAYMENT-SUCCESS",
            "amount": order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_id": partner.id,
            "operation": "online_direct",
            "sale_order_ids": [Command.set(order.ids)],
        })

        transaction._process("demo", {
            "reference": transaction.reference,
            "payment_details": "test",
            "simulated_state": "完成",
        })
        self.assertEqual(transaction.state, "done")

        transaction.with_user(self.env.ref("base.public_user")).sudo().action_post_process()
        self.assertEqual(order.state, "sale")
        self.assertTrue(transaction.is_post_processed)
