from odoo import fields, models


class B2BCustomerSegment(models.Model):
    _name = "b2b.customer.segment"
    _description = "B2B Customer Segment"
    _order = "priority, sequence, name, id"

    name = fields.Char(required=True, translate=True, index="trigram")
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    priority = fields.Integer(
        default=100,
        help="Lower values take precedence when a deterministic segment order is required.",
    )
    description = fields.Text(translate=True)
    partner_count = fields.Integer(compute="_compute_partner_count")

    _name_unique = models.Constraint("UNIQUE (name)", "Customer segment names must be unique.")

    def _compute_partner_count(self):
        grouped = self.env["res.partner"]._read_group(
            [("b2b_segment_ids", "in", self.ids)],
            groupby=["b2b_segment_ids"],
            aggregates=["__count"],
        )
        counts = {segment.id: count for segment, count in grouped}
        for segment in self:
            segment.partner_count = counts.get(segment.id, 0)

    def action_view_partners(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("base.action_partner_form")
        action["domain"] = [("b2b_segment_ids", "in", self.id)]
        return action
