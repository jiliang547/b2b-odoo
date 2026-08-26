from odoo import _, api, models
from odoo.exceptions import AccessError


class B2BPriceWriteMixin(models.AbstractModel):
    _name = "b2b.price.write.mixin"
    _description = "B2B Sensitive Price Write Policy"

    @api.model
    def _b2b_check_price_write(self):
        """One narrow server-side policy for all native price models."""
        if self.env.su or self.env.user.has_group("base.group_system"):
            return
        if not self.env.user.has_group("b2b_core.group_b2b_special_price_manager"):
            raise AccessError(_("You are not authorized to maintain B2B prices."))

    @api.model
    def _b2b_check_price_only_product_write(self, vals, allowed_fields):
        """Prevent a price-only role from using its narrow ACL to edit products."""
        if self.env.su or self.env.user.has_group("base.group_system"):
            return
        if not self.env.user.has_group("b2b_core.group_b2b_special_price_manager"):
            return
        if self.env.user.has_group("product.group_product_manager"):
            return
        forbidden_fields = set(vals) - set(allowed_fields)
        if forbidden_fields:
            raise AccessError(_(
                "B2B Special Price Managers can update prices, but not product master data."
            ))


class ProductPricelist(models.Model):
    _name = "product.pricelist"
    _inherit = ["product.pricelist", "b2b.price.write.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        self._b2b_check_price_write()
        return super().create(vals_list)

    def write(self, vals):
        self._b2b_check_price_write()
        return super().write(vals)

    def unlink(self):
        self._b2b_check_price_write()
        return super().unlink()


class ProductPricelistItem(models.Model):
    _name = "product.pricelist.item"
    _inherit = ["product.pricelist.item", "b2b.price.write.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        self._b2b_check_price_write()
        return super().create(vals_list)

    def write(self, vals):
        self._b2b_check_price_write()
        return super().write(vals)

    def unlink(self):
        self._b2b_check_price_write()
        return super().unlink()
