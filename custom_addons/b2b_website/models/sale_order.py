from odoo import _, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _b2b_check_product_allowed(self, product_id):
        product = self.env["product.product"].browse(product_id).exists()
        if not product or not self.env["b2b.product.service"].is_visible(
            product.product_tmpl_id,
            partner=self.partner_id,
            website=self.website_id,
        ):
            raise AccessError(_("This product is not available to your Partner Hub account."))
        if not self.env.user._is_internal() and not self.env["b2b.product.service"].can_view_price(
            partner=self.partner_id, website=self.website_id
        ):
            raise AccessError(_("Ordering is not enabled for your Partner Hub account."))

    def _prepare_order_line_values(self, product_id, quantity, uom_id, **kwargs):
        self.ensure_one()
        if self.website_id and not self.env.user._is_internal():
            self._b2b_check_product_allowed(product_id)
        return super()._prepare_order_line_values(
            product_id, quantity, uom_id, **kwargs
        )

    def _verify_updated_quantity(
        self, order_line, product_id, new_qty, uom_id, **kwargs
    ):
        if self.website_id and not self.env.user._is_internal() and new_qty > 0:
            self._b2b_check_product_allowed(product_id)
        return super()._verify_updated_quantity(
            order_line, product_id, new_qty, uom_id, **kwargs
        )

    def action_confirm(self):
        for order in self.filtered("website_id"):
            if (
                order.website_id.b2b_require_approved_checkout
                and not order.partner_id.commercial_partner_id.b2b_approved
                and not self.env.user._is_internal()
            ):
                raise UserError(
                    _("Your Partner Hub account must be approved before submitting an order.")
                )
            for line in order.order_line.filtered(lambda item: not item.display_type):
                order._b2b_check_product_allowed(line.product_id.id)
        return super().action_confirm()
