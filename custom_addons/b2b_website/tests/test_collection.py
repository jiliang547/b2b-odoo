import base64
import re

from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, tagged
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch, PropertyMock
from uuid import uuid4
from werkzeug.datastructures import FileStorage
from odoo.addons.b2b_website.controllers.collection import CollectionPortal


class B2BCollectionCommon(AccountTestInvoicingCommon):
    @classmethod
    def get_default_groups(cls):
        return super().get_default_groups() | cls.env.ref('b2b_core.group_b2b_manager') | cls.env.ref('b2b_website.group_b2b_finance')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env['website'].create({'name': 'Collection Test Website', 'company_id': cls.env.company.id})
        cls.customer = cls.env['res.partner'].sudo().create({'name': 'Collection Test Company', 'is_company': True, 'b2b_approved': True})
        cls.product = cls.env['product.product'].create({'name': 'Collection Test Product', 'type': 'consu', 'list_price': 100, 'taxes_id': [Command.clear()], 'b2b_visibility_mode': 'all'})
        cls.journal = cls.company_data['default_journal_bank']
        cls.journal.bank_account_id = cls.env['res.partner.bank'].create({'partner_id': cls.env.company.partner_id.id, 'acc_number': 'TEST-NOT-A-REAL-ACCOUNT', 'company_id': cls.env.company.id})
        cls.journal.inbound_payment_method_line_ids.filtered(lambda l: l.code == 'manual').payment_account_id = cls.company_data['default_account_assets']
        cls.brand = cls.env['b2b.product.brand'].create({'name': 'Collection UAT Brand', 'b2b_collection_journal_ids': [Command.set(cls.journal.ids)]})
        cls.website.b2b_default_account_brand_id = cls.brand
        cls.finance = mail_new_test_user(cls.env, login='collection-finance', groups='b2b_website.group_b2b_finance', company_id=cls.env.company.id, company_ids=[Command.set(cls.env.company.ids)])
        cls.operator = mail_new_test_user(cls.env, login='collection-operator', groups='b2b_core.group_b2b_operator')
        cls.portal_user = mail_new_test_user(cls.env, login='collection-portal', groups='base.group_portal', partner_id=cls.env['res.partner'].create({'name': 'Collection Contact', 'parent_id': cls.customer.id}).id)

    def _order(self, policy='a'):
        self.customer.b2b_collection_policy_id = self.env.ref('b2b_website.collection_policy_' + policy)
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'website_id': self.website.id, 'company_id': self.env.company.id, 'order_line': [Command.create({'product_id': self.product.id, 'product_uom_qty': 1, 'price_unit': 100, 'tax_ids': [Command.clear()]})]})
        order._b2b_start_collection()
        order.action_quotation_sent()
        return order

    def _receipt(self, order, amount):
        payment = self.env['account.payment'].create({'payment_type': 'inbound', 'partner_type': 'customer', 'partner_id': self.customer.id, 'amount': amount, 'currency_id': order.currency_id.id, 'journal_id': self.journal.id, 'payment_method_line_id': self.journal.inbound_payment_method_line_ids.filtered(lambda l: l.code == 'manual')[:1].id})
        payment.action_post()
        receipt = self.env['b2b.bank.receipt'].create({'order_id': order.id, 'declared_amount': amount, 'transfer_reference': 'UAT-%s' % payment.id, 'payment_id': payment.id, 'allocated_amount': amount})
        return receipt


@tagged('post_install', '-at_install')
class TestB2BCollection(B2BCollectionCommon):
    def test_customer_terms_and_quote_status_preserve_payment_rules(self):
        order = self._order('b20')
        self.assertEqual(order._b2b_customer_terms_label(), '20% deposit, 80% before shipment')
        order.write({'b2b_checkout_mode': 'review', 'b2b_review_state': 'pending'})
        self.assertEqual(order._b2b_customer_order_status(), 'Awaiting Final Quote')
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Awaiting Final Quote')
        self.assertFalse(order._has_to_be_paid())
        order.action_b2b_mark_review_ready()
        self.assertEqual(order._b2b_customer_order_status(), 'Ready for Payment')
        self.assertEqual(order.prepayment_percent, 0.2)
        self.assertEqual(order.b2b_payable_now, 20)
        self._receipt(order, 20).action_confirm_receipt()
        self.assertEqual(order._b2b_customer_order_status(), 'Order Confirmed')
        self.assertFalse(order.b2b_shipment_allowed)

    def test_invoice_terms_warning_does_not_change_collection_thresholds(self):
        order = self._order('d')
        self.assertFalse(order.b2b_payment_configuration_warning)
        order.payment_term_id = False
        self.assertIn('no invoice payment terms', order.b2b_payment_configuration_warning)
        self.assertEqual(order.b2b_production_percent, 0)
        self.assertEqual(order.b2b_shipment_percent, 0)
        order.payment_term_id = order.b2b_collection_policy_id.payment_term_id
        self.assertFalse(order.b2b_payment_configuration_warning)

    def test_invoice_schedule_is_independent_of_deposit_clearance(self):
        order = self._order('b30')
        order.payment_term_id = self.env.ref('b2b_website.collection_net30')
        self.assertFalse(order.b2b_payment_configuration_warning)
        self.assertEqual(order.b2b_production_percent, 30)
        self.assertEqual(order.b2b_shipment_percent, 100)
        self.assertEqual(order.prepayment_percent, 0.3)
        order.prepayment_percent = 0.2
        self.assertIn('online prepayment', order.b2b_payment_configuration_warning)
        self.assertEqual(order.b2b_production_percent, 30)
        order.prepayment_percent = 0.3
        self.assertFalse(order.b2b_payment_configuration_warning)

    def test_portal_deposit_status_and_balance_request(self):
        order = self._order('b20')
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Deposit Payment Required')
        receipt = self._receipt(order, 20)
        self.assertTrue(order._b2b_portal_payment_summary()['pending'])
        self.assertEqual(order.b2b_net_received, 0)
        receipt.action_confirm_receipt()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Deposit Received · Balance Outstanding')
        self.assertFalse(order._b2b_portal_payment_summary()['requested'])
        self.assertFalse(order.b2b_shipment_allowed)
        # A change hold blocks fulfilment, not a required deposit top-up.
        order.sudo().write({'b2b_change_payment_hold': True})
        order.order_line.price_unit = 200
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Deposit Payment Required')
        order.order_line.price_unit = 100
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Order Change Under Review')
        with self.assertRaises(UserError):
            order.action_b2b_request_balance_payment()
        order.sudo().write({'b2b_change_payment_hold': False})
        with self.assertRaises(AccessError):
            order.with_user(self.portal_user).action_b2b_request_balance_payment()
        with self.assertRaises(AccessError):
            order.with_user(self.operator).write({'b2b_balance_payment_requested': True})
        order.action_b2b_request_balance_payment()
        self.assertTrue(order._b2b_portal_payment_summary()['requested'])
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Balance Payment Required')
        messages = order.message_ids
        order.action_b2b_request_balance_payment()
        self.assertEqual(order.message_ids, messages)
        self._receipt(order, 80).action_confirm_receipt()
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Fully Paid')
        self.assertFalse(order._b2b_portal_payment_summary()['requested'])
        with self.assertRaises(UserError):
            order.action_b2b_request_balance_payment()

    def test_portal_credit_cancel_and_unconfirmed_request(self):
        order = self._order('b20')
        with self.assertRaises(UserError):
            order.action_b2b_request_balance_payment()
        order._action_cancel()
        self.assertEqual(order._b2b_portal_payment_summary()['label'], 'Order Cancelled')
        credit = self._order('d')
        credit.action_confirm()
        self.assertEqual(credit._b2b_portal_payment_summary()['label'], 'Balance Outstanding')
        self.assertFalse(credit._b2b_portal_payment_summary()['requested'])

    def test_native_demo_confirmation_does_not_activate_collection(self):
        order = self.env['sale.order'].create({
            'partner_id': self.customer.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': self.product.id, 'price_unit': 100})],
        })
        # Odoo.sh may force demos after registry initialization.
        with patch.object(self.env.registry, '_init', False):
            order.sudo().with_context(install_demo=True).action_confirm()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.b2b_collection_active)

    def test_demo_context_cannot_bypass_real_collection(self):
        order = self._order('a')
        with patch.object(self.env.registry, '_init', False):
            self.assertFalse(order.with_user(self.operator).with_context(install_demo=True)._b2b_loading_native_demo())
            with self.assertRaises(UserError), self.cr.savepoint():
                order.sudo().with_context(install_demo=True).action_confirm()
        with patch.object(self.env.registry, '_init', True):
            self.assertFalse(order.with_user(self.operator).with_context(install_demo=True)._b2b_loading_native_demo())
            # Even a loader context must not release an already active order.
            with self.assertRaises(UserError), self.cr.savepoint():
                order.sudo().with_context(install_demo=True).action_confirm()
            with self.assertRaises(UserError), self.cr.savepoint():
                order.sudo().with_context(install_demo=True).write({'state': 'sale'})

    def test_duplicate_uses_new_order_payment_reference(self):
        source = self._order('b30')
        duplicate = source.copy()
        self.assertIn('Payment reference: %s' % duplicate.name, duplicate.b2b_bank_instructions)
        self.assertNotIn('Payment reference: %s' % source.name, duplicate.b2b_bank_instructions)
        self.assertIn('Payment reference: %s' % duplicate.name, duplicate.b2b_pi_bank_instructions)
        self.assertNotIn('Payment reference: %s' % source.name, duplicate.b2b_pi_bank_instructions)

    def test_pi_has_complete_native_bank_details_without_expanding_portal_snapshot(self):
        self.env.company.partner_id.write({
            'street': 'RM 3 Unit P, Kaiser Estate Phase 3',
            'city': 'Hong Kong',
            'country_id': self.env.ref('base.hk').id,
        })
        bank = self.env['res.bank'].create({
            'name': 'China Merchants Bank Co., Limited (Hong Kong Branch)',
            'bic': 'CMBCHKHH',
            'street': '31/F, Three Exchange Square',
            'street2': '8 Connaught Place',
            'city': 'Central',
            'country': self.env.ref('base.hk').id,
        })
        self.journal.bank_account_id.write({
            'acc_holder_name': 'Lucky Tone Technology Co., Limited',
            'bank_id': bank.id,
            'clearing_number': '238',
            'note': 'Bank Code: 238\nBranch Code: 860',
        })
        order = self._order('a')
        self.assertNotIn('Beneficiary Address:', order.b2b_bank_instructions)
        self.assertNotIn('Branch Code: 860', order.b2b_bank_instructions)
        self.assertIn('USD Account No.: TEST-NOT-A-REAL-ACCOUNT', order.b2b_pi_bank_instructions)
        self.assertIn('SWIFT/BIC: CMBCHKHH', order.b2b_pi_bank_instructions)
        self.assertIn('Beneficiary Address:', order.b2b_pi_bank_instructions)
        self.assertIn('RM 3 Unit P, Kaiser Estate Phase 3', order.b2b_pi_bank_instructions)
        self.assertIn('Bank Address: 31/F, Three Exchange Square, 8 Connaught Place, Central', order.b2b_pi_bank_instructions)
        self.assertIn('Clearing Number: 238', order.b2b_pi_bank_instructions)
        self.assertIn('Branch Code: 860', order.b2b_pi_bank_instructions)
        content, _ = self.env['ir.actions.report']._render_qweb_html(
            'b2b_website.action_report_collection_pi', order.ids)
        self.assertIn(b'31/F, Three Exchange Square', content)
        self.assertIn(b'Branch Code: 860', content)

    def test_online_deposit_refund_requires_actual_evidence(self):
        order = self._order('b30')
        provider = self.env.ref('payment.payment_provider_demo').sudo().copy({'company_id': self.env.company.id})
        payment = self.env['payment.transaction'].create({
            'provider_id': provider.id, 'payment_method_id': self.env.ref('payment_demo.payment_method_demo').id,
            'reference': 'COLLECTION-ONLINE-%s' % order.id, 'amount': 30,
            'currency_id': order.currency_id.id, 'partner_id': self.customer.id,
            'operation': 'online_direct', 'state': 'done', 'sale_order_ids': [Command.set(order.ids)],
        })
        order.action_confirm()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'Reduce to 20.'})
        change.action_start_review()
        change.revision_order_id.order_line.price_unit = 20
        change.action_send_proposal()
        change.with_user(self.portal_user).action_customer_accept()
        change.with_user(self.finance).finance_reference = 'TEXT-IS-NOT-A-REFUND'
        with self.assertRaises(ValidationError):
            change.with_user(self.finance).action_finance_complete()
        self.assertEqual(change.state, 'finance_review')
        self.assertEqual(order._b2b_received_amount(), 30)
        self.assertFalse(order._b2b_can_ship())
        refund = self.env['payment.transaction'].create({
            'provider_id': provider.id, 'payment_method_id': payment.payment_method_id.id,
            'reference': 'COLLECTION-REFUND-%s' % order.id, 'amount': -10,
            'currency_id': order.currency_id.id, 'partner_id': self.customer.id,
            'operation': 'refund', 'state': 'done', 'source_transaction_id': payment.id,
        })
        change.with_user(self.finance).refund_transaction_id = refund
        change.with_user(self.finance).action_finance_complete()
        self.assertEqual(order._b2b_received_amount(), 20)
        with self.assertRaises(ValidationError):
            change.with_user(self.finance).refund_transaction_id = False

    def test_historical_completion_without_payment_does_not_reduce_receipts(self):
        order = self._order('b30')
        self._receipt(order, 30).action_confirm_receipt()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'Legacy invalid completion'})
        change.sudo().write({'state': 'completed', 'delta_amount': -80, 'refund_amount': 10})
        self.assertEqual(order._b2b_received_amount(), 30)
        self.assertFalse(order._b2b_can_ship())

    def test_manager_without_accounting_can_apply_collection_terms(self):
        manager = mail_new_test_user(self.env, login='collection-manager-no-accounting',
                                    groups='b2b_core.group_b2b_manager')
        self.assertFalse(manager.has_group('account.group_account_invoice'))
        order = self._order('b30').with_user(manager)
        order.write({'b2b_configuration_reason': 'UAT switch to full prepayment',
                     'b2b_collection_policy_id': self.env.ref('b2b_website.collection_policy_a').id})
        order.action_b2b_refresh_collection()
        self.assertEqual(order.b2b_production_percent, 100)
        self.assertFalse(order.b2b_production_allowed)

    def test_invoice_uses_order_bank_and_keeps_collection_orders_separate(self):
        order = self._order('d')
        self.assertEqual(order._prepare_invoice()['partner_bank_id'], self.journal.bank_account_id.id)
        self.assertIn('invoice_origin', order._get_invoice_grouping_keys())
        order.action_confirm()
        order.order_line.qty_delivered = 1
        invoice = order._create_invoices()
        self.assertEqual(invoice.partner_bank_id, self.journal.bank_account_id)
        self.assertEqual(invoice.invoice_payment_term_id, order.payment_term_id)

    def test_a_requires_full_receipt_not_evidence(self):
        order = self._order()
        receipt = self._receipt(order, 100)
        self.assertFalse(order.b2b_production_allowed)
        with self.assertRaises(UserError):
            order.action_confirm()
        receipt.with_user(self.finance).action_confirm_receipt()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.amount_paid, 100)
        self.assertTrue(order.b2b_shipment_allowed)
        receipt.with_user(self.finance).action_confirm_receipt()
        self.assertEqual(order.amount_paid, 100)

    def test_b_partial_deposit_then_balance(self):
        order = self._order('b30')
        self._receipt(order, 20).action_confirm_receipt()
        self.assertEqual(order.state, 'sent')
        self._receipt(order, 10).action_confirm_receipt()
        self.assertEqual(order.state, 'sale')
        self.assertFalse(order.b2b_shipment_allowed)
        self._receipt(order, 70).action_confirm_receipt()
        self.assertTrue(order.b2b_shipment_allowed)
        self.assertEqual(order.b2b_balance, 0)

    def test_c_can_produce_without_receipt_but_not_ship(self):
        order = self._order('c')
        order.action_confirm()
        self.assertFalse(order.b2b_shipment_allowed)
        picking = order.picking_ids[:1]
        self.assertTrue(picking)
        with self.assertRaises(UserError):
            picking._b2b_check_collection_release()

    def test_d_native_terms_and_credit_release(self):
        order = self._order('d')
        self.assertEqual(order.payment_term_id, self.env.ref('b2b_website.collection_net30'))
        order.action_confirm()
        self.assertTrue(order.b2b_shipment_allowed)
        self.assertEqual(order.b2b_balance, 100)
        self.assertEqual(order.b2b_payable_now, 0)

    def test_e_threshold_validation(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['b2b.collection.policy'].create({'name': 'Invalid', 'category': 'E', 'production_percent': 80, 'shipment_percent': 20})

    def test_d_delivery_creates_native_receivable(self):
        order = self._order('d')
        order.action_confirm()
        for move in order.picking_ids.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        order.picking_ids._action_done()
        self.assertTrue(order.invoice_ids)
        self.assertEqual(order.invoice_ids.state, 'posted')
        self.assertEqual(order.invoice_ids.amount_residual, 100)
        self.assertEqual(order.invoice_ids.invoice_payment_term_id, self.env.ref('b2b_website.collection_net30'))

    def test_native_receipt_reversal_reblocks_shipment(self):
        order = self._order()
        receipt = self._receipt(order, 100)
        receipt.action_confirm_receipt()
        receipt.payment_id.action_draft()
        self.assertEqual(order.b2b_net_received, 0)
        self.assertFalse(order.b2b_shipment_allowed)

    def test_configuration_change_updates_snapshot_atomically(self):
        order = self._order()
        order.write({'b2b_configuration_reason': 'Approved deposit terms', 'b2b_collection_policy_id': self.env.ref('b2b_website.collection_policy_b30').id})
        self.assertEqual(order.b2b_production_percent, 30)
        self.assertEqual(order.prepayment_percent, .3)

    def test_partial_paid_decrease_reduces_balance_not_deposit(self):
        order = self._order('b30')
        self._receipt(order, 30).action_confirm_receipt()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'Reduce the agreed product price.'})
        change.action_start_review()
        change.revision_order_id.order_line.price_unit = 80
        change.action_send_proposal()
        change.with_user(self.portal_user).action_customer_accept()
        self.assertEqual(change.state, 'completed')
        self.assertEqual(change.refund_amount, 0)
        self.assertEqual(order.b2b_net_received, 30)
        self.assertEqual(order.b2b_balance, 50)

    def test_bank_refund_uses_actual_excess_and_native_outbound_payment(self):
        order = self._order('b30')
        self._receipt(order, 30).action_confirm_receipt()
        change = self.env['b2b.order.change.request'].create({'order_id': order.id, 'requested_changes': 'Reduce order to 20.'})
        change.action_start_review()
        change.revision_order_id.order_line.price_unit = 20
        change.action_send_proposal()
        change.with_user(self.portal_user).action_customer_accept()
        self.assertEqual(change.refund_amount, 10)
        self.assertEqual(change.state, 'finance_review')
        change.with_user(self.finance).finance_reference = 'UAT-NATIVE-REFUND'
        with self.assertRaises(ValidationError):
            change.with_user(self.finance).action_finance_complete()
        method = self.journal.outbound_payment_method_line_ids.filtered(lambda line: line.code == 'manual')[:1]
        method.payment_account_id = self.company_data['default_account_assets']
        refund = self.env['account.payment'].create({'payment_type': 'outbound', 'partner_type': 'customer', 'partner_id': self.customer.id, 'amount': 10, 'currency_id': order.currency_id.id, 'journal_id': self.journal.id, 'payment_method_line_id': method.id})
        refund.action_post()
        change.with_user(self.finance).refund_payment_id = refund
        change.with_user(self.finance).action_finance_complete()
        self.assertEqual(change.state, 'completed')
        self.assertEqual(order.b2b_net_received, 20)
        self.assertEqual(order.b2b_balance, 0)

    def test_confirmed_order_bank_change_preserves_payment_thresholds(self):
        order = self._order('b30')
        self._receipt(order, 30).action_confirm_receipt()
        brand = self.env['b2b.product.brand'].create({'name': 'Another approved brand', 'b2b_collection_journal_ids': [Command.set(self.journal.ids)]})
        order.write({'b2b_brand_id': brand.id, 'b2b_configuration_reason': 'Approved brand reassignment'})
        self.assertEqual(order.b2b_brand_id, brand)
        self.assertEqual(order.b2b_receiving_journal_id, self.journal)
        self.assertEqual(order.b2b_production_percent, 30)
        with self.assertRaises(UserError):
            order.write({'b2b_collection_policy_id': self.env.ref('b2b_website.collection_policy_c').id})

    def test_pi_html_reuses_native_order_lines_and_bank_snapshot(self):
        order = self._order('b30')
        self.assertEqual(self.env.ref('b2b_website.action_report_collection_pi').paperformat_id.orientation, 'Portrait')
        content, _ = self.env['ir.actions.report']._render_qweb_html('b2b_website.action_report_collection_pi', order.ids)
        self.assertIn(b'PRO-FORMA INVOICE', content)
        self.assertIn(b'TEST-NOT-A-REAL-ACCOUNT', content)
        self.assertIn(b'Collection Test Product', content)

    def test_portal_has_no_direct_receipt_access(self):
        receipt = self._receipt(self._order(), 100)
        with self.assertRaises(AccessError):
            receipt.with_user(self.portal_user).read(['payment_id'])

    def test_collection_portal_template_compiles(self):
        self.env['ir.qweb']._compile('b2b_website.portal_collection')

    def test_upload_controller_records_evidence_without_credit(self):
        order = self._order()
        portal = CollectionPortal()
        upload = FileStorage(stream=BytesIO(b'%PDF-1.4\n% LOCAL TEST EVIDENCE'), filename='test-proof.pdf')
        fake = SimpleNamespace(env=self.env(user=self.portal_user), httprequest=SimpleNamespace(files={'proof': upload}))
        with patch.object(CollectionPortal, 'env', new_callable=PropertyMock, return_value=self.env), patch('odoo.addons.b2b_website.controllers.collection.request', fake), patch.object(portal, '_render', return_value='submitted'):
            self.assertEqual(portal.upload_proof(order.id, amount='100', transfer_date=str(fields.Date.today()), reference='UPLOAD-UAT', submission_key=str(uuid4())).get_data(as_text=True), 'submitted')
        self.assertEqual(len(order.b2b_receipt_ids), 1)
        self.assertEqual(order.b2b_receipt_ids.state, 'submitted')
        self.assertTrue(order.b2b_receipt_ids.attachment_ids)
        self.assertEqual(order.b2b_net_received, 0)

    def test_upload_rejects_invalid_file_and_other_company(self):
        order = self._order()
        portal = CollectionPortal()
        upload = FileStorage(stream=BytesIO(b'<script>invalid evidence</script>'), filename='fake.pdf')
        fake = SimpleNamespace(env=self.env(user=self.portal_user), httprequest=SimpleNamespace(files={'proof': upload}))
        with patch.object(CollectionPortal, 'env', new_callable=PropertyMock, return_value=self.env), patch('odoo.addons.b2b_website.controllers.collection.request', fake), patch.object(portal, '_render', return_value='error') as render:
            portal.upload_proof(order.id, amount='100', transfer_date=str(fields.Date.today()), reference='BAD-UAT', submission_key=str(uuid4()))
            self.assertIn('Upload a PDF', render.call_args.kwargs['error'])
        self.assertFalse(order.b2b_receipt_ids)
        from werkzeug.exceptions import NotFound
        other = self.env['res.partner'].create({'name': 'Different customer'})
        order.partner_id = other
        with patch('odoo.addons.b2b_website.controllers.collection.request', fake), self.assertRaises(NotFound):
            portal._order(order.id)

    def test_finance_can_map_accounts_but_not_edit_brand_content(self):
        self.brand.with_user(self.finance).write({'b2b_collection_journal_ids': [Command.set(self.journal.ids)]})
        with self.assertRaises(AccessError):
            self.brand.with_user(self.finance).write({'name': 'Unauthorized rename'})

    def test_native_credit_limit_includes_other_confirmed_orders(self):
        self.env.company.account_use_credit_limit = True
        self.customer.credit_limit = 150
        self.product.invoice_policy = 'delivery'
        first = self._order('d')
        first.action_confirm()
        second = self._order('d')
        with self.assertRaises(UserError):
            second.action_confirm()

    def test_pi_never_rewrites_issued_pdf(self):
        order = self._order()
        with patch.object(type(self.env['ir.actions.report']), '_render_qweb_pdf', return_value=(b'%PDF-1.4 UAT', 'pdf')):
            first = order.sudo()._b2b_issue_pi()
            self.assertEqual(order.sudo()._b2b_issue_pi(), first)
            order.order_line.price_unit = 120
            second = order.sudo()._b2b_issue_pi()
            self.assertEqual(second.revision, first.revision + 1)
            order.sudo().write({'b2b_pi_bank_instructions': order.b2b_pi_bank_instructions + '\nBranch Code: 860'})
            third = order.sudo()._b2b_issue_pi()
            self.assertEqual(third.revision, second.revision + 1)
        with self.assertRaises(UserError):
            first.write({'digest': 'tampered'})

    def test_snapshot_does_not_follow_customer_changes(self):
        order = self._order('b20')
        self.customer.b2b_collection_policy_id = self.env.ref('b2b_website.collection_policy_d')
        self.assertEqual(order.b2b_production_percent, 20)
        self.assertEqual(order.b2b_brand_id, self.brand)

    def test_operator_cannot_confirm_or_change_terms(self):
        order = self._order()
        receipt = self._receipt(order, 100)
        with self.assertRaises(AccessError):
            receipt.with_user(self.operator).action_confirm_receipt()
        with self.assertRaises(AccessError):
            self.customer.with_user(self.operator).write({'b2b_collection_policy_id': self.env.ref('b2b_website.collection_policy_d').id})

    def test_duplicate_payment_cannot_be_overallocated(self):
        order = self._order('b30')
        receipt = self._receipt(order, 30)
        receipt.action_confirm_receipt()
        duplicate = self.env['b2b.bank.receipt'].create({'order_id': order.id, 'declared_amount': 30, 'transfer_reference': 'duplicate', 'payment_id': receipt.payment_id.id, 'allocated_amount': 30})
        with self.assertRaises(ValidationError):
            duplicate.action_confirm_receipt()

    def test_wrong_customer_payment_rejected(self):
        order = self._order()
        receipt = self._receipt(order, 100)
        receipt.payment_id.action_draft()
        receipt.payment_id.partner_id = self.env['res.partner'].create({'name': 'Other payer'})
        receipt.payment_id.action_post()
        with self.assertRaises(ValidationError):
            receipt.action_confirm_receipt()

    def test_returned_evidence_not_counted(self):
        order = self._order()
        receipt = self._receipt(order, 100)
        receipt.review_note = 'Please provide the bank reference.'
        receipt.action_return()
        self.assertEqual(order.b2b_net_received, 0)

    def test_authorized_online_payment_not_received(self):
        order = self._order()
        provider = self.env.ref('payment.payment_provider_demo').sudo().copy({'company_id': self.env.company.id})
        self.env['payment.transaction'].create({'provider_id': provider.id, 'payment_method_id': self.env.ref('payment_demo.payment_method_demo').id, 'reference': 'COLLECTION-AUTH-%s' % order.id, 'amount': 100, 'currency_id': order.currency_id.id, 'partner_id': self.customer.id, 'operation': 'online_direct', 'state': 'authorized', 'sale_order_ids': [Command.set(order.ids)]})
        self.assertEqual(order.b2b_net_received, 0)
        self.assertFalse(order._is_confirmation_amount_reached())


@tagged('post_install', '-at_install')
class TestB2BCollectionHttp(B2BCollectionCommon, HttpCase):
    def test_authenticated_multipart_upload_and_repeat_submission(self):
        """Exercise the real HTTP/CSRF/file parser, not a mocked request."""
        order = self._order()
        self.authenticate(self.portal_user.login, self.portal_user.login)
        page = self.url_open('/my/orders/%s/collection' % order.id)
        self.assertEqual(page.status_code, 200)
        payload = {name: re.search(r'name="%s" value="([^"]+)"' % name, page.text).group(1)
                   for name in ('csrf_token', 'submission_key')}
        payload.update(amount='100', transfer_date=str(fields.Date.today()), reference='HTTP-UPLOAD-UAT')
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1cAAAAASUVORK5CYII=')
        url = '/my/orders/%s/collection/proof' % order.id
        response = self.url_open(url, data=payload, files={'proof': ('receipt.png', png, 'image/png')})
        self.assertEqual(response.status_code, 200)
        order.invalidate_recordset()
        receipt = order.b2b_receipt_ids
        self.assertEqual(len(receipt), 1)
        self.assertEqual(receipt.state, 'submitted')
        self.assertEqual(order.b2b_net_received, 0)
        self.assertFalse(receipt.attachment_ids.public)
        downloaded = self.url_open('%s/%s/%s' % (url, receipt.id, receipt.attachment_ids.id))
        self.assertEqual(downloaded.content, png)
        repeated = self.url_open(url, data=payload, files={'proof': ('receipt.png', png, 'image/png')})
        self.assertEqual(repeated.status_code, 200)
        order.invalidate_recordset()
        self.assertEqual(len(order.b2b_receipt_ids), 1)
