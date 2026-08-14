from odoo import fields, models


class HelpdeskTicket(models.Model):
    _inherit = "helpdesk.ticket"

    b2b_request_type = fields.Selection(
        [("repair", "Repair"), ("replacement", "Replacement")],
        string="Partner Request Type",
        index=True,
    )
    b2b_product_id = fields.Many2one(
        "product.product", string="Partner Product", ondelete="restrict", index=True
    )
    b2b_serial_number = fields.Char(string="Serial Number", index=True)
    b2b_sale_order_id = fields.Many2one(
        "sale.order", string="Original Sales Order", ondelete="set null", index=True
    )
    b2b_contact_name = fields.Char(string="Submitted Contact")
    b2b_company_name = fields.Char(string="Submitted Company")
    b2b_contact_phone = fields.Char(string="Submitted Phone")
    b2b_contact_email = fields.Char(string="Submitted Email")
    b2b_submitted_at = fields.Datetime(string="Partner Submission Time", readonly=True)
