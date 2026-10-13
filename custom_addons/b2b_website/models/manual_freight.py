"""Optional website freight, using native delivery lines and negotiated quotes."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.translate import LazyTranslate

_native = LazyTranslate("website_sale")


class Website(models.Model):
    _inherit = "website"

    b2b_manual_freight = fields.Boolean(
        string="Add freight manually", default=True,
        help="Do not automatically charge a carrier at checkout. Staff can add freight to the quotation or an approved order revision.",
    )
    b2b_freight_product_id = fields.Many2one(
        "product.product", string="Freight Product",
        domain="[('type', '=', 'service'), ('sale_ok', '=', True), ('company_id', '=', False)]",
        help="Shared service product used by all selling companies. Configure its ERP material mapping before adding it to an ERP order.",
    )

    @api.constrains("b2b_freight_product_id")
    def _check_b2b_freight_product(self):
        for website in self:
            product = website.b2b_freight_product_id
            if product and (product.type != "service" or not product.sale_ok or product.company_id):
                raise ValidationError(_("Choose a shared, saleable service product for freight."))


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _b2b_freight_website(self):
        self.ensure_one()
        # Revisions intentionally have no website_id (not a cart or a second
        # ERP order). Read freight configuration from their original order.
        website = self.b2b_source_order_id.website_id if self.b2b_is_change_revision else self.website_id
        return website.sudo()

    def _b2b_uses_manual_freight(self):
        website = self._b2b_freight_website()
        return bool(website and website.b2b_manual_freight)

    def _get_preferred_delivery_method(self, available_delivery_methods):
        if self._b2b_uses_manual_freight():
            return self.env["delivery.carrier"]
        return super()._get_preferred_delivery_method(available_delivery_methods)

    def _allow_express_checkout(self):
        # Carrier-based express wallets cannot represent an unquoted freight
        # charge. Keep regular checkout and its native online payment methods.
        return not self._b2b_uses_manual_freight() and super()._allow_express_checkout()

    def _set_delivery_method(self, delivery_method, rate=None):
        # This is the website auto-rating hook. Native backend set_delivery_line
        # / Add Shipping remains available and is never suppressed.
        if not self._b2b_uses_manual_freight():
            return super()._set_delivery_method(delivery_method, rate=rate)

    def _verify_cart_after_update(self):
        if not self._b2b_uses_manual_freight():
            return super()._verify_cart_after_update()
        # Odoo 19's hook only reprices/removes carrier lines and caches quantity.
        # Never overwrite a negotiated freight amount on address/quantity edits.
        if request:
            request.session["website_sale_cart_quantity"] = self.cart_quantity

    def _check_cart_is_ready_to_be_paid(self):
        try:
            return super()._check_cart_is_ready_to_be_paid()
        except ValidationError as error:
            # Run the native chain first (including stock/quantity checks).
            # Only Odoo 19's two final carrier-selection errors are optional;
            # never swallow a stock, cart, ERP or payment validation error.
            carrier_errors = {
                self.env._(_native("No shipping method is selected.")),
                self.env._(_native("The delivery method is not compatible with your delivery address.")),
            }
            if not self._b2b_uses_manual_freight() or str(error) not in carrier_errors:
                raise

    def _b2b_clear_legacy_free_delivery(self):
        """Clean only an unpaid active draft cart; never migrate order history."""
        self.ensure_one()
        if (not self._b2b_uses_manual_freight() or self.state != "draft"
                or self.b2b_is_change_revision or self.invoice_ids
                or self.transaction_ids.filtered(lambda tx: tx.state not in ("cancel", "error"))
                or self.b2b_receipt_ids or getattr(self, "yonyou_key", False)):
            return
        free_lines = self.order_line.filtered(
            lambda line: line.is_delivery and not line.qty_invoiced
            and not line.price_unit and not line.price_total
        )
        if free_lines:
            free_lines.unlink()
            if not self.order_line.filtered("is_delivery"):
                self.write({"carrier_id": False, "recompute_delivery_price": False,
                            "pickup_location_data": {}})


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals.get("order_id")).exists()
            if (order and order._b2b_uses_manual_freight() and order._b2b_freight_website().b2b_freight_product_id
                    and not vals.get("display_type")
                    and vals.get("product_id") == order._b2b_freight_website().b2b_freight_product_id.id):
                vals["is_delivery"] = True
        return super().create(vals_list)

    def write(self, vals):
        if "product_id" not in vals:
            return super().write(vals)
        # Split the recordset because each website can choose a different SKU.
        for line in self:
            line_vals = dict(vals)
            order = line.order_id
            if order._b2b_uses_manual_freight():
                line_vals["is_delivery"] = bool(vals["product_id"] and
                    vals["product_id"] == order._b2b_freight_website().b2b_freight_product_id.id)
            super(SaleOrderLine, line).write(line_vals)
        return True
