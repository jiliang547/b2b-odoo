from odoo import fields, models


class WebsiteTrack(models.Model):
    _inherit = "website.track"

    b2b_product_tmpl_id = fields.Many2one(
        "product.template",
        string="Viewed Partner Product",
        ondelete="cascade",
        index=True,
        readonly=True,
    )
