"""Visual-system contracts; actual hover/responsive QA is done in the browser."""
from pathlib import Path
import re

from lxml import html

from odoo.tests import HttpCase, TransactionCase, tagged


STYLE_DIR = Path(__file__).resolve().parents[1] / "static/src/scss"


@tagged("post_install", "-at_install")
class TestSiteTheme(TransactionCase):
    def test_brand_tokens_replace_legacy_accents_and_preserve_semantic_states(self):
        css = (STYLE_DIR / "partner_hub.scss").read_text(encoding="utf-8")
        self.assertIn("--lt-blue: var(--lt-primary)", css)
        self.assertIn("--lt-blue-dark: var(--lt-primary-hover)", css)
        self.assertIn("--lt-green: #16a36a", css)
        self.assertIn("--lt-red: #dc2626", css)
        for old in ("#2558e8", "#1744c6", "#2563eb", "#1d4ed8", "#d9ff43", "#c8ff62", "#efffcf"):
            self.assertNotIn(old, css.lower())
        fallback = (STYLE_DIR.parents[2] / "views/frontend_error_templates.xml").read_text(encoding="utf-8")
        self.assertNotIn("#315efb", fallback)
        self.assertIn("background:#d64100", fallback)

    def test_primary_button_white_text_has_sufficient_contrast(self):
        css = (STYLE_DIR / "partner_hub.scss").read_text(encoding="utf-8")
        value = re.search(r"--lt-primary:\s*#([0-9a-f]{6})", css).group(1)
        channels = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        luminance = sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
        self.assertGreaterEqual(1.05 / (luminance + .05), 4.5)

    def test_shared_chrome_and_natural_type_have_one_owner(self):
        base = (STYLE_DIR / "partner_hub.scss").read_text(encoding="utf-8")
        home = (STYLE_DIR / "homepage.scss").read_text(encoding="utf-8")
        shared = (STYLE_DIR / "site_theme.scss").read_text(encoding="utf-8")
        self.assertNotIn("JetBrains", base)
        self.assertIn("font-family: FontAwesome", base)
        self.assertIn(".lt-subnav .container, .lt-footer .container", shared)
        self.assertIn("font-size: calc(14 * var(--lt-chrome-u))", shared)
        self.assertNotIn("lt-footer", home)
        self.assertIn("--ph-page-max: 1500px", home)
        self.assertIn(".lt-product-card__model, .lt-purchase-panel__model", shared)
        self.assertIn(".lt-catalog-intro { padding: 12px 0 24px; }", shared)
        self.assertIn("--btn-hover-bg: var(--lt-primary-hover)", shared)


@tagged("post_install", "-at_install")
class TestSiteThemeHttp(HttpCase):
    def test_catalog_image_keeps_product_link_without_static_partner_badge(self):
        product = self.env["product.template"].create({
            "name": "Catalog badge removal regression", "sale_ok": True,
            "is_published": True, "b2b_visibility_mode": "all",
        })
        response = self.url_open("/products?search=Catalog+badge+removal+regression")
        self.assertEqual(response.status_code, 200)
        page = html.fromstring(response.content)
        image = page.xpath("//a[@class='lt-product-card__image'][img[@alt='%s']]" % product.name)
        self.assertEqual(len(image), 1)
        self.assertTrue(image[0].get("href").startswith("/products/"))
        self.assertIn("/web/image/product.template/%s/" % product.id, image[0].xpath("./img/@src")[0])
        self.assertFalse(image[0].xpath("./span"))
        self.assertNotIn("Partner Catalog", page.text_content())

    def test_public_surfaces_keep_native_routes_and_shared_footer(self):
        for route in ("/", "/products", "/resources", "/contact", "/about", "/repair-service",
                      "/warranty", "/faq", "/shipping", "/privacy", "/terms-of-use",
                      "/web/login", "/web/signup", "/partner-application"):
            with self.subTest(route=route):
                response = self.url_open(route)
                self.assertEqual(response.status_code, 200)
                page = html.fromstring(response.content)
                self.assertEqual(len(page.xpath("//footer[contains(@class,'lt-footer')]")), 1)
                self.assertTrue(page.xpath("//footer//a[@href='/products']"))
                self.assertTrue(page.xpath("//footer//a[@href='/contact']"))

    def test_compiled_theme_preserves_native_control_and_typography_contracts(self):
        page = html.fromstring(self.url_open("/products").content)
        css = ""
        for path in page.xpath("//link[@rel='stylesheet']/@href"):
            if path.startswith("/web/assets/"):
                response = self.url_open(path, timeout=45)
                self.assertEqual(response.status_code, 200)
                css += response.text
        self.assertIn("--lt-chrome-content-max", css)
        self.assertIn("--lt-font-body", css)
        self.assertIn("--btn-disabled-bg:var(--lt-primary)", re.sub(r"\s+", "", css))
        self.assertIn(".lt-product-card__model", css)
        self.assertNotIn("Error: Undefined", css)
