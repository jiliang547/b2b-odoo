"""One-time editable homepage brand presets, not a second brand registry."""
from odoo import api, models


HOMEPAGE_BRANDS_KEY = "b2b_website.homepage_brands_initialized_v1"
HOMEPAGE_BRANDS = (
    ("Power & Grace", "Professional Audio Solutions", ("powerandgrace",)),
    ("Lucky Tone", "Commercial Audio Systems", ("lucky",)),
    ("Ben & Fellows", "Smart Home & Hotel Audio", ("benandfellows", "bandf", "bf")),
    ("Like Audio", "Party Speakers", ("like",)),
    ("TEMEISHENG", "Portable & Karaoke Audio", ()),
)


def _brand_key(name):
    return "".join(character for character in (name or "").casefold() if character.isalnum())


class ProductBrand(models.Model):
    _inherit = "b2b.product.brand"

    @api.model
    def _b2b_initialize_homepage_brands(self):
        """Adopt existing brand IDs and seed missing content once per database.

        Only presentation fields change. No company, bank, customer, product or
        ERP mappings are assigned. There are deliberately no owned brand XML IDs:
        these become normal operator-managed records, retained on uninstall.
        The marker also preserves later edits, archiving and ordering on upgrade.
        """
        params = self.env["ir.config_parameter"].sudo()
        if params.get_param(HOMEPAGE_BRANDS_KEY):
            return
        brands = self.sudo().with_context(lang="en_US", active_test=False)
        existing = brands.search([], order="id")
        sequence = min(existing.mapped("sequence") or [60]) - 50
        for index, (name, tagline, aliases) in enumerate(HOMEPAGE_BRANDS):
            canonical = _brand_key(name)
            matches = existing.filtered(lambda record: _brand_key(record.name) in (canonical, *aliases))
            # Prefer an exact spelling; otherwise keep the oldest existing ID.
            # Never merge/delete duplicate historical records or their bindings.
            brand = matches.filtered(lambda record: _brand_key(record.name) == canonical)[:1] or matches[:1]
            values = {"name": name, "tagline": tagline, "sequence": sequence + index * 10,
                      "active": True, "website_published": True}
            if brand:
                brand.write(values)
            else:
                brands.create(values)
        params.set_param(HOMEPAGE_BRANDS_KEY, "1")
