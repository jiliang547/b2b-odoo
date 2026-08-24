from odoo import fields, models


class B2BFaqCategory(models.Model):
    _name = "b2b.faq.category"
    _description = "Partner Hub FAQ Category"
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    website_id = fields.Many2one("website", ondelete="cascade")
    item_ids = fields.One2many("b2b.faq.item", "category_id", string="Questions")


class B2BFaqItem(models.Model):
    _name = "b2b.faq.item"
    _description = "Partner Hub FAQ Item"
    _order = "sequence, id"

    question = fields.Char(required=True, translate=True)
    answer = fields.Html(required=True, translate=True, sanitize=True)
    category_id = fields.Many2one(
        "b2b.faq.category", required=True, ondelete="restrict", index=True
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    published = fields.Boolean(default=True)
    website_id = fields.Many2one(
        "website", related="category_id.website_id", store=True, readonly=True
    )
    action_label = fields.Char(translate=True)
    action_url = fields.Char()
