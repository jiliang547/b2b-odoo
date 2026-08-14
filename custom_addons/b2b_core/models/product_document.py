from odoo import fields, models


class ProductDocument(models.Model):
    _inherit = "product.document"

    b2b_visibility_mode = fields.Selection(
        [
            ("product", "Anyone Who Can View the Product"),
            ("approved", "Approved B2B Customers"),
            ("segments", "Selected B2B Segments"),
            ("internal", "Internal Users Only"),
        ],
        required=True,
        default="product",
        index=True,
    )
    b2b_visible_segment_ids = fields.Many2many(
        "b2b.customer.segment",
        "b2b_document_segment_rel",
        "document_id",
        "segment_id",
        string="Visible B2B Segments",
    )
    b2b_resource_type = fields.Selection(
        [
            ("datasheet", "Datasheet"),
            ("manual", "User Manual"),
            ("certificate", "Certificate"),
            ("installation", "Installation Guide"),
            ("drawing", "Drawing"),
            ("image", "Image"),
            ("video", "Video"),
            ("software", "Software"),
            ("other", "Other"),
        ],
        default="other",
        required=True,
    )
    b2b_version = fields.Char(string="Version")
    b2b_language = fields.Char(string="Language")
