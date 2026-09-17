from unittest.mock import patch

from odoo import Command
from odoo.tests import HttpCase, tagged
from odoo.addons.mail.models.mail_template import MailTemplate


@tagged("post_install", "-at_install")
class TestPartnerHubMultilingual(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.languages = cls.env["res.lang"]
        for code in ("es_ES", "fr_FR", "ar_001"):
            cls.languages |= cls.env["res.lang"]._activate_lang(code)
        cls.website.language_ids = [Command.link(language.id) for language in cls.languages]
        cls.env["ir.module.module"].search([("name", "in", [
            "b2b_website", "b2b_core", "b2b_sample", "b2b_erp_connector",
        ])])._update_translations(cls.languages.mapped("code"), overwrite=True)

    def test_localized_public_pages_and_fallbacks(self):
        expected = {
            "es": ("es-ES", "Catálogo de productos", "Crea tu cuenta de socio", "Política de privacidad"),
            "fr": ("fr-FR", "Catalogue de produits", "Créez votre compte partenaire", "Politique de confidentialité"),
            "ar": ("ar-001", "كتالوج المنتجات", "أنشئ حساب الشريك", "سياسة الخصوصية"),
        }
        for prefix, (lang, catalog, signup, privacy) in expected.items():
            for path, heading in (("/products", catalog), ("/web/signup", signup), ("/privacy", privacy)):
                with self.subTest(language=prefix, path=path):
                    response = self.url_open(f"/{prefix}{path}")
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(f'lang="{lang}"', response.text)
                    self.assertIn(heading, response.text)
                    if prefix == "ar":
                        self.assertIn('dir="rtl"', response.text)

    def test_native_translated_content_keeps_source_and_pricing(self):
        category = self.env["product.public.category"].create({"name": "Audio source"})
        category.with_context(lang="es_ES").name = "Audio traducido"
        self.assertEqual(category.with_context(lang="en_US").name, "Audio source")
        self.assertEqual(category.with_context(lang="es_ES").name, "Audio traducido")
        self.assertEqual(category.with_context(lang="fr_FR").name, "Audio source")
        partner = self.env['res.partner'].create({'name': 'Language pricing customer'})
        pricelist = partner.property_product_pricelist
        for language in self.languages:
            self.assertEqual(partner.with_context(lang=language.code).property_product_pricelist, pricelist)

    def test_frontend_js_catalog_contains_custom_validation(self):
        # Native translation payload includes website-named custom modules.
        response = self.url_open("/website/translations?lang=es_ES")
        self.assertEqual(response.status_code, 200)
        self.assertIn("b2b_website", response.text)
        self.assertIn("Selecciona una opción de la lista.", response.text)

    def test_language_cleanup_preserves_operator_default(self):
        french = self.languages.filtered(lambda language: language.code == "fr_FR")
        self.website.default_lang_id = french
        self.env["website"]._b2b_apply_export_language()
        self.assertEqual(self.website.default_lang_id, french)

    def test_registration_email_uses_recipient_language(self):
        partner = self.env["res.partner"].create({
            "name": "Language recipient", "email": "language-recipient@example.test", "lang": "fr_FR",
        })
        user = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": partner.name, "login": partner.email, "partner_id": partner.id,
            "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
        })
        application = self.env["b2b.registration.application"].create({
            "website_id": self.website.id, "partner_id": partner.id, "user_id": user.id,
            "full_name": partner.name, "business_email": partner.email,
        })
        rendered = []
        def capture(template, record_id, **kwargs):
            rendered.append(template._render_field("body_html", [record_id])[record_id])
            self.assertEqual(template.env.lang, "fr_FR")
        with patch.object(MailTemplate, "send_mail", capture):
            application.with_context(lang="en_US").action_send_verification_email()
        self.assertIn("Vérifier l’e-mail", rendered[0])
        self.assertNotIn("Thank you for registering", rendered[0])
