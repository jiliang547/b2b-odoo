from pathlib import Path
import re

from lxml import html

from odoo.addons.website_sale.tests.common import MockRequest
from odoo.tests import HttpCase, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestHomepageDesign(HttpCase):
    """Server-side rendering/configuration checks, not a browser visual UAT."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.b2b_price_display_mode = "approved"
        cls.env["b2b.product.brand"].search([]).active = False
        cls.brands = cls.env["b2b.product.brand"].create([
            {"name": "Homepage real brand %s" % i, "sequence": i,
             "tagline": "Configured tagline %s" % i, "website_published": True}
            for i in range(7)
        ])
        cls.unpublished = cls.env["b2b.product.brand"].create({
            "name": "Unpublished homepage brand", "sequence": -1, "website_published": False,
        })
        cls.category = cls.env["product.public.category"].create({"name": "Configured homepage category"})
        cls.product = cls.env["product.template"].create({
            "name": "Configured homepage speaker", "is_published": True,
            "sale_ok": True, "b2b_visibility_mode": "all", "list_price": 9743.27,
            "public_categ_ids": [(4, cls.category.id)],
        })
        cls.env["b2b.homepage.product"].search([("website_id", "=", cls.website.id)]).active = False
        for section in ("recommended", "special", "best_seller"):
            cls.env["b2b.homepage.product"].create({
                "website_id": cls.website.id, "section": section,
                "product_tmpl_id": cls.product.id, "sequence": 1,
            })

    def _page(self):
        response = self.url_open("/en/partner-home")
        self.assertEqual(response.status_code, 200)
        return html.fromstring(response.content)

    def test_five_published_brands_reuse_configuration_even_without_products(self):
        page = self._page()
        brands = page.xpath("//*[@data-home-brand]")
        self.assertEqual([int(node.get("data-home-brand")) for node in brands], self.brands[:5].ids)
        for index, brand in enumerate(brands):
            self.assertIn("Configured tagline %s" % index, brand.text_content())
            self.assertTrue(brand.get("href").startswith("/brands/"))
        self.assertNotIn(self.unpublished.name, page.text_content())

    def test_real_categories_featured_tabs_and_public_price_permissions(self):
        page = self._page()
        category = page.xpath("//*[@data-category-id='%s']" % self.category.id)
        self.assertTrue(category)
        self.assertEqual(category[0].xpath("./strong")[0].text, self.category.name)
        self.assertEqual([node.get("data-pg-featured-tab") for node in page.xpath("//*[@data-pg-featured-tab]")],
                         ["recommended", "special", "best_seller"])
        panels = page.xpath("//*[@data-pg-featured-panel]")
        self.assertFalse("hidden" in panels[0].attrib)
        self.assertTrue(all("hidden" in node.attrib for node in panels[1:]))
        for panel in panels:
            self.assertIn(self.product.name, panel.text_content())
            self.assertIn("Sign in to view partner pricing", panel.text_content())
            self.assertNotIn("9,743.27", panel.text_content())
            self.assertNotIn("9743.27", panel.text_content())
        self.assertFalse(page.xpath("//*[contains(@class,'ph-home')]//*[@data-lt-add-cart]"))

    def test_service_links_and_reserved_solutions_do_not_create_dead_routes(self):
        page = self._page()
        services = page.xpath("//*[contains(@class,'ph-services__grid')]/a")
        self.assertEqual(len(services), 4)
        self.assertTrue(all(link.get("href") == "/contact" for link in services))
        scenes = page.xpath("//*[contains(@class,'ph-solutions__track')]/article")
        self.assertEqual([node.xpath("./h3")[0].text for node in scenes],
                         ["Healthcare", "Education", "Corporate", "Public Venues", "Retail", "Entertainment"])
        self.assertTrue(scenes[0].xpath("./img[substring(@src,string-length(@src)-14)='healthcare.webp']"))
        self.assertFalse(page.xpath("//*[contains(@class,'ph-solutions__track')]//a"))
        self.assertTrue(page.xpath("//footer//a[contains(@href,'/my/tickets')]"))
        self.assertTrue(page.xpath("//a[@class='ph-explore'][@href='/products']"))

    def test_youtube_reuses_native_website_social_configuration(self):
        self.website.social_youtube = False
        page = self._page()
        self.assertTrue(page.xpath("//span[@aria-label='YouTube is not configured']"))
        self.assertFalse(page.xpath("//a[@href='/website/social/youtube']"))
        self.website.social_youtube = "https://www.youtube.com/@homepage-configuration-test"
        page = self._page()
        self.assertTrue(page.xpath("//a[@href='/website/social/youtube'][@rel='noopener noreferrer']"))
        response = self.url_open("/website/social/youtube", allow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], self.website.social_youtube)
        settings = self.env["res.config.settings"].create({"website_id": self.website.id})
        self.assertEqual(settings.b2b_social_youtube, self.website.social_youtube)

    def test_logos_assets_and_shared_navigation_remain_native(self):
        page = self._page()
        logos = page.xpath("//a[contains(@class,'lt-brand--wordmark')]/img")
        self.assertEqual(len(logos), 2)
        self.assertTrue(all("/web/image/website/%s/logo" % self.website.id in img.get("src") for img in logos))
        for selector in ("lt-locale-menu", "lt-nav-actions", "lt-footer"):
            self.assertTrue(page.xpath("//*[contains(@class,'%s')]" % selector))
        home = page.xpath("//div[@class='ph-home']")[0]
        self.assertNotIn("data:image", html.tostring(home).decode())
        self.assertFalse(home.xpath(".//iframe | .//script | .//form"))
        for path in set(home.xpath(".//img[starts-with(@src,'/b2b_website/static/')]/@src")):
            response = self.url_open(path)
            self.assertEqual(response.status_code, 200, path)
        response = self.url_open("/b2b_website/static/src/img/homepage/icons.svg")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ph-icon-shield", response.text)

    def test_frontend_styles_compile_with_the_new_homepage_scope(self):
        page = self._page()
        css = ""
        for path in page.xpath("//link[@rel='stylesheet']/@href"):
            if path.startswith("/web/assets/"):
                response = self.url_open(path, timeout=30)
                self.assertEqual(response.status_code, 200)
                css += response.text
        self.assertIn(".ph-home", css)
        self.assertIn(".ph-hero__benefits", css)
        frame = re.search(r"\.ph-home-page\s*\{([^}]+)\}", css)
        self.assertIsNotNone(frame)
        self.assertRegex(frame.group(1), r"--ph-page-max:\s*1500px")
        self.assertRegex(frame.group(1), r"max-width:\s*none")
        self.assertIn("--ph-vw", frame.group(1))
        self.assertIn("--ph-content-max", frame.group(1))
        self.assertNotIn("box-shadow", frame.group(1))
        sections = re.search(r"\.ph-home\s*>\s*section\s*\{([^}]+)\}", css)
        self.assertIsNotNone(sections)
        self.assertRegex(sections.group(1), r"max-width:\s*var\(--ph-page-max\)")
        cta = re.search(r"\.ph-home\s+\.ph-partner-cta\s*\{([^}]+)\}", css)
        self.assertIsNotNone(cta)
        self.assertRegex(cta.group(1), r"max-width:\s*none")
        # Native SCSS extends .container with .o_container_small in this group.
        shared_containers = [m for m in re.finditer(
            r"\.lt-subnav\s+\.container[^{}]*\{([^}]+)\}", css)
            if "var(--lt-chrome-content-max)" in m.group(1)]
        self.assertEqual(len(shared_containers), 1)
        self.assertRegex(shared_containers[0].group(0), r"\.lt-footer\s+\.container")
        eyebrow = re.search(r"\.ph-home\s+\.ph-hero__eyebrow\s*\{([^}]+)\}", css)
        self.assertIsNotNone(eyebrow)
        self.assertRegex(eyebrow.group(1), r"font-weight:\s*600")
        self.assertRegex(eyebrow.group(1), r"line-height:\s*1\.35")
        category_back = re.search(
            r"\.ph-home\s+\.pg-category-browser__trail\s*>\s*\[data-pg-category-back\]\s*\{([^}]+)\}", css)
        self.assertIsNotNone(category_back)
        for declaration in (r"border:\s*1px solid #e8e8eb", r"background:\s*#fff",
                            r"display:\s*inline-flex", r"white-space:\s*nowrap", r"font-weight:\s*600"):
            self.assertRegex(category_back.group(1), declaration)
        footer_copy = re.search(r"\.lt-footer\s+\.lt-footer__about\s+p\s*\{([^}]+)\}", css)
        self.assertIsNotNone(footer_copy)
        self.assertRegex(footer_copy.group(1), r"font-size:\s*calc\(14\s*\*\s*var\(--lt-chrome-u\)\)")
        self.assertRegex(footer_copy.group(1), r"line-height:\s*calc\(22\.75\s*\*\s*var\(--lt-chrome-u\)\)")
        self.assertRegex(css, r"--lt-orange:\s*#ff4d00")
        for prefix in (r"", r"\.lt-footer\s+"):
            footer_hover = re.search(
                prefix + r"\.lt-footer__grid\s+a:not\(\.lt-brand\):hover[^{}]*\{([^}]+)\}", css)
            self.assertIsNotNone(footer_hover)
            self.assertRegex(footer_hover.group(1), r"color:\s*var\(--lt-orange\)")
        divider = re.search(r"\.ph-home\s+\.pg-category-grid\s*>\s*button\s*>\s*span\s*\{([^}]+)\}", css)
        self.assertIsNotNone(divider)
        self.assertRegex(divider.group(1), r"border-bottom:\s*1px solid #f0f1f3")
        self.assertRegex(divider.group(1), r"padding:\s*0(?:;|$)")
        for image_selector in (r"\.pg-category-grid\s*>\s*button\s+img",
                               r"\.pg-featured-card__image\s+img"):
            image_rule = re.search(r"\.ph-home\s+" + image_selector + r"\s*\{([^}]+)\}", css)
            self.assertIsNotNone(image_rule)
            for declaration in (r"object-fit:\s*cover", r"object-position:\s*center",
                                r"padding:\s*0(?:;|$)", r"position:\s*absolute"):
                self.assertRegex(image_rule.group(1), declaration)
        credentials = re.search(r"\.ph-home\s+\.ph-credentials\s*\{([^}]+)\}", css)
        self.assertIsNotNone(credentials)
        self.assertRegex(credentials.group(1), r"background:\s*transparent")
        credentials_inner = re.search(
            r"\.ph-home\s+\.ph-credentials\s*>\s*\.ph-container\s*\{([^}]+)\}", css)
        self.assertIsNotNone(credentials_inner)
        self.assertRegex(credentials_inner.group(1), r"background:\s*#fdf5e9")
        self.assertRegex(credentials_inner.group(1), r"min-height:\s*calc\(63\s*\*\s*var\(--ph-u\)\)")
        services = re.search(r"\.ph-home\s+\.ph-services__panel\s*\{([^}]+)\}", css)
        self.assertIsNotNone(services)
        self.assertRegex(services.group(1), r"height:\s*calc\(131\s*\*\s*var\(--ph-u\)\)")
        self.assertNotIn("Error: Undefined", css)

    def test_credentials_background_uses_the_same_inner_container_as_content(self):
        page = self._page()
        credentials = page.xpath("//section[@class='ph-credentials']")[0]
        inner = credentials.xpath("./div[@class='ph-container']")
        self.assertEqual(len(inner), 1)
        self.assertEqual(len(inner[0].xpath("./div")), 4)
        self.assertEqual([" ".join(node.text_content().split()) for node in inner[0].xpath("./div/p")],
                         ["20+ Years of Experience", "Serving 100+ Countries", "ISO 9001 Certified", "Strict Quality Control"])
        self.assertTrue(page.xpath("//section[contains(@class,'ph-solutions')]/div[@class='ph-container']"))

    def test_entire_homepage_frame_and_warm_partnership_panel_match_reference_structure(self):
        page = self._page()
        frame = page.xpath("//div[contains(concat(' ',normalize-space(@class),' '),' ph-home-page ')]")
        self.assertEqual(len(frame), 1)
        self.assertTrue(frame[0].xpath("./nav[contains(@class,'lt-subnav')]"))
        self.assertTrue(frame[0].xpath("./footer"))
        self.assertTrue(frame[0].xpath("./main//section[contains(@class,'ph-hero')]"))
        cta = frame[0].xpath(".//section[@class='ph-partner-cta']")[0]
        self.assertIn("Become a Power & Grace Partner", cta.text_content())
        self.assertEqual(cta.xpath(".//a/@href"), ["/partner-application", "/contact"])
        self.assertFalse(cta.xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' lt-btn ')]"))
        self.assertFalse(page.xpath("//*[contains(@class,'pg-partner-cta')]"))
        catalog = html.fromstring(self.url_open("/products").content)
        self.assertFalse(catalog.xpath("//*[contains(@class,'ph-home-page')]"))

    def test_category_back_button_matches_reference_without_changing_navigation_hook(self):
        page = self._page()
        browser = page.xpath("//*[@data-pg-category-browser]")[0]
        trail = browser.xpath("./div[@data-pg-category-trail]")[0]
        back = trail.xpath("./button[@data-pg-category-back]")[0]
        self.assertEqual(back.get("type"), "button")
        self.assertEqual(back.get("aria-label"), "Back to previous category")
        self.assertEqual(back.text_content(), "Back")
        self.assertEqual(back.xpath("./svg/use/@href"),
                         ["/b2b_website/static/src/img/homepage/icons.svg#ph-icon-arrow"])
        self.assertFalse(back.xpath("./i"))
        self.assertFalse(trail.xpath("./span"))
        self.assertTrue(trail.xpath("./nav[@data-pg-category-breadcrumbs]"))

    def test_partner_copy_and_existing_actions(self):
        page = self._page()
        hero = page.xpath("//section[contains(@class,'ph-hero')]")[0]
        self.assertEqual(hero.xpath(".//h1")[0].text_content(),
                         "Professional & Commercial Audio")
        self.assertEqual(hero.xpath(".//h1/span/text()"), ["Professional &", "Commercial Audio"])
        self.assertEqual(hero.xpath(".//span[@class='ph-hero__eyebrow']")[0].text_content(), "B2B PARTNER PORTAL")
        self.assertEqual(hero.xpath(".//div[@class='ph-container ph-hero__content']/p")[0].text_content(),
                         "Explore our product range, access partner pricing, request samples, and manage your orders—all in one place.")
        self.assertTrue(hero.xpath(".//a[@href='/contact']/span[text()='Technical Support']"))
        self.assertTrue(hero.xpath(".//a[@class='ph-explore'][@href='/products']"))
        self.assertNotIn("Project Support", hero.text_content())
        self.assertEqual(page.xpath("//*[@id='ph-solutions-title']")[0].text_content(), "Audio Solutions by Application")
        cta = page.xpath("//section[@class='ph-partner-cta']")[0]
        self.assertEqual(cta.xpath(".//p")[0].text_content(),
                         "Apply for a partner account to access partner pricing, request samples, download technical resources, and get support from our sales team.")
        self.assertEqual([node.text_content() for node in cta.xpath(".//a")],
                         ["Apply for a Partner Account", "Contact Sales"])
        self.assertIn("Professional and commercial audio for distributors, system integrators, and audio brands worldwide.",
                      page.xpath("//footer")[0].text_content())

    def test_home_cards_do_not_inherit_legacy_button_layout(self):
        page = self._page()
        cards = page.xpath("//article[@class='ph-product-card']")
        self.assertEqual(len(cards), 3)
        for card in cards:
            self.assertTrue(card.xpath(".//span[@class='ph-product-card__rule']"))
            self.assertTrue(card.xpath(".//a[@class='ph-product-card__details']/svg"))
            self.assertFalse(card.xpath(".//*[contains(concat(' ',normalize-space(@class),' '),' lt-btn ')]"))
            self.assertNotIn("MOQ:", card.text_content())
        self.assertTrue(page.xpath("//*[@data-pg-featured-pagination]")[0].get("hidden"))


@tagged("post_install", "-at_install")
class TestHomepageProductCard(TransactionCase):
    def test_all_viewport_sizing_uses_one_capped_unit(self):
        stylesheet = Path(__file__).resolve().parents[1] / "static/src/scss/homepage.scss"
        source = stylesheet.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"(?<![\w-])\d*\.?\d+vw", source), ["1vw"])
        self.assertIn("--ph-page-max: 1500px", source)

    def test_home_variant_reuses_native_price_states_without_exposing_restricted_values(self):
        website = self.env.ref("website.default_website")
        product = self.env["product.template"].create({"name": "Reference homepage speaker"})
        with MockRequest(self.env, website=website):
            for state, text in (("login", "Sign in to view partner pricing"),
                                ("pending_approval", "awaiting approval"),
                                ("pricing_pending", "being configured"),
                                ("hidden", "Contact sales"), ("visible", "125")):
                values = {"product": product, "section": "recommended", "home_design_card": True,
                    "price": {"state": state, "price": 125, "currency": website.company_id.currency_id},
                    "procurement": {"minimum_quantity": 8, "uom_name": "Units"}}
                page = html.fromstring(self.env["ir.ui.view"]._render_template("b2b_website.homepage_featured_card", values))
                self.assertIn(text, page.text_content())
                if state != "visible":
                    self.assertNotIn("125", page.text_content())
                self.assertTrue(page.xpath("//a[@class='ph-product-card__details']"))
                self.assertNotIn("MOQ:", page.text_content())

    def test_native_card_keeps_all_price_states_and_only_real_sale_badges(self):
        website = self.env.ref("website.default_website")
        product = self.env["product.template"].create({"name": "Home price state speaker"})
        with MockRequest(self.env, website=website):
            for state, text in (("login", "Sign in to view price"),
                                ("pending_approval", "awaiting approval"),
                                ("pricing_pending", "being configured"),
                                ("hidden", "Contact sales"), ("visible", "125")):
                values = {"product": product, "section": "special", "price": {
                    "state": state, "price": 125, "base_price": 125,
                    "currency": website.company_id.currency_id,
                }, "procurement": {"minimum_quantity": 8, "uom_name": "Units"}}
                page = html.fromstring(self.env["ir.ui.view"]._render_template("b2b_website.homepage_featured_card", values))
                self.assertIn(text, page.text_content())
                self.assertIn("MOQ: 8", page.text_content())
                self.assertFalse(page.xpath("//*[contains(@class,'pg-sale-badge')]"))
            values["price"]["base_price"] = 150
            page = html.fromstring(self.env["ir.ui.view"]._render_template("b2b_website.homepage_featured_card", values))
            self.assertTrue(page.xpath("//*[contains(@class,'pg-sale-badge')]"))

    def test_decorative_asset_budget_and_reproducible_import(self):
        root = Path(__file__).resolve().parents[1] / "static/src/img/homepage"
        self.assertLess(sum(path.stat().st_size for path in root.iterdir()), 700_000)
        for name in ("hero", "healthcare", "education", "corporate", "public-venues", "retail", "entertainment"):
            self.assertTrue((root / (name + ".webp")).is_file())


@tagged("post_install", "-at_install")
class TestHomepageBrandPresets(TransactionCase):
    def setUp(self):
        super().setUp()
        self.Brand = self.env["b2b.product.brand"].with_context(lang="en_US", active_test=False)
        for brand in self.Brand.search([]):
            brand.name = "Other existing brand %s" % brand.id
        self.env["ir.config_parameter"].sudo().set_param("b2b_website.homepage_brands_initialized_v1", False)
        values = {"name": "like", "description": "Keep existing brand details", "product_focus": "Keep product focus"}
        if "b2b_selling_company_id" in self.Brand._fields:
            values["b2b_selling_company_id"] = self.env.company.id
        if "yonyou_class_code" in self.Brand._fields:
            values["yonyou_class_code"] = "05"
        self.like = self.Brand.create(values)
        self.bf = self.Brand.create({"name": "bandf"})
        self.product = self.env["product.template"].create({"name": "Existing brand-linked product", "b2b_brand_id": self.like.id})

    def test_adopts_existing_ids_and_preserves_business_bindings(self):
        fields = [name for name in ("description", "product_focus", "logo", "cover_image",
                  "b2b_selling_company_id", "b2b_collection_journal_ids", "yonyou_class_code",
                  "yonyou_class_snapshot", "yonyou_snapshot", "yonyou_salesperson", "yonyou_department")
                  if name in self.Brand._fields]
        before = self.like.read(fields)
        count = self.Brand.search_count([])
        self.Brand._b2b_initialize_homepage_brands()
        self.assertEqual(self.Brand.search_count([]), count + 3)
        self.assertEqual(self.like.name, "Like Audio")
        self.assertEqual(self.bf.name, "Ben & Fellows")
        self.assertEqual(self.product.b2b_brand_id, self.like)
        self.assertEqual(self.like.read(fields), before)
        first_five = self.Brand.search([("active", "=", True), ("website_published", "=", True)], limit=5)
        self.assertEqual(first_five.mapped("name"), ["Power & Grace", "Lucky Tone", "Ben & Fellows", "Like Audio", "TEMEISHENG"])
        self.assertEqual(first_five.mapped("tagline"), ["Professional Audio Solutions", "Commercial Audio Systems",
                         "Smart Home & Hotel Audio", "Party Speakers", "Portable & Karaoke Audio"])

    def test_upgrade_preserves_operator_changes_and_does_not_recreate_brands(self):
        self.Brand._b2b_initialize_homepage_brands()
        self.like.write({"name": "Operator brand name", "tagline": "Operator tagline", "sequence": 999,
                         "active": False, "website_published": False})
        before = self.Brand.search([]).read(["name", "tagline", "sequence", "active", "website_published"])
        self.Brand._b2b_initialize_homepage_brands()
        self.assertEqual(self.Brand.search([]).read(["name", "tagline", "sequence", "active", "website_published"]), before)

    def test_prefers_canonical_record_without_merging_duplicate_aliases(self):
        canonical = self.Brand.create({"name": "Like Audio"})
        self.Brand._b2b_initialize_homepage_brands()
        self.assertEqual(self.like.name, "like")
        self.assertEqual(canonical.tagline, "Party Speakers")
        self.assertEqual(self.product.b2b_brand_id, self.like)
        self.assertTrue(self.like.exists())
