from odoo import SUPERUSER_ID, _, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _b2b_is_trusted_payment_confirmation(self):
        self.ensure_one()
        transaction_ids = self.env.context.get("b2b_payment_transaction_ids") or []
        if not transaction_ids:
            return False
        transactions = self.env["payment.transaction"].sudo().browse(transaction_ids).exists()
        return any(
            self in transaction.sale_order_ids
            and transaction.partner_id.commercial_partner_id
            == self.partner_id.commercial_partner_id
            for transaction in transactions
        )

    def _b2b_check_product_allowed(self, product_id):
        self.ensure_one()
        product = self.env["product.product"].browse(product_id).exists()
        service = self.env["b2b.product.service"]
        if self._b2b_is_trusted_payment_confirmation():
            # The transaction/order/customer relationship was verified above.
            # Change the policy evaluator's user rather than globally bypassing
            # the catalog rules for normal portal requests.
            service = service.with_user(SUPERUSER_ID)
            product = product.with_user(SUPERUSER_ID)
        if not product or not service.is_visible(
            product.product_tmpl_id,
            partner=self.partner_id,
            website=self.website_id,
        ):
            raise AccessError(_("This product is not available to your Partner Hub account."))
        if not self.env.user._is_internal() and not service.can_view_price(
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
            for line in order.order_line.filtered(
                lambda item: not item.display_type and not item.is_delivery
            ):
                order._b2b_check_product_allowed(line.product_id.id)
        return super().action_confirm()
