from odoo import Command
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestExportLanguage(HttpCase):
    def test_chinese_browser_preference_uses_english_website(self):
        website = self.env.ref("website.default_website")
        self.assertEqual(website.default_lang_id.code, "en_US")
        self.assertFalse(website.language_ids.filtered(lambda lang: lang.code.startswith("zh_")))
        for path in ("/web/signup", "/web/login", "/contact", "/products"):
            response = self.url_open(path, headers={"Accept-Language": "zh-CN,zh;q=0.9"})
            self.assertEqual(response.status_code, 200)
            self.assertIn('lang="en-US"', response.text)
            self.assertNotIn('data-url_code="zh_CN"', response.text)

    def test_cleanup_preserves_other_languages_and_custom_payment_details(self):
        website = self.env.ref("website.default_website")
        spanish = self.env.ref("base.lang_es")
        spanish.active = True
        website.language_ids = [Command.link(spanish.id)]
        provider = self.env.ref("payment.payment_provider_demo").with_context(lang="en_US")
        provider.pending_msg = "<p>请使用以下转账详细信息</p><pre>TEST-ACCOUNT-42</pre>"
        self.env["website"]._b2b_apply_export_language()
        self.assertIn(spanish, website.language_ids)
        self.assertIn("Please use the following transfer details", provider.pending_msg)
        self.assertIn("TEST-ACCOUNT-42", provider.pending_msg)
        previous = provider.pending_msg
        self.env["website"]._b2b_apply_export_language()
        self.assertEqual(provider.pending_msg, previous)

    def test_website_order_does_not_inherit_customer_chinese_language(self):
        chinese = self.env.ref("base.lang_zh_CN")
        chinese.active = True
        partner = self.env["res.partner"].create({"name": "Language test", "lang": "zh_CN"})
        order = self.env["sale.order"].create({
            "partner_id": partner.id,
            "website_id": self.env.ref("website.default_website").id,
        })
        self.assertEqual(order._get_lang(), "en_US")
        order.website_id = False
        self.assertEqual(order._get_lang(), "zh_CN")
