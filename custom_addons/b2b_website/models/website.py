from odoo import Command, api, models
from odoo.http import request
from odoo.addons.website_sale.models.website import (
    PRICELIST_SELECTED_SESSION_CACHE_KEY,
    PRICELIST_SESSION_CACHE_KEY,
)


class Website(models.Model):
    _inherit = "website"

    @api.model
    def _b2b_apply_export_language(self):
        """Use native website language routing; leave staff languages intact."""
        english = self.env.ref("base.lang_en")
        if not english.active:
            english.active = True
        for website in self.search([]):
            languages = website.language_ids.filtered(
                lambda language: not language.code.startswith("zh_")
            ) | english
            website.write({
                "default_lang_id": (
                    website.default_lang_id.id
                    if website.default_lang_id and not website.default_lang_id.code.startswith("zh_")
                    else english.id
                ),
                "language_ids": [Command.set(languages.ids)],
            })

        # Repair known Chinese text saved as the English source. Exact
        # replacements preserve custom bank instructions, HTML and images.
        replacements = {
            "您的付款已经处理，但正在等待批准。": "Your payment has been processed but is awaiting approval.",
            "支付已获授权。": "Your payment has been authorized.",
            "您的付款已被处理。": "Your payment has been processed.",
            "您的支付已被取消。": "Your payment has been cancelled.",
            "请使用以下转账详细信息": "Please use the following transfer details",
            "银行账户": "Bank account",
            "条款和条件：": "Terms and Conditions: ",
            "品牌历史、定位、能力、产品和服务区域": "Brand history, positioning, capabilities, products and service regions",
            "我自己创建的产品长标题啊啊": "My custom product with a long title. ",
            "我自己创建的产品": "My Custom Product",
            "非常专业！": "Highly professional!",
            "专业！": "Professional!",
            "标签": "Tag",
            "优势1": "Advantage 1",
            "优势2": "Advantage 2",
        }
        exact = {
            "帮助": "Help", "我": "My Category", "我的": "My Products",
            "外部的": "External", "产品1": "Product 1", "产品2": "Product 2",
            "黑色": "Black", "白色": "White",
            "客户关怀": "Customer Care",
            "默认": "Default",
            "专属我的公司的价格表": "Company-specific Pricelist",
        }
        # Native state names are not translated fields. Keep record IDs and
        # codes unchanged so existing addresses and integrations remain valid.
        exact.update(dict(pair.split("=", 1) for pair in (
            "北京市=Beijing;上海市=Shanghai;浙江省=Zhejiang;天津市=Tianjin;"
            "安徽省=Anhui;福建省=Fujian;重庆市=Chongqing;江西省=Jiangxi;"
            "山东省=Shandong;河南省=Henan;内蒙古自治区=Inner Mongolia;"
            "湖北省=Hubei;新疆维吾尔自治区=Xinjiang;湖南省=Hunan;"
            "宁夏回族自治区=Ningxia;广东省=Guangdong;西藏自治区=Tibet;"
            "海南省=Hainan;广西壮族自治区=Guangxi;四川省=Sichuan;"
            "河北省=Hebei;贵州省=Guizhou;山西省=Shanxi;云南省=Yunnan;"
            "辽宁省=Liaoning;陕西省=Shaanxi;吉林省=Jilin;甘肃省=Gansu;"
            "黑龙江省=Heilongjiang;青海省=Qinghai;江苏省=Jiangsu;"
            "台湾省=Taiwan;香港特别行政区=Hong Kong;澳门特别行政区=Macao;"
            "彰化縣=Changhua County;嘉義市=Chiayi City;嘉義縣=Chiayi County;"
            "新竹縣=Hsinchu County;新竹市=Hsinchu City;花蓮縣=Hualien County;"
            "宜蘭縣=Yilan County;高雄市=Kaohsiung City;基隆市=Keelung City;"
            "金門縣=Kinmen County;連江縣=Lienchiang County;苗栗縣=Miaoli County;"
            "南投縣=Nantou County;新北市=New Taipei City;澎湖縣=Penghu County;"
            "屏東縣=Pingtung County;台中市=Taichung City;台南市=Tainan City;"
            "台北市=Taipei City;台東縣=Taitung County;桃園市=Taoyuan City;雲林縣=Yunlin County"
        ).split(";")))
        fields_by_model = {
            "payment.provider": ("pending_msg", "auth_msg", "done_msg", "cancel_msg"),
            "b2b.product.brand": ("website_description", "product_focus", "advantages"),
            "product.template": ("name", "description_sale"),
            "website.menu": ("name",),
            "product.public.category": ("name",),
            "product.attribute": ("name",),
            "product.attribute.value": ("name",),
            "product.pricelist": ("name",),
            "helpdesk.team": ("name",),
            "res.country.state": ("name",),
            "sale.order": ("note",),
        }
        for model_name, field_names in fields_by_model.items():
            for record in self.env[model_name].with_context(lang="en_US").search([]):
                values = {}
                for field_name in field_names:
                    original = record[field_name]
                    if not original:
                        continue
                    translated = exact.get(original, original)
                    for source, target in replacements.items():
                        translated = translated.replace(source, target)
                    if translated != original:
                        values[field_name] = translated
                if values:
                    record.write(values)

        # Only translate an unchanged native Chinese-generated description.
        # Negotiated/custom line descriptions must remain exactly as entered.
        portal_companies = self.env["res.users"].search([
            ("share", "=", True),
        ]).partner_id.commercial_partner_id
        for line in self.env["sale.order.line"].search([
            ("product_id", "!=", False), "|",
            ("order_id.website_id", "!=", False),
            ("order_id.partner_id", "child_of", portal_companies.ids),
        ]):
            if not any("\u3400" <= char <= "\u9fff" for char in line.name):
                continue
            if line.name == line.with_context(lang="zh_CN")._get_sale_order_line_multiline_description_sale():
                english_name = line.with_context(lang="en_US")._get_sale_order_line_multiline_description_sale()
                if english_name != line.name:
                    line.name = english_name

    def _prepare_sale_order_values(self, partner_sudo):
        values = super()._prepare_sale_order_values(partner_sudo)
        if partner_sudo:
            values["b2b_pricing_revision"] = (
                partner_sudo.commercial_partner_id.sudo().b2b_pricing_revision
            )
        return values

    def b2b_currency_pricelists(self):
        """Return one native selectable pricelist per currency in UI order."""
        self.ensure_one()
        available = self.get_pricelist_available(show_visible=True)
        current = request.pricelist if request else self.env["product.pricelist"]
        by_currency = {}
        for pricelist in available:
            code = pricelist.currency_id.name
            if code not in by_currency or pricelist == current:
                by_currency[code] = pricelist
        result = self.env["product.pricelist"]
        for code in ("USD", "EUR", "GBP", "CNY", "AED", "SGD"):
            if code in by_currency:
                result |= by_currency.pop(code)
        for code in sorted(by_currency):
            result |= by_currency[code]
        return result

    def b2b_language_label(self, language):
        labels = {
            "en_US": "English",
            "es_ES": "Español",
            "ar_001": "العربية",
            "fr_FR": "Français",
        }
        return labels.get(language.code, language.name.split("/")[-1].strip())

    def b2b_frontend_languages(self, frontend_languages):
        order = {code: index for index, code in enumerate(
            ("en_US", "es_ES", "ar_001", "fr_FR")
        )}
        return sorted(
            (language for language in frontend_languages.values()
             if not language.code.startswith("zh_")),
            key=lambda language: (order.get(language.code, 99), language.name),
        )

    def _get_and_cache_current_pricelist(self):
        session_pricelist = self.env["product.pricelist"]
        if request:
            session_pricelist_id = request.session.get(PRICELIST_SESSION_CACHE_KEY)
            session_pricelist = (
                request.env["product.pricelist"]
                .sudo()
                .browse(session_pricelist_id)
                .exists()
            )
        pricelist = super()._get_and_cache_current_pricelist()
        if not request or request.env.user._is_public() or not request.env.user.share:
            return pricelist

        company = request.env.user.partner_id.commercial_partner_id.sudo()
        # Keep the requested currency independently from the selected record.
        # The native partner property can legitimately be empty in a fresh or
        # neutralized database, but we still need the currency to resolve this
        # company's generated effective pricelist.
        pricing_source = pricelist or session_pricelist
        pricing_currency = pricing_source.currency_id if pricing_source else False
        selected_id = request.session.get(PRICELIST_SELECTED_SESSION_CACHE_KEY)
        selected = request.env["product.pricelist"].sudo().browse(selected_id).exists()
        if (
            pricelist.sudo().b2b_effective_partner_id
            and pricelist.sudo().b2b_effective_partner_id != company
        ):
            # Never accept another customer's generated pricelist, even if its
            # technical ID was submitted directly to the native selector.
            request.session.pop(PRICELIST_SESSION_CACHE_KEY, None)
            pricelist = company.property_product_pricelist.sudo()
            if not pricing_currency and pricelist:
                pricing_currency = pricelist.currency_id

        effective = (
            company._b2b_get_effective_pricelist(self, pricing_currency)
            if pricing_currency else request.env["product.pricelist"]
        )
        assigned = effective or company.property_product_pricelist.sudo()
        if (
            selected
            and selected == pricelist
            and selected.selectable
            and self.is_pricelist_available(selected.id)
            and not effective
        ):
            return pricelist

        if not assigned or (
            not assigned.b2b_effective_partner_id
            and not assigned._is_available_on_website(self)
        ):
            return pricelist

        # Portal B2B accounts always follow the pricelist assigned to their
        # customer record. This also invalidates a stale website-session choice
        # after an operator changes the customer's negotiated pricelist.
        request.session[PRICELIST_SESSION_CACHE_KEY] = assigned.id
        cart = request.cart
        revision_changed = bool(
            cart
            and cart.b2b_pricing_revision != company.b2b_pricing_revision
        )
        if cart and cart.state == "draft" and (
            cart.pricelist_id != assigned or revision_changed
        ):
            cart.write({
                "pricelist_id": assigned.id,
                "b2b_pricing_revision": company.b2b_pricing_revision,
            })
            cart._recompute_prices()
        return assigned
