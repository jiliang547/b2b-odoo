from odoo import fields, models
from odoo.fields import Domain


class Website(models.Model):
    _inherit = "website"

    b2b_price_display_mode = fields.Selection(
        [
            ("always", "Show Using the Current Website Pricelist"),
            ("authenticated", "Authenticated Customers Only"),
            ("approved", "Approved B2B Customers Only"),
            ("never", "Never Show a Numeric Price"),
        ],
        required=True,
        default="approved",
    )
    b2b_guest_price_state = fields.Selection(
        [
            ("login", "Login to View Price"),
            ("contact", "Contact Us"),
            ("quote", "Request Quote"),
        ],
        required=True,
        default="login",
    )
    b2b_no_price_state = fields.Selection(
        [("contact", "Contact Us"), ("quote", "Request Quote")],
        required=True,
        default="quote",
    )
    b2b_require_approved_checkout = fields.Boolean(default=True)
    b2b_require_approved_sample = fields.Boolean(default=True)

    def sale_product_domain(self):
        domain = super().sale_product_domain()
        if self.env.context.get("b2b_skip_visibility"):
            return domain
        policy = self.env["b2b.product.service"].visibility_policy_domain()
        return Domain.AND([domain, policy])
