from odoo import fields, models


class B2BProductBrand(models.Model):
    _name = "b2b.product.brand"
    _description = "B2B Product Brand"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, index="trigram")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    product_ids = fields.One2many(
        "product.template", "b2b_brand_id", string="Products", groups="base.group_user"
    )
    product_count = fields.Integer(compute="_compute_product_count", groups="base.group_user")

    _name_unique = models.Constraint("UNIQUE (name)", "Product brand names must be unique.")

    def _compute_product_count(self):
        grouped = self.env["product.template"]._read_group(
            [("b2b_brand_id", "in", self.ids)],
            groupby=["b2b_brand_id"],
            aggregates=["__count"],
        )
        counts = {brand.id: count for brand, count in grouped}
        for brand in self:
            brand.product_count = counts.get(brand.id, 0)


class B2BProductApplication(models.Model):
    _name = "b2b.product.application"
    _description = "B2B Product Application"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True, index="trigram")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    description = fields.Text(translate=True)
    product_ids = fields.Many2many(
        "product.template",
        "b2b_product_application_rel",
        "application_id",
        "product_tmpl_id",
        string="Products",
        groups="base.group_user",
    )
    product_count = fields.Integer(compute="_compute_product_count", groups="base.group_user")

    _name_unique = models.Constraint(
        "UNIQUE (name)", "Product application names must be unique."
    )

    def _compute_product_count(self):
        grouped = self.env["product.template"]._read_group(
            [("b2b_application_ids", "in", self.ids)],
            groupby=["b2b_application_ids"],
            aggregates=["__count"],
        )
        counts = {application.id: count for application, count in grouped}
        for application in self:
            application.product_count = counts.get(application.id, 0)
