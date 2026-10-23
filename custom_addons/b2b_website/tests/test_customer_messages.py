"""Native transport, customer isolation and protected conversation regression."""
import base64
import json
from types import SimpleNamespace
from unittest.mock import patch
from psycopg2 import IntegrityError

from lxml import html
from odoo import Command, SUPERUSER_ID
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError, ConcurrencyError, ValidationError
from odoo.tests import HttpCase, tagged
from .test_collection import B2BCollectionCommon


class CustomerMessagesCommon(B2BCollectionCommon):
    @classmethod
    def get_default_groups(cls):
        return (super().get_default_groups() | cls.env.ref('helpdesk.group_helpdesk_manager')
                | cls.env.ref('stock.group_stock_manager'))

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.contact = cls.portal_user.partner_id
        cls.contact.email = 'message-customer@example.test'
        cls.operator.partner_id.email = 'message-operator@example.test'
        cls.website.salesperson_id = cls.operator
        cls.other_customer = cls.env['res.partner'].create({'name': 'Other message customer', 'email': 'other-message@example.test'})
        cls.other_user = mail_new_test_user(cls.env, login='message-other-portal', password='Portal-Test-2026!',
            groups='base.group_portal', partner_id=cls.other_customer.id)
        cls.order = cls.env['sale.order'].create({'partner_id': cls.contact.id, 'website_id': cls.website.id,
            'user_id': cls.operator.id, 'state': 'sale'})
        cls.evidence = cls.env['b2b.bank.receipt'].create({'order_id': cls.order.id, 'declared_amount': 100, 'transfer_reference': 'MESSAGE-TEST'})

    def public(self, source, **kwargs):
        return source.with_context(mail_notify_force_send=False)._b2b_post_customer_message(
            'Customer-visible message', author_id=self.operator.partner_id.id, **kwargs)

    def thread(self, source):
        return self.env['b2b.message.thread'].search([('source_model', '=', source._name), ('res_id', '=', source.id)])

    def notifications(self, message, partner=None):
        domain = [('mail_message_id', '=', message.id)]
        if partner:
            domain.append(('res_partner_id', '=', partner.id))
        return self.env['mail.notification'].sudo().search(domain)

    def all_sources(self):
        ticket = self.env['helpdesk.ticket'].create({'name': 'Message support', 'partner_id': self.contact.id,
            'company_id': self.env.company.id, 'user_id': self.operator.id})
        change = self.env['b2b.order.change.request'].create({'order_id': self.order.id, 'requested_changes': 'Please review.'})
        inquiry = self.env['b2b.contact.request'].create({'partner_id': self.contact.id, 'website_id': self.website.id,
            'contact_name': self.contact.name, 'email': self.contact.email, 'subject': 'Message inquiry', 'message': 'Question'})
        sample = self.env['b2b.sample.request'].create({'partner_id': self.customer.id, 'contact_id': self.contact.id,
            'website_id': self.website.id, 'contact_name': self.contact.name, 'company_name': self.customer.name,
            'email': self.contact.email, 'phone': '+15550100', 'shipping_address': 'Test road', 'reason': 'Message test',
            'line_ids': [Command.create({'product_id': self.product.id, 'quantity': 1, 'uom_id': self.product.uom_id.id})]})
        invoice = self.env['account.move'].create({'move_type': 'out_invoice', 'partner_id': self.contact.id,
            'journal_id': self.company_data['default_journal_sale'].id})
        credit = self.env['account.move'].create({'move_type': 'out_refund', 'partner_id': self.contact.id,
            'journal_id': self.company_data['default_journal_sale'].id})
        payment = self.env['account.payment'].create({'payment_type': 'inbound', 'partner_type': 'customer',
            'partner_id': self.contact.id, 'journal_id': self.journal.id, 'amount': 100})
        refund = payment.copy({'payment_type': 'outbound'})
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        picking = self.env['stock.picking'].create({'partner_id': self.contact.id, 'ticket_id': ticket.id,
            'picking_type_id': warehouse.out_type_id.id, 'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id})
        repair = self.env['repair.order'].create({'partner_id': self.contact.id, 'ticket_id': ticket.id,
            'company_id': self.env.company.id, 'product_id': self.product.id})
        application = self.env['b2b.registration.application'].create({'user_id': self.portal_user.id,
            'partner_id': self.contact.id, 'website_id': self.website.id, 'full_name': self.contact.name,
            'company_name': self.customer.name, 'business_email': self.contact.email})
        return [self.order, inquiry, sample, ticket, change, self.evidence, payment, refund, invoice, credit,
                picking, repair, self.contact, application]


@tagged('post_install', '-at_install')
class TestCustomerMessages(CustomerMessagesCommon):
    def test_every_customer_source_uses_one_native_message_email_and_unread(self):
        for source in self.all_sources():
            with self.subTest(model=source._name, id=source.id):
                message = self.public(source)
                thread = self.thread(source)
                self.assertEqual(len(thread), 1)
                self.assertEqual(thread.last_message_id, message)
                notice = self.notifications(message, self.contact)
                self.assertEqual(len(notice), 1)
                self.assertEqual(notice.notification_type, 'email')
                self.assertFalse(notice.is_read)
                self.assertTrue(notice.mail_mail_id, 'Native email queue must exist')
                self.assertIn(message, thread.with_user(self.portal_user)._customer_messages())
                action_link = source._notify_get_action_link('view')
                if source._b2b_customer_message_context()['route'] and isinstance(source, self.env.registry['portal.mixin']):
                    self.assertNotIn('/my/messages/', action_link)
                else:
                    self.assertIn('/my/messages/', action_link)

    def test_notes_never_notify_customer_even_if_explicitly_mentioned(self):
        for source in self.all_sources():
            public = self.public(source)
            note = source.with_context(mail_notify_force_send=False).message_post(body='Private staff note',
                message_type='comment', subtype_xmlid='mail.mt_note', partner_ids=self.contact.ids)
            self.assertFalse(self.notifications(note, self.contact), source._name)
            self.assertEqual(self.thread(source).last_message_id, public)
            self.assertNotIn(note, self.thread(source).with_user(self.portal_user)._customer_messages())

    def test_cross_customer_explicit_recipient_is_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.public(self.evidence, partner_ids=self.other_customer.ids)

    def test_guest_inquiry_cannot_be_sent_to_an_unrelated_customer(self):
        guest = self.env['b2b.contact.request'].create({'website_id': self.website.id,
            'contact_name': 'Unregistered visitor', 'email': 'visitor-message@example.test',
            'subject': 'Guest conversation', 'message': 'Test inquiry'})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.public(guest, partner_ids=self.other_customer.ids)

    def test_cross_customer_author_is_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.evidence._b2b_post_customer_message('Not my record', author_id=self.other_customer.id)

    def test_sudoed_public_and_portal_callbacks_deliver_system_events_to_the_customer(self):
        for user in (self.env.ref('base.public_user'), self.portal_user):
            message = self.evidence.with_user(user).sudo().with_context(mail_notify_force_send=False)._b2b_post_customer_message(
                'Automatic payment status update')
            self.assertEqual(message.author_id, self.env.ref('base.partner_root'))
            self.assertEqual(self.thread(self.evidence).last_message_id, message)
            self.assertEqual(len(self.notifications(message, self.contact)), 1)

    def test_sample_payment_polling_keeps_customer_confirmation_email(self):
        sample = self.all_sources()[2]
        sample.action_submit()
        sample.action_approve()
        order = sample.sale_order_id
        transaction = self._online_transaction(order, order.amount_total, state='done')
        order.with_user(self.portal_user).sudo().with_context(mail_notify_force_send=False,
            b2b_payment_transaction_ids=transaction.ids).action_confirm()
        message = self.thread(sample).last_message_id
        self.assertIn('confirmed after payment', str(message.body))
        self.assertEqual(message.author_id, self.env.ref('base.partner_root'))
        self.assertEqual(len(self.notifications(message, self.contact)), 1)

    def test_context_flag_cannot_bypass_customer_boundary(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.evidence.with_user(self.operator).sudo().with_context(install_demo=True)._b2b_post_customer_message(
                'A request cannot impersonate the native demo loader', partner_ids=self.other_customer.ids)

    def test_native_superuser_demo_import_does_not_create_customer_threads(self):
        demo = self.evidence.with_user(SUPERUSER_ID).with_context(install_demo=True, mail_notify_force_send=False)
        demo._b2b_post_customer_message('Native demonstration comment')
        self.assertFalse(self.thread(demo))

    def test_stale_external_follower_is_not_notified(self):
        self.evidence.message_subscribe(self.other_customer.ids)
        message = self.public(self.evidence)
        self.assertFalse(self.notifications(message, self.other_customer))
        self.assertEqual(len(self.notifications(message, self.contact)), 1)

    def test_native_composer_proposes_actual_contact_not_a_company_without_email(self):
        for source in self.all_sources():
            suggestions = source._message_get_suggested_recipients_batch()[source.id]
            self.assertTrue(all(row['email'] for row in suggestions), source._name)
            self.assertIn(self.contact.id, [row['partner_id'] for row in suggestions], source._name)

    def test_company_and_contact_with_same_mailbox_do_not_send_two_emails(self):
        self.customer.email = self.contact.email
        order = self.env['sale.order'].create({'partner_id': self.customer.id, 'website_id': self.website.id,
            'user_id': self.operator.id})
        message = self.public(order)
        notices = self.notifications(message)
        self.assertEqual(len(notices.filtered(lambda notice: notice.notification_type == 'email'
            and notice.res_partner_id.email_normalized == self.contact.email_normalized)), 1)
        self.assertTrue(self.notifications(message, self.contact))

    def test_staff_without_source_company_is_not_notified(self):
        company = self.env['res.company'].create({'name': 'Unrelated messaging seller'})
        staff = mail_new_test_user(self.env, login='message-other-company-staff', groups='base.group_user',
            company_id=company.id, company_ids=[Command.set(company.ids)])
        self.evidence.message_subscribe(staff.partner_id.ids)
        self.assertFalse(self.notifications(self.public(self.evidence), staff.partner_id))

    def test_private_note_cannot_notify_staff_outside_the_source_company(self):
        company = self.env['res.company'].create({'name': 'Unrelated private-note company'})
        staff = mail_new_test_user(self.env, login='message-unrelated-private-note-staff', groups='base.group_user',
            company_id=company.id, company_ids=[Command.set(company.ids)])
        note = self.evidence.with_context(mail_notify_force_send=False).message_post(body='Private note',
            message_type='comment', subtype_xmlid='mail.mt_note', partner_ids=staff.partner_id.ids)
        self.assertFalse(self.notifications(note, staff.partner_id))

    def test_internal_conversation_lookup_cannot_bypass_native_index_company_rule(self):
        application = self.all_sources()[-1]
        self.public(application)
        company = self.env['res.company'].create({'name': 'Unrelated registration reviewer company'})
        staff = mail_new_test_user(self.env, login='message-unrelated-registration-reviewer',
            groups='b2b_core.group_b2b_manager', company_id=company.id, company_ids=[Command.set(company.ids)])
        # Registration review is a shared workspace; its source ACL alone must
        # not bypass the company rule on the indexed conversation.
        application.with_user(staff).with_context(allowed_company_ids=company.ids).check_access('read')
        with self.assertRaises(AccessError):
            self.thread(application).with_user(staff).with_context(allowed_company_ids=company.ids)._customer_source()

    def test_unlinked_customer_payment_reuses_native_customer_salesperson(self):
        self.contact.user_id = self.operator
        payment = self.env['account.payment'].create({'payment_type': 'outbound', 'partner_type': 'customer',
            'partner_id': self.contact.id, 'journal_id': self.journal.id, 'amount': 1})
        self.assertEqual(payment._b2b_customer_message_context()['staff'], self.operator)

    def test_portal_cannot_read_finance_source_or_other_thread(self):
        self.public(self.evidence)
        thread = self.thread(self.evidence)
        self.assertTrue(thread.with_user(self.portal_user)._customer_source())
        with self.assertRaises(AccessError):
            self.evidence.with_user(self.portal_user).read(['review_note'])
        with self.assertRaises(AccessError):
            thread.with_user(self.other_user)._customer_source()
        with self.assertRaises(AccessError):
            thread.with_user(self.other_user).read(['last_message_preview'])

    def test_company_selection_still_scopes_backend(self):
        self.public(self.evidence)
        other = self.env['res.company'].create({'name': 'Selected messaging seller'})
        self.operator.company_ids |= other
        visible = self.env['b2b.message.thread'].with_user(self.operator).with_context(allowed_company_ids=[other.id])
        self.assertFalse(visible.search([('id', '=', self.thread(self.evidence).id)]))

    def test_read_state_cannot_be_changed_for_another_customer(self):
        message = self.public(self.evidence)
        thread = self.thread(self.evidence).with_user(self.portal_user)
        with self.assertRaises(AccessError):
            thread.action_mark_read(self.other_customer)
        thread.action_mark_read()
        self.assertTrue(self.notifications(message, self.contact).is_read)

    def test_index_metadata_is_system_managed_even_for_a_b2b_manager(self):
        self.public(self.evidence)
        thread = self.thread(self.evidence)
        with self.assertRaises(AccessError):
            thread.write({'last_message_preview': 'Forged preview'})
        with self.assertRaises(AccessError):
            thread.unlink()
        message = self.public(self.evidence)
        self.assertEqual(thread.last_message_id, message)

    def test_non_portal_customer_keeps_native_token_based_document_link(self):
        partner = self.env['res.partner'].create({'name': 'Not yet invited customer', 'email': 'uninvited@example.test'})
        order = self.env['sale.order'].create({'partner_id': partner.id, 'website_id': self.website.id})
        self.public(order)
        self.assertNotIn('/my/messages/', order._notify_get_action_link('view'))

    def test_backfill_is_idempotent_and_never_sends_another_email(self):
        message = self.public(self.evidence)
        count = len(self.notifications(message))
        mails = self.env['mail.mail'].search_count([('mail_message_id', '=', message.id)])
        self.thread(self.evidence).sudo().unlink()
        # Narrow the migration query to this test's rows for speed; the real
        # migration scans all supported sources in bounded batches.
        for unused in range(2):
            self.env['b2b.message.thread']._sync_from_message(message)
        self.assertEqual(len(self.thread(self.evidence)), 1)
        self.assertEqual(len(self.notifications(message)), count)
        self.assertEqual(self.env['mail.mail'].search_count([('mail_message_id', '=', message.id)]), mails)

    def test_registration_result_template_uses_one_native_public_delivery(self):
        self.env.company.email = 'message-legal-seller@example.test'
        application = self.all_sources()[-1]
        for xmlid in ('b2b_website.mail_template_registration_approved', 'b2b_website.mail_template_registration_rejected'):
            message = application.with_context(mail_notify_force_send=False).message_post_with_source(
                self.env.ref(xmlid), message_type='comment', subtype_xmlid='mail.mt_comment')
            self.assertEqual(len(message), 1)
            self.assertEqual(self.thread(application).last_message_id, message)
            self.assertEqual(len(self.notifications(message, self.contact)), 1)
            self.assertFalse(self.notifications(message, self.contact).is_read)
            self.assertEqual(message.author_id, self.env.user.partner_id)
            self.assertIn(self.env.company.email, message.email_from)

    def test_every_customer_template_separates_company_mailbox_from_author(self):
        self.env.company.email = 'message-legal-seller@example.test'
        self.assertTrue(self.env.company.partner_id.partner_share)
        for source in self.all_sources():
            with self.subTest(model=source._name):
                template = self.env['mail.template'].create({
                    'name': 'Customer template sender regression',
                    'model_id': self.env['ir.model']._get_id(source._name),
                    'email_from': self.env.company.email,
                    'partner_to': str(self.contact.id),
                    'subject': 'Public customer template',
                    'body_html': '<p>Public template notification.</p>',
                })
                message = source.with_context(mail_notify_force_send=False).message_post_with_source(
                    template, message_type='comment', subtype_xmlid='mail.mt_comment')
                self.assertEqual(message.author_id, self.env.user.partner_id)
                self.assertIn(self.env.company.email, message.email_from)
                self.assertEqual(self.thread(source).last_message_id, message)
                notice = self.notifications(message, self.contact)
                self.assertEqual(len(notice), 1)
                self.assertEqual(notice.notification_type, 'email')
                self.assertFalse(notice.is_read)
                self.assertFalse(self.notifications(message, self.other_customer))

    def test_template_author_fix_does_not_allow_other_customer_recipient(self):
        self.env.company.email = 'message-legal-seller@example.test'
        template = self.env['mail.template'].create({
            'name': 'Foreign template recipient must stay blocked',
            'model_id': self.env['ir.model']._get_id(self.evidence._name),
            'email_from': self.env.company.email,
            'partner_to': str(self.other_customer.id),
            'use_default_to': False,
            'body_html': '<p>Wrong recipient.</p>',
        })
        with self.assertRaisesRegex(ValidationError, "another customer's contacts"), self.cr.savepoint():
            self.evidence.message_post_with_source(template, message_type='comment', subtype_xmlid='mail.mt_comment')

    def test_registration_uses_native_resolved_seller_for_staff_isolation(self):
        application = self.all_sources()[-1]
        seller = self.env['res.company'].create({'name': 'Registration resolved seller',
            'email': 'message-other-legal-seller@example.test'})
        reviewer = mail_new_test_user(self.env, login='message-seller-reviewer', groups='b2b_core.group_b2b_manager',
            email='message-seller-reviewer@example.test', company_id=seller.id, company_ids=[Command.set(seller.ids)])
        self.customer.b2b_selling_company_id = seller
        application.write({'resolved_partner_id': self.customer.id, 'approved_by_id': reviewer.id})
        application.message_subscribe(self.operator.partner_id.ids)
        self.assertEqual(application._b2b_customer_message_context()['company'], seller)
        message = application.with_user(reviewer).sudo().with_context(mail_notify_force_send=False).message_post_with_source(
            self.env.ref('b2b_website.mail_template_registration_approved'), message_type='comment', subtype_xmlid='mail.mt_comment')
        self.assertEqual(message.author_id, reviewer.partner_id)
        self.assertFalse(self.notifications(message, self.operator.partner_id))
        self.assertEqual(len(self.notifications(message, self.contact)), 1)

    def test_template_internal_note_still_never_notifies_customer(self):
        template = self.env['mail.template'].create({
            'name': 'Private template note', 'model_id': self.env['ir.model']._get_id(self.evidence._name),
            'email_from': self.env.company.email or self.env.user.email,
            'partner_to': str(self.contact.id), 'body_html': '<p>Private template note.</p>',
        })
        message = self.evidence.with_context(mail_notify_force_send=False).message_post_with_source(
            template, message_type='comment', subtype_xmlid='mail.mt_note')
        self.assertFalse(self.notifications(message, self.contact))
        self.assertFalse(self.thread(self.evidence))

    def test_native_notification_retry_does_not_duplicate_email_or_thread(self):
        message = self.public(self.evidence)
        count = len(self.notifications(message))
        mails = self.env['mail.mail'].search_count([('mail_message_id', '=', message.id)])
        self.evidence.with_context(mail_notify_force_send=False)._notify_thread(message, skip_existing=True)
        self.assertEqual(len(self.notifications(message)), count)
        self.assertEqual(self.env['mail.mail'].search_count([('mail_message_id', '=', message.id)]), mails)
        self.assertEqual(len(self.thread(self.evidence)), 1)

    def test_technical_notifications_and_activation_email_are_not_indexed(self):
        notification = self.evidence.message_post(body='Internal workflow event')
        email = self.env['mail.message'].create({'model': self.evidence._name, 'res_id': self.evidence.id,
            'message_type': 'email', 'body': 'SECRET ACTIVATION TOKEN', 'subtype_id': False})
        for message in (notification, email):
            self.assertFalse(self.env['b2b.message.thread']._sync_from_message(message))
        self.assertFalse(self.thread(self.evidence))

    def test_reindex_cannot_move_last_message_backwards(self):
        first = self.public(self.evidence)
        last = self.public(self.evidence)
        self.env['b2b.message.thread']._sync_from_message(first)
        self.assertEqual(self.thread(self.evidence).last_message_id, last)

    def test_first_message_race_uses_odoo_native_transaction_retry(self):
        class DuplicateConversation(IntegrityError):
            @property
            def diag(self):
                return SimpleNamespace(constraint_name='b2b_message_thread_source_unique')
        message = self.env['mail.message'].create({'model': self.evidence._name, 'res_id': self.evidence.id,
            'message_type': 'comment', 'subtype_id': self.env.ref('mail.mt_comment').id, 'body': 'Concurrent reply'})
        model = self.env['b2b.message.thread']
        with patch.object(type(model), 'create', side_effect=DuplicateConversation('simulated unique race')):
            with self.assertRaises(ConcurrencyError):
                model._sync_from_message(message)

    def test_reassigned_order_does_not_transfer_old_conversation(self):
        message = self.public(self.order)
        thread = self.thread(self.order)
        self.order.partner_id = self.other_customer
        self.assertFalse(thread.exists())
        self.assertFalse(self.env['b2b.message.thread']._sync_from_message(message))

    def test_logged_in_contact_company_change_invalidates_native_owner_rules(self):
        self.public(self.evidence)
        old_thread = self.thread(self.evidence)
        portal_threads = self.env['b2b.message.thread'].with_user(self.portal_user)
        self.assertIn(old_thread, portal_threads.search([]))  # Warm native ir.rule cache.
        self.contact.parent_id = self.other_customer
        new_order = self.env['sale.order'].create({'partner_id': self.contact.id,
            'website_id': self.website.id, 'user_id': self.operator.id})
        self.public(new_order)
        visible = portal_threads.search([])
        self.assertIn(self.thread(new_order), visible)
        self.assertNotIn(old_thread, visible)
        self.assertFalse(old_thread.exists())

    def test_supplier_payment_and_invoice_are_not_customer_conversations(self):
        payment = self.env['account.payment'].create({'payment_type': 'outbound', 'partner_type': 'supplier',
            'partner_id': self.other_customer.id, 'journal_id': self.journal.id, 'amount': 1})
        invoice = self.env['account.move'].create({'move_type': 'in_invoice', 'partner_id': self.other_customer.id,
            'journal_id': self.company_data['default_journal_purchase'].id})
        for source in (payment, invoice):
            message = self.public(source)
            self.assertFalse(self.thread(source))
            self.assertFalse(self.notifications(message, self.contact))


@tagged('post_install', '-at_install')
class TestCustomerMessagesHttp(CustomerMessagesCommon, HttpCase):
    def test_every_source_opens_a_readable_conversation_not_an_empty_business_page(self):
        sources = self.all_sources()
        messages = {source: self.public(source) for source in sources}
        self.authenticate(self.portal_user.login, 'Portal-Test-2026!')
        for source, message in messages.items():
            response = self.url_open('/my/messages/%s/open' % self.thread(source).id)
            self.assertEqual(response.status_code, 200, source._name)
            self.assertIn('Customer-visible message', response.text, source._name)
            self.assertIn('Your reply', response.text, source._name)

    def test_native_order_and_ticket_portal_reply_needs_read_not_business_write(self):
        ticket = self.env['helpdesk.ticket'].create({'name': 'Portal reply permission regression',
            'partner_id': self.contact.id, 'user_id': self.operator.id})
        self.authenticate(self.portal_user.login, 'Portal-Test-2026!')
        for source in (self.order, ticket):
            self.public(source)
            with self.assertRaises(AccessError):
                source.with_user(self.portal_user).check_access('write')
            payload = {'jsonrpc': '2.0', 'method': 'call', 'params': {'thread_model': source._name,
                'thread_id': source.id, 'post_data': {'body': '<p>Native customer reply</p>',
                    'message_type': 'comment', 'subtype_xmlid': 'mail.mt_comment'}}}
            response = self.url_open('/mail/message/post', data=json.dumps(payload), headers={'Content-Type': 'application/json'})
            result = response.json()
            self.assertNotIn('error', result, str(result))
            message = self.env['mail.message'].browse(result['result']['message_id'])
            self.assertEqual(message.author_id, self.contact)
            self.assertEqual(self.thread(source).last_message_id, message)
            self.assertEqual(len(self.notifications(message, self.operator.partner_id)), 1)

    def _page(self):
        self.public(self.evidence)
        self.authenticate(self.portal_user.login, 'Portal-Test-2026!')
        thread = self.thread(self.evidence)
        response = self.url_open('/my/messages/%s' % thread.id)
        self.assertEqual(response.status_code, 200)
        tree = html.fromstring(response.text)
        data = {node.get('name'): node.get('value') for node in tree.xpath('//form[contains(@action,"/reply")]//input')}
        return thread, response, data

    def test_finance_conversation_renders_and_reply_replay_sends_once(self):
        thread, page, data = self._page()
        self.assertIn('Customer-visible message', page.text)
        data.update(body='Customer reply <script>alert(1)</script>', author_id=self.other_customer.id)
        before = self.env['mail.message'].search_count([('model', '=', self.evidence._name), ('res_id', '=', self.evidence.id)])
        for unused in range(2):
            response = self.url_open('/my/messages/%s/reply' % thread.id, data=data)
            self.assertEqual(response.status_code, 200)
        messages = self.env['mail.message'].search([('model', '=', self.evidence._name), ('res_id', '=', self.evidence.id)], order='id desc')
        self.assertEqual(len(messages), before + 1)
        self.assertEqual(messages[0].author_id, self.contact)
        self.assertIn('&lt;script&gt;', str(messages[0].body))
        self.assertEqual(len(self.notifications(messages[0], self.operator.partner_id)), 1)

    def test_other_customer_get_read_reply_and_attachment_are_denied(self):
        thread, page, data = self._page()
        attachment = self.env['ir.attachment'].create({'name': 'public-test.txt', 'datas': base64.b64encode(b'PUBLIC'),
            'res_model': self.evidence._name, 'res_id': self.evidence.id})
        message = self.public(self.evidence, attachment_ids=attachment.ids)
        download = self.url_open('/my/messages/%s/attachments/%s/%s' % (thread.id, message.id, attachment.id))
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b'PUBLIC')
        self.authenticate(self.other_user.login, 'Portal-Test-2026!')
        for url in ('/my/messages/%s', '/my/messages/%s/open'):
            self.assertEqual(self.url_open(url % thread.id).status_code, 404)
        # Use the attacker's own CSRF token, so authorization rather than CSRF
        # is the reason the cross-customer reply is denied.
        other_order = self.env['sale.order'].create({'partner_id': self.other_customer.id, 'website_id': self.website.id})
        self.public(other_order)
        own = self.url_open('/my/messages/%s' % self.thread(other_order).id)
        token = html.fromstring(own.text).xpath('//input[@name="csrf_token"]/@value')[0]
        self.assertEqual(self.url_open('/my/messages/%s/reply' % thread.id,
            data={'body': 'ATTACK', 'csrf_token': token, 'submission_key': data['submission_key']}).status_code, 404)
        self.assertEqual(self.url_open('/my/messages/%s/attachments/%s/%s' % (thread.id, message.id, attachment.id)).status_code, 404)

    def test_internal_note_and_attachment_never_render_for_customer(self):
        thread, page, data = self._page()
        attachment = self.env['ir.attachment'].create({'name': 'private-test.txt', 'datas': base64.b64encode(b'SECRET'),
            'res_model': self.evidence._name, 'res_id': self.evidence.id})
        note = self.evidence.message_post(body='SECRET STAFF NOTE', message_type='comment',
            subtype_xmlid='mail.mt_note', attachment_ids=attachment.ids, partner_ids=self.contact.ids)
        response = self.url_open('/my/messages/%s' % thread.id)
        self.assertNotIn('SECRET STAFF NOTE', response.text)
        self.assertNotIn('private-test.txt', response.text)
        self.assertEqual(self.url_open('/my/messages/%s/attachments/%s/%s' % (thread.id, note.id, attachment.id)).status_code, 404)
