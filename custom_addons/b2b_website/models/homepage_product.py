from odoo import fields, models


class B2BHomepageProduct(models.Model):
    _name = "b2b.homepage.product"
    _description = "Partner Hub Homepage Product"
    _order = "section, sequence, id"

    website_id = fields.Many2one(
        "website",
        required=True,
        default=lambda self: self.env["website"].get_current_website(),
        ondelete="cascade",
        index=True,
    )
    section = fields.Selection(
        [
            ("recommended", "Recommended"),
            ("special", "Special Offers"),
            ("best_seller", "Best Sellers"),
        ],
        required=True,
        default="recommended",
        index=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template",
        string="Product",
        required=True,
        ondelete="cascade",
        domain="[('sale_ok', '=', True)]",
        index=True,
    )
    sequence = fields.Integer(default=10, index=True)
    active = fields.Boolean(default=True)

    _section_product_website_unique = models.Constraint(
        "UNIQUE (website_id, section, product_tmpl_id)",
        "A product can only appear once in each homepage section for a website.",
    )
