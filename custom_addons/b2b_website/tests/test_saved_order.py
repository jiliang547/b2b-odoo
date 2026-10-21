from types import SimpleNamespace
from unittest.mock import patch, PropertyMock
from uuid import uuid4
from io import BytesIO

from lxml import html
from werkzeug.datastructures import FileStorage
from werkzeug.utils import redirect

from odoo import Command, fields
from odoo.http import root
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.addons.website_sale.tests.common import MockRequest
from odoo.addons.sale.controllers.portal import PaymentPortal as NativePaymentPortal
from ..controllers.portal import PartnerHubPortal
from ..controllers.collection import CollectionPortal
from ..controllers.collection_payment import CollectionPaymentPortal
from .test_collection import B2BCollectionCommon, valid_png


class SavedOrderCommon(B2BCollectionCommon):
    def _saved(self, policy='b20'):
        self.product.is_published = True
        self.customer.b2b_collection_policy_id = self.env.ref('b2b_website.collection_policy_' + policy)
        order = self.env['sale.order'].create({
            'partner_id': self.portal_user.partner_id.id, 'website_id': self.website.id,
            'order_line': [Command.create({'product_id': self.product.id,
                'product_uom_qty': 1, 'price_unit': 100, 'tax_ids': [Command.clear()]})],
        })
        order._b2b_save_for_later()
        return order

    def _add_freight(self, order, amount=20):
        freight = self.env['product.product'].create({'name': 'Saved order freight',
            'type': 'service', 'taxes_id': [Command.clear()]})
        self.website.b2b_freight_product_id = freight
        return self.env['sale.order.line'].create({'order_id': order.id,
            'product_id': freight.id, 'product_uom_qty': 1, 'price_unit': amount,
            'tax_ids': [Command.clear()]})


@tagged('post_install', '-at_install')
class TestSavedOrders(SavedOrderCommon):
    def test_save_is_payable_native_unconfirmed_order_not_a_review(self):
        order = self._saved()
        self.assertEqual((order.state, order.b2b_checkout_mode, order.b2b_review_state), ('sent', 'pay_later', 'none'))
        self.assertTrue(order.b2b_submitted_at)
        self.assertEqual(order.type_name, 'Order')
        self.assertEqual(order._b2b_customer_order_status(), 'Awaiting Payment')
        self.assertTrue(order._has_to_be_paid())
        self.assertFalse(order._has_to_be_signed())
        self.assertEqual(order.b2b_production_percent, 20)
        self.assertEqual(order.prepayment_percent, .2)
        self.assertFalse(order.b2b_erp_job_ids)
        self.assertFalse(order.b2b_pi_ids)
        with self.assertRaises(UserError):
            order.action_confirm()

    def test_saved_orders_are_in_orders_not_quotes_without_any_transaction(self):
        order = self._saved()
        env = self.env(user=self.portal_user)
        with MockRequest(env, website=self.website.with_env(env)):
            portal = PartnerHubPortal()
            self.assertIn(order, self.env['sale.order'].search(portal._prepare_orders_domain(self.portal_user.partner_id)))
            self.assertNotIn(order, self.env['sale.order'].search(portal._prepare_quotations_domain(self.portal_user.partner_id)))

    def test_native_report_calls_saved_record_order_but_keeps_normal_quote(self):
        order = self._saved()
        report = self.env['ir.actions.report']
        saved_html, _ = report._render_qweb_html('sale.action_report_saleorder', order.ids)
        text = ' '.join(html.fromstring(saved_html).text_content().split())
        self.assertIn('Order #', text)
        self.assertIn('Order Date', text)
        self.assertNotIn('Quotation #', text)
        self.assertNotIn('Quotation Date', text)
        normal = self._order()
        normal_html, _ = report._render_qweb_html('sale.action_report_saleorder', normal.ids)
        self.assertIn('Quotation #', ' '.join(html.fromstring(normal_html).text_content().split()))

    def test_freight_updates_same_order_and_invalidates_old_payment_token(self):
        order = self._saved()
        name, token = order.name, order._b2b_quote_token()
        freight = self._add_freight(order)
        self.assertTrue(freight.is_delivery)
        self.assertEqual(order.name, name)
        self.assertEqual(order.amount_total, 120)
        self.assertEqual(order.b2b_payable_now, 24)
        self.assertNotEqual(order._b2b_quote_token(), token)
        with MockRequest(self.env, website=self.website), \
                patch.object(CollectionPaymentPortal, '_document_check_access', return_value=order), \
                patch.object(NativePaymentPortal, 'portal_order_transaction') as native:
            with self.assertRaisesRegex(ValidationError, 'has changed'):
                CollectionPaymentPortal().portal_order_transaction.__wrapped__(
                    CollectionPaymentPortal(), order.id, 'native-token', b2b_quote_token=token)
            native.assert_not_called()
        self.assertFalse(order.b2b_erp_job_ids)

    def test_bank_receipts_confirm_only_at_current_deposit_threshold(self):
        order = self._saved()
        self._add_freight(order)
        first = self._receipt(order, 10)
        first.action_confirm_receipt()
        self.assertEqual(order.state, 'sent')
        self.assertEqual(order.b2b_net_received, 10)
        self.assertEqual(order.b2b_payable_now, 14)
        with self.assertRaisesRegex(UserError, 'already received funds'):
            order.order_line[0].price_unit = 101
        self._receipt(order, 14).action_confirm_receipt()
        self.assertEqual(order.state, 'sale')
        self.assertEqual(order.b2b_net_received, 24)
        self.assertEqual(order.b2b_balance, 96)
        self.assertEqual(order._b2b_customer_order_status(), 'Order Confirmed')

    def test_pending_bank_evidence_blocks_edits_and_online_duplicate(self):
        order = self._saved()
        self.env['b2b.bank.receipt'].create({'order_id': order.id,
            'declared_amount': 20, 'transfer_reference': 'Awaiting bank verification'})
        self.assertFalse(order._has_to_be_paid())
        with self.assertRaisesRegex(UserError, 'Finance must review'):
            self._add_freight(order)
        with self.assertRaisesRegex(ValidationError, 'reviewing your bank payment'), self.cr.savepoint():
            self._online_transaction(order, 20)
        self.assertEqual(order.b2b_net_received, 0)
        self.assertFalse(order.b2b_erp_job_ids)

    def test_pending_online_payment_blocks_operator_edits(self):
        order = self._saved()
        self._online_transaction(order, 20)
        self.assertEqual(order._b2b_customer_order_status(), 'Payment Processing')
        with self.assertRaises(UserError):
            self._add_freight(order)

    def test_returned_evidence_does_not_permanently_lock_unpaid_order(self):
        order = self._saved()
        evidence = self.env['b2b.bank.receipt'].create({'order_id': order.id,
            'declared_amount': 20, 'transfer_reference': 'Need another proof',
            'review_note': 'Please submit a readable bank proof.'})
        evidence.action_return()
        self.assertFalse(order._b2b_pending_bank_evidence())
        self.assertTrue(order._has_to_be_paid())
        self._add_freight(order)
        self.assertEqual(order.amount_total, 120)
        self.assertEqual(order.b2b_net_received, 0)

    def test_native_draft_paypal_attempt_is_not_an_edit_or_duplicate_window(self):
        order = self._saved()
        self._online_transaction(order, 20, state='draft')
        self.assertFalse(order._has_to_be_paid())
        with self.assertRaises(UserError):
            self._add_freight(order)
        with self.assertRaisesRegex(ValidationError, 'Another payment'), self.cr.savepoint():
            self._online_transaction(order, 20, state='draft', reference='DUPLICATE-SAVED')

    def test_credit_terms_save_never_confirms_or_dispatches_automatically(self):
        for policy in ('c', 'd'):
            with self.subTest(policy=policy):
                order = self._saved(policy)
                self.assertEqual(order.state, 'sent')
                self.assertEqual(order.b2b_production_percent, 0)
                self.assertTrue(order._has_to_be_paid())
                self.assertFalse(order.b2b_erp_job_ids)

    def test_old_reviews_require_explicit_manager_conversion(self):
        order = self._order('b30')
        order.write({'b2b_checkout_mode': 'review', 'b2b_review_state': 'pending',
                     'prepayment_percent': 1.0})
        self.assertFalse(order._has_to_be_paid())
        with self.assertRaises(AccessError):
            order.with_user(self.operator).action_b2b_allow_saved_order_payment()
        order.action_b2b_allow_saved_order_payment()
        self.assertEqual(order.b2b_checkout_mode, 'pay_later')
        self.assertTrue(order._has_to_be_paid())
        self.assertEqual(order.prepayment_percent, .3)
        self.assertFalse(order.b2b_erp_job_ids)

    def test_old_bank_page_cannot_submit_evidence_after_order_change(self):
        order = self._saved()
        token = order._b2b_quote_token()
        self._add_freight(order)
        portal = CollectionPortal()
        upload = FileStorage(stream=BytesIO(valid_png()), filename='test-proof.png')
        fake = SimpleNamespace(env=self.env(user=self.portal_user), session={}, redirect=redirect,
                               httprequest=SimpleNamespace(files={'proof': upload}))
        with patch.object(CollectionPortal, 'env', new_callable=PropertyMock, return_value=self.env), \
                patch('odoo.addons.b2b_website.controllers.collection.request', fake), \
                patch.object(portal, '_render', return_value='safe error') as render:
            portal.upload_proof(order.id, amount='20', transfer_date=str(fields.Date.today()),
                reference='STALE-ORDER', submission_key=str(uuid4()), b2b_quote_token=token)
            self.assertIn('has changed', render.call_args.kwargs['error'])
        self.assertFalse(order.b2b_receipt_ids)


@tagged('post_install', '-at_install')
class TestSavedOrdersHttp(SavedOrderCommon, HttpCase):
    def test_saved_order_detail_and_bank_page_use_live_amount_and_order_copy(self):
        order = self._saved()
        self._add_freight(order)
        # An isolated database may have no enabled online provider. Supply the
        # same optional native Demo fixture used by the collection regressions.
        # Merely render the native form; no provider is contacted by this test.
        self.env['payment.provider'].search([('company_id', '=', self.env.company.id)]).state = 'disabled'
        provider = self.env.ref('payment.payment_provider_demo').sudo().copy({
            'name': 'Saved order HTTP Demo', 'company_id': self.env.company.id,
            'website_id': False, 'is_published': True, 'journal_id': self.journal.id,
            'payment_method_ids': [Command.set(self.env.ref('payment.payment_method_card').ids)]})
        self.cr.execute("UPDATE payment_provider SET code = 'demo', state = 'test' WHERE id = %s", [provider.id])
        provider.invalidate_recordset(['code', 'state'])
        # Disabling the last native provider also archives its payment methods.
        self.env.ref('payment.payment_method_card').sudo().active = True
        self.authenticate(self.portal_user.login, 'Portal-Test-2026!')
        response = self.url_open('/my/orders/%s' % order.id)
        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.text)
        self.assertIn('Order - ' + order.name, ' '.join(page.text_content().split()))
        self.assertIn('Awaiting Payment', page.text_content())
        self.assertNotIn('Awaiting Final Quote', page.text_content())
        self.assertEqual(page.xpath("//a[@id='o_sale_portal_paynow']")[0].text_content().strip(), 'Pay by Paypal')
        self.assertTrue(page.xpath("//a[normalize-space(.)='Pay by Bank (TT)']"))
        self.assertIn('Pay by Paypal', page.xpath("//div[@name='sale_order_actions']")[0].text_content())
        payment_forms = page.xpath("//form[@id='o_payment_form']")
        self.assertTrue(payment_forms, ' '.join(page.xpath("//div[@id='payment_method']")[0].text_content().split()))
        self.assertEqual(float(payment_forms[0].get('data-amount')), 24)
        response = self.url_open('/my/orders/%s/collection' % order.id)
        page = html.fromstring(response.text)
        self.assertTrue(page.xpath("//form[contains(@action, '/collection/proof')]"))
        self.assertEqual(page.xpath("//input[@name='b2b_quote_token']")[0].get('value'), order._b2b_quote_token())
        self.assertIn(order.name, self.url_open('/my/orders').text)
        self.assertNotIn(order.name, self.url_open('/my/quotes').text)

    def test_save_http_post_redirects_to_payable_order_and_clears_cart(self):
        # Exercise the actual controller/CSRF handling through Odoo's HTTP test
        # client. This is automated HTTP coverage, not a manual browser test.
        order = self._saved()
        order.write({'state': 'draft', 'b2b_checkout_mode': 'pay_now', 'b2b_submitted_at': False})
        self.authenticate(self.portal_user.login, 'Portal-Test-2026!',
                          session_extra={'sale_order_id': order.id})
        page = self.url_open('/my/orders/%s' % order.id)
        csrf = html.fromstring(page.text).xpath("//input[@name='csrf_token']")[0].get('value')
        def cart_for_request(website):
            return website.env['sale.order'].sudo().browse(order.id)

        with patch('odoo.addons.b2b_website.controllers.website_sale._can_checkout', return_value=True), \
                patch.object(type(order), '_is_cart_ready', return_value=True), \
                patch.object(type(order), '_b2b_check_product_allowed'), \
                patch.object(type(order), '_b2b_validate_sale_quantity'), \
                patch.object(type(self.website), '_get_and_cache_current_cart', cart_for_request):
            response = self.url_open('/shop/submit-for-review', data={'csrf_token': csrf})
        self.assertEqual(response.status_code, 200)
        order.invalidate_recordset()
        self.assertEqual(order.b2b_checkout_mode, 'pay_later')
        self.assertEqual(order.state, 'sent')
        self.assertNotIn('Awaiting Final Quote', response.text)
        self.assertFalse(order.b2b_erp_job_ids)
        self.assertNotIn('sale_order_id', root.session_store.get(self.session.sid))
