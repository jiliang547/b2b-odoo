from odoo import Command
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestB2BOrderChange(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.partner = cls.env["res.partner"].create({
            "name": "Paid Order Company",
            "is_company": True,
            "email": "orders@example.test",
            "b2b_approved": True,
        })
        cls.product = cls.env["product.product"].create({
            "name": "Order Change Product",
            "list_price": 100.0,
            "sale_ok": True,
            "is_published": True,
            "b2b_visibility_mode": "all",
        })
        cls.manager = mail_new_test_user(
            cls.env,
            login="order-change-manager",
            groups="b2b_core.group_b2b_manager,sales_team.group_sale_salesman",
        )
        cls.portal_contact = cls.env["res.partner"].create({
            "name": "Paid Order Contact", "parent_id": cls.partner.id,
            "email": "paid-order-contact@example.test",
        })
        cls.portal_user = mail_new_test_user(
            cls.env,
            login="paid-order-customer",
            groups="base.group_portal",
            partner_id=cls.portal_contact.id,
        )

    def _order(self, amount=100.0):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "partner_invoice_id": self.partner.id,
            "partner_shipping_id": self.partner.id,
            "website_id": self.website.id,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom_id": self.product.uom_id.id,
                "price_unit": amount,
            })],
        })
        order.action_confirm()
        self.env["payment.transaction"].create({
            "provider_id": self.env.ref("payment.payment_provider_demo").id,
            "payment_method_id": self.env.ref("payment_demo.payment_method_demo").id,
            "reference": "PAID-%s" % order.id,
            "amount": order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_id": self.partner.id,
            "operation": "online_direct",
            "state": "done",
            "sale_order_ids": [Command.set(order.ids)],
        })
        order.invalidate_recordset(["amount_paid"])
        self.assertEqual(order.amount_paid, order.amount_total)
        return order

    def _proposal(self, order, proposed_price):
        change = self.env["b2b.order.change.request"].create({
            "order_id": order.id,
            "requested_changes": "Please revise the product quantity and final total.",
        })
        change.with_user(self.manager).action_start_review()
        change.revision_order_id.order_line.filtered(
            lambda line: not line.display_type
        ).price_unit = proposed_price
        change.with_user(self.manager).action_send_proposal()
        return change

    def _customer_accept(self, change):
        change.with_user(self.portal_user).action_customer_accept()

    def test_proposal_editor_uses_native_save_and_close_dialog(self):
        order = self._order()
        change = self.env["b2b.order.change.request"].create({
            "order_id": order.id,
            "requested_changes": "Please increase the ordered quantity by one unit.",
        })
        change.with_user(self.manager).action_start_review()
        action = change.with_user(self.manager).action_open_revision()
        self.assertEqual(action["target"], "new")
        self.assertEqual(action["res_id"], change.revision_order_id.id)
        view = self.env.ref("b2b_website.view_order_form_b2b_proposal")
        self.assertEqual(action["views"], [(view.id, "form")])
        self.assertIn('special="save"', view.arch_db)
        self.assertIn('special="cancel"', view.arch_db)
        change.with_user(self.manager).action_send_proposal()
        with self.assertRaises(ValidationError):
            change.with_user(self.manager).action_open_revision()

    def test_pre_payment_review_is_released_by_manager(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "b2b_checkout_mode": "review",
            "b2b_review_state": "pending",
            "require_payment": True,
            "prepayment_percent": 1.0,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom_id": self.product.uom_id.id,
            })],
        })
        order.action_quotation_sent()
        self.assertFalse(order._has_to_be_paid())
        self.assertFalse(order._has_to_be_signed())
        with self.assertRaises(UserError):
            order.action_confirm()
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env["payment.transaction"].create({
                "provider_id": self.env.ref("payment.payment_provider_demo").id,
                "payment_method_id": self.env.ref("payment_demo.payment_method_demo").id,
                "reference": "BLOCKED-REVIEW-%s" % order.id,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
                "partner_id": self.partner.id,
                "operation": "online_direct",
                "sale_order_ids": [Command.set(order.ids)],
            })
        order.with_user(self.manager).action_b2b_mark_review_ready()
        self.assertEqual(order.state, "sent")
        self.assertEqual(order.b2b_review_state, "ready")
        self.assertTrue(order._has_to_be_paid())

    def test_pre_payment_review_closes_during_native_payment_post_processing(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "website_id": self.website.id,
            "b2b_checkout_mode": "review",
            "b2b_review_state": "pending",
            "require_payment": True,
            "prepayment_percent": 1.0,
            "order_line": [Command.create({
                "product_id": self.product.id,
                "product_uom_qty": 1.0,
                "product_uom_id": self.product.uom_id.id,
            })],
        })
        order.action_quotation_sent()
        order.with_user(self.manager).action_b2b_mark_review_ready()
        transaction = self.env["payment.transaction"].create({
            "provider_id": self.env.ref("payment.payment_provider_demo").id,
            "payment_method_id": self.env.ref("payment_demo.payment_method_demo").id,
            "reference": "REVIEW-PAYMENT-%s" % order.id,
            "amount": order.amount_total,
            "currency_id": order.currency_id.id,
            "partner_id": self.partner.id,
            "operation": "online_direct",
            "state": "done",
            "sale_order_ids": [Command.set(order.ids)],
        })

        transaction._post_process()

        self.assertEqual(order.state, "sale")
        self.assertEqual(order.b2b_review_state, "confirmed")
        self.assertTrue(transaction.is_post_processed)

    def test_positive_change_keeps_order_number_and_waits_for_difference(self):
        order = self._order()
        original_name = order.name
        original_total = order.amount_total
        change = self._proposal(order, 125.0)
        expected_delta = change.proposed_amount - original_total
        self.assertEqual(order.amount_total, original_total)
        self._customer_accept(change)

        self.assertEqual(order.name, original_name)
        self.assertEqual(order.b2b_change_revision, 1)
        self.assertEqual(change.state, "balance_due")
        self.assertTrue(order.b2b_change_payment_hold)
        self.assertEqual(change.delta_amount, expected_delta)
        self.assertEqual(order.amount_total - order.amount_paid, expected_delta)
        with self.assertRaises(UserError):
            order.picking_ids.button_validate()

        transaction = self.env["payment.transaction"].create({
            "provider_id": self.env.ref("payment.payment_provider_demo").id,
            "payment_method_id": self.env.ref("payment_demo.payment_method_demo").id,
            "reference": "SUPPLEMENT-%s" % order.id,
            "amount": expected_delta,
            "currency_id": order.currency_id.id,
            "partner_id": self.partner.id,
            "operation": "online_direct",
            "state": "done",
            "sale_order_ids": [Command.set(order.ids)],
        })
        order.invalidate_recordset(["amount_paid"])
        transaction._post_process()
        self.assertEqual(change.state, "completed")
        self.assertFalse(order.b2b_change_payment_hold)
        self.assertEqual(order.amount_paid, order.amount_total)

    def test_equal_change_completes_without_finance(self):
        order = self._order()
        change = self._proposal(order, 100.0)
        self._customer_accept(change)
        self.assertEqual(change.delta_amount, 0.0)
        self.assertEqual(change.state, "completed")
        self.assertFalse(order.b2b_change_payment_hold)

    def test_lower_change_requires_finance_completion(self):
        order = self._order()
        original_total = order.amount_total
        change = self._proposal(order, 80.0)
        expected_delta = change.proposed_amount - original_total
        self._customer_accept(change)
        self.assertEqual(change.state, "finance_review")
        self.assertTrue(order.b2b_change_payment_hold)
        self.assertEqual(change.delta_amount, expected_delta)
        self.assertLess(change.delta_amount, 0)
        with self.assertRaises(ValidationError):
            change.action_finance_complete()
        change.finance_reference = "REFUND-DEMO-001"
        with self.assertRaises(AccessError):
            change.with_user(self.manager).action_finance_complete()
        change.action_finance_complete()
        self.assertEqual(change.state, "completed")
        self.assertFalse(order.b2b_change_payment_hold)

    def test_rejection_does_not_modify_paid_order(self):
        order = self._order()
        original_total = order.amount_total
        change = self._proposal(order, 140.0)
        change.rejection_reason = "Production has already started."
        change.with_user(self.manager).action_reject()
        self.assertEqual(change.state, "rejected")
        self.assertEqual(order.amount_total, original_total)
        self.assertEqual(order.b2b_change_revision, 0)

    def test_sent_revision_is_frozen_and_cannot_be_confirmed(self):
        order = self._order()
        change = self._proposal(order, 125.0)
        revision_line = change.revision_order_id.order_line.filtered(
            lambda line: not line.display_type
        )
        with self.assertRaises(UserError):
            revision_line.price_unit = 130.0
        with self.assertRaises(UserError):
            change.revision_order_id.action_confirm()

    def test_only_one_open_change_is_allowed(self):
        order = self._order()
        self.env["b2b.order.change.request"].create({
            "order_id": order.id,
            "requested_changes": "Please increase the ordered quantity by one unit.",
        })
        with self.assertRaises(ValidationError):
            self.env["b2b.order.change.request"].create({
                "order_id": order.id,
                "requested_changes": "Please make another simultaneous order change.",
            })

    def test_duplicate_requests_in_one_batch_are_rejected(self):
        order = self._order()
        with self.assertRaises(ValidationError):
            self.env["b2b.order.change.request"].create([
                {
                    "order_id": order.id,
                    "requested_changes": "Please increase the ordered quantity by one unit.",
                },
                {
                    "order_id": order.id,
                    "requested_changes": "Please remove one line from this same order.",
                },
            ])

    def test_plain_operator_cannot_prepare_sales_revision(self):
        order = self._order()
        change = self.env["b2b.order.change.request"].create({
            "order_id": order.id,
            "requested_changes": "Please increase the ordered quantity by one unit.",
        })
        operator = mail_new_test_user(
            self.env,
            login="order-change-operator",
            groups="b2b_core.group_b2b_operator",
        )
        with self.assertRaises(AccessError):
            change.with_user(operator).action_start_review()

    def test_finance_cannot_mutate_request_outside_finance_fields(self):
        order = self._order()
        change = self._proposal(order, 80.0)
        self._customer_accept(change)
        finance_user = mail_new_test_user(
            self.env,
            login="order-change-finance",
            groups="account.group_account_invoice",
        )
        change.with_user(finance_user).write({"finance_reference": "REFUND-ALLOWED"})
        with self.assertRaises(AccessError):
            change.with_user(finance_user).write({"state": "completed"})
        with self.assertRaises(AccessError):
            change.with_user(finance_user).write({"requested_changes": "Tampered"})
        change.with_user(finance_user).action_finance_complete()
        self.assertEqual(change.state, "completed")

    def test_finance_refund_must_match_order_and_difference(self):
        order = self._order()
        change = self._proposal(order, 80.0)
        self._customer_accept(change)
        change.finance_reference = "TEST-REFUND"
        source = order.transaction_ids.filtered(lambda tx: tx.state == "done")
        change.refund_transaction_id = source
        with self.assertRaises(ValidationError):
            change.action_finance_complete()
        refund = source.copy({
            "reference": "MATCHED-REFUND-%s" % order.id,
            "operation": "refund", "source_transaction_id": source.id,
            "amount": -10.0, "state": "done",
        })
        change.refund_transaction_id = refund
        with self.assertRaises(ValidationError):
            change.action_finance_complete()
        refund.amount = -abs(change.delta_amount)
        change.action_finance_complete()
        self.assertEqual(change.state, "completed")
        self.assertAlmostEqual(order.amount_paid, order.amount_total)
        refund.sale_order_ids = [Command.set(order.ids)]
        self.assertAlmostEqual(order.amount_paid, order.amount_total)
        next_change = self._proposal(order, 90.0)
        self._customer_accept(next_change)
        self.assertEqual(next_change.state, "balance_due")
        self.assertAlmostEqual(order.amount_total - order.amount_paid, next_change.delta_amount)

    def test_recorded_external_refund_reduces_balance_for_later_changes(self):
        order = self._order()
        change = self._proposal(order, 80.0)
        self._customer_accept(change)
        change.finance_reference = "EXTERNAL-REFUND-TEST"
        change.action_finance_complete()
        self.assertAlmostEqual(order.amount_paid, order.amount_total)
        next_change = self._proposal(order, 90.0)
        self._customer_accept(next_change)
        self.assertAlmostEqual(order.amount_total - order.amount_paid, next_change.delta_amount)

    def test_delivered_order_cannot_open_change_request(self):
        order = self._order()
        order.order_line.filtered(lambda line: not line.display_type).qty_delivered = 1.0
        with self.assertRaises(ValidationError):
            self.env["b2b.order.change.request"].create({
                "order_id": order.id,
                "requested_changes": "Please change this already delivered order.",
            })

    def test_customer_context_cannot_accept_another_company_request(self):
        order = self._order()
        change = self._proposal(order, 110.0)
        other_partner = self.env["res.partner"].create({"name": "Other Company", "is_company": True})
        other_contact = self.env["res.partner"].create({
            "name": "Other Contact", "parent_id": other_partner.id,
        })
        other_user = mail_new_test_user(
            self.env, login="other-order-customer", groups="base.group_portal",
            partner_id=other_contact.id,
        )
        with self.assertRaises(AccessError):
            change.with_user(other_user).action_customer_accept()
