from odoo import _, api, models
from odoo.exceptions import AccessError, ValidationError


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
        if not self.env.context.get("b2b_system_pricing"):
            self._b2b_check_price_write()
        records = super().create(vals_list)
        records._b2b_touch_pricing_partners(sync=True)
        return records

    def write(self, vals):
        if not self.env.context.get("b2b_system_pricing"):
            self._b2b_check_price_write()
        if "currency_id" in vals and self._b2b_pricing_partners():
            raise ValidationError(_(
                "Remove this pricelist from customer-type and company pricing before changing its currency."
            ))
        if vals.get("active") is False and self.env[
            "b2b.customer.type.pricelist"
        ].sudo().search_count([
            ("pricelist_id", "in", self.ids),
            ("active", "=", True),
        ], limit=1):
            raise ValidationError(_(
                "Deactivate the customer-type base mapping before archiving its pricelist."
            ))
        sources = self.filtered(lambda pricelist: not pricelist.b2b_effective_partner_id)
        result = super().write(vals)
        sources._b2b_touch_pricing_partners(
            sync=bool({"currency_id", "website_id", "active"} & set(vals))
        )
        return result

    def unlink(self):
        self._b2b_check_price_write()
        partners = self._b2b_pricing_partners()
        result = super().unlink()
        partners._b2b_sync_effective_pricelists()
        return result


class ProductPricelistItem(models.Model):
    _name = "product.pricelist.item"
    _inherit = ["product.pricelist.item", "b2b.price.write.mixin"]

    @api.model_create_multi
    def create(self, vals_list):
        self._b2b_check_price_write()
        records = super().create(vals_list)
        records.pricelist_id._b2b_touch_pricing_partners()
        return records

    def write(self, vals):
        self._b2b_check_price_write()
        pricelists = self.pricelist_id
        result = super().write(vals)
        (pricelists | self.pricelist_id)._b2b_touch_pricing_partners()
        return result

    def unlink(self):
        self._b2b_check_price_write()
        pricelists = self.pricelist_id
        result = super().unlink()
        pricelists._b2b_touch_pricing_partners()
        return result
