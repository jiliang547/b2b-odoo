from odoo import api, fields, models
from odoo.exceptions import AccessError


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
    b2b_publish_in_partner_hub = fields.Boolean(
        string="Publish Variant Document in Partner Hub",
        help="Publish a document attached to a specific product variant without changing Odoo's native product-page constraint.",
    )

    def _b2b_is_limited_marketing_editor(self):
        return (
            not self.env.su
            and self.env.user.has_group("b2b_core.group_b2b_marketing_media")
            and not self.env.user.has_group("product.group_product_manager")
        )

    def _b2b_check_marketing_document_target(self, res_model, res_id):
        if res_model not in ("product.template", "product.product") or not res_id:
            raise AccessError("Marketing documents must be attached to an existing product.")
        product = self.env[res_model].browse(res_id).exists()
        if not product:
            raise AccessError("The target product does not exist.")
        product.check_access("read")

    @api.model_create_multi
    def create(self, vals_list):
        if not self._b2b_is_limited_marketing_editor():
            return super().create(vals_list)
        for vals in vals_list:
            self._b2b_check_marketing_document_target(vals.get("res_model"), vals.get("res_id"))
        # Odoo's attachment layer requires write access on the attached record.
        # Marketing intentionally has read-only product access, so elevate only
        # after validating that every attachment targets a readable product.
        return super(ProductDocument, self.sudo()).create(vals_list).with_env(self.env)

    def write(self, vals):
        if not self._b2b_is_limited_marketing_editor():
            return super().write(vals)
        if {"res_model", "res_id", "ir_attachment_id"} & set(vals):
            raise AccessError("Marketing users cannot move documents between products.")
        for document in self:
            self._b2b_check_marketing_document_target(document.res_model, document.res_id)
        return super(ProductDocument, self.sudo()).write(vals)

    def unlink(self):
        if not self._b2b_is_limited_marketing_editor():
            return super().unlink()
        for document in self:
            self._b2b_check_marketing_document_target(document.res_model, document.res_id)
        return super(ProductDocument, self.sudo()).unlink()
