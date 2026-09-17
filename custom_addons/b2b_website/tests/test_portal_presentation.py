from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPortalPresentation(TransactionCase):
    def setUp(self):
        super().setUp()
        self.env["ir.config_parameter"].sudo().set_param("account.use_invoice_terms", True)
        self.company = self.env.company
        self.company.write({"terms_type": "html", "invoice_terms_html": "<p>You should update this document. Odoo S.A.</p>"})
        self.order = self.env["sale.order"].new({"company_id": self.company.id})

    def test_default_link_hidden_without_mutating_note(self):
        note = '<p>Terms and Conditions: <a href="http://localhost:8070/terms">http://localhost:8070/terms</a></p>'
        self.order.note = note
        self.assertTrue(self.order._b2b_is_placeholder_terms_note())
        self.assertEqual(self.order.note, note)
        self.assertFalse(self.company._b2b_has_published_sale_terms())

    def test_invoice_placeholder_preserves_contract_and_record(self):
        invoice = self.env['account.move'].new({'company_id': self.company.id})
        invoice.narration = '<p>Terms &amp; Conditions: <a href="http://localhost:8070/terms">Terms</a></p>'
        original = invoice.narration
        self.assertTrue(invoice._b2b_is_placeholder_terms_note())
        self.assertEqual(invoice.narration, original)
        invoice.narration = '<p>Special agreed payment terms.</p>'
        self.assertFalse(invoice._b2b_is_placeholder_terms_note())

    def test_preview_and_cart_templates(self):
        invoice = self.env.ref('account.report_invoice_document')._get_combined_arch()
        self.assertEqual(invoice.xpath(".//t[@name='proforma_invoice_title']")[0].text, 'Invoice Preview')
        self.assertIn('_b2b_is_placeholder_terms_note', invoice.xpath(".//div[@name='comment']")[0].get('t-if'))
        for xmlid in ('b2b_website.product_card', 'b2b_website.product_detail'):
            arch = self.env.ref(xmlid)._get_combined_arch()
            self.assertTrue(arch.xpath(".//form[@data-lt-cart-form]//button[@type='submit'][@disabled]"))

    def test_negotiated_prose_and_external_links_preserved(self):
        for note in (
            '<p>Custom delivery agreement. <a href="/terms">Terms</a></p>',
            '<p>Terms and Conditions: <a href="https://supplier.example/terms">Terms</a></p>',
            '<p>Shipment only after customer approval.</p>',
        ):
            self.order.note = note
            self.assertFalse(self.order._b2b_is_placeholder_terms_note())

    def test_published_terms_keep_native_order_link(self):
        self.company.with_context(lang="en_US").invoice_terms_html = '<p>Delivery and payment follow the accepted quotation.</p>'
        self.order.note = '<p>Terms &amp; Conditions: <a href="/terms">Terms</a></p>'
        self.assertTrue(self.company._b2b_has_published_sale_terms())
        self.assertFalse(self.order._b2b_is_placeholder_terms_note())

    def test_shared_templates_have_no_vendor_promotion(self):
        view = self.env.ref("portal.portal_record_sidebar")._get_combined_arch()
        self.assertFalse(view.xpath(".//a[@title='odoo']"))
        view = self.env.ref("sale.sale_order_portal_template")._get_combined_arch()
        self.assertFalse(view.xpath(".//*[@id='sale_portal_connect_software_modal']"))
        self.assertFalse(view.xpath(".//*[@id='portal_connect_software_modal_btn']"))

    def test_quotation_details_and_shared_header(self):
        view = self.env.ref("sale.portal_my_quotations")._get_combined_arch()
        self.assertTrue(view.xpath(".//t[@t-call='b2b_website.portal_order_list_header']"))
        self.assertTrue(view.xpath(".//a[@t-att-href='quotation.get_portal_url()'][contains(@class, 'lt-btn')]"))

    def test_native_promo_entry_disabled(self):
        self.assertFalse(self.env.ref("website_sale.reduction_code").active)
        view = self.env.ref("website_sale.total")._get_combined_arch()
        self.assertFalse(view.xpath(".//t[@t-call='website_sale.coupon_form']"))
