from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    b2b_visibility_mode = fields.Selection(
        [
            ("all", "All Website Visitors"),
            ("approved", "Approved B2B Customers"),
            ("segments", "Selected B2B Segments"),
            ("hidden", "Hidden from Partner Hub"),
        ],
        required=True,
        default="approved",
        index=True,
        tracking=True,
    )
    b2b_visible_segment_ids = fields.Many2many(
        "b2b.customer.segment",
        "b2b_product_segment_rel",
        "product_tmpl_id",
        "segment_id",
        string="Visible B2B Segments",
    )
    b2b_brand_id = fields.Many2one(
        "b2b.product.brand",
        string="Brand",
        ondelete="restrict",
        index=True,
    )
    b2b_application_ids = fields.Many2many(
        "b2b.product.application",
        "b2b_product_application_rel",
        "product_tmpl_id",
        "application_id",
        string="Applications",
    )
    b2b_model_number = fields.Char(string="Model Number", index="trigram")
    b2b_specifications = fields.Html(string="Technical Specifications", sanitize=True)
