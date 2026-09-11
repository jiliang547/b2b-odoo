"""Presentation-only safeguards: never rewrite contractual order notes."""
import re
from urllib.parse import urlsplit

from lxml import html

from odoo import models
from odoo.tools import is_html_empty


class ResCompany(models.Model):
    _inherit = "res.company"

    def _b2b_has_published_sale_terms(self):
        self.ensure_one()
        # Inspect the source language so a translation cannot publish the demo.
        content = self.with_context(lang="en_US").invoice_terms_html or ""
        return bool(
            self.env["ir.config_parameter"].sudo().get_param("account.use_invoice_terms")
            and self.terms_type == "html"
            and not is_html_empty(content)
            and "odoo s.a." not in content.lower()
            and "you should update this document" not in content.lower()
            and "yourcompany" not in content.lower()
        )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _b2b_is_placeholder_terms_note(self):
        self.ensure_one()
        if not self.note or self.company_id._b2b_has_published_sale_terms():
            return False
        document = html.fragment_fromstring(str(self.note), create_parent="div")
        links = document.xpath(".//a[@href]")
        if len(links) != 1:
            return False
        target = urlsplit(links[0].get("href"))
        hosts = {"localhost", "127.0.0.1", urlsplit(self.company_id.get_base_url()).hostname}
        if target.path.rstrip("/") != "/terms" or (target.hostname and target.hostname not in hosts):
            return False
        links[0].drop_tree()
        label = re.sub(r"[\s:：]+", "", document.text_content()).casefold()
        # Only the native link-only placeholder; preserve any negotiated prose.
        return label in {"terms&conditions", "termsandconditions", "条款和条件", "条款与条件"}
