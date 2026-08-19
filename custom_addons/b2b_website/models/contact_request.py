import uuid

from odoo import _, api, fields, models


class B2BContactRequest(models.Model):
    _name = "b2b.contact.request"
    _description = "B2B Contact Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"

    name = fields.Char(default=lambda self: _("New"), readonly=True, copy=False, index=True)
    access_token = fields.Char(default=lambda self: str(uuid.uuid4()), readonly=True, copy=False, index=True)
    request_type = fields.Selection(
        [
            ("sales", "Sales Inquiry"),
            ("technical", "Technical Support"),
            ("sample", "Sample Request"),
            ("partnership", "Partnership"),
            ("company_change", "Company Change"),
            ("user_change", "Company User Change"),
            ("other", "Other"),
        ],
        required=True,
        default="sales",
        tracking=True,
    )
    state = fields.Selection(
        [
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
        ],
        required=True,
        default="new",
        tracking=True,
    )
    subject = fields.Char(required=True)
    contact_name = fields.Char(required=True)
    email = fields.Char(required=True)
    phone = fields.Char()
    company_name = fields.Char()
    message = fields.Text(required=True)
    partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    commercial_partner_id = fields.Many2one("res.partner", index=True, ondelete="set null")
    website_id = fields.Many2one("website", required=True, ondelete="restrict")
    source_url = fields.Char()
    assigned_user_id = fields.Many2one("res.users", tracking=True)

    requested_company_name = fields.Char()
    requested_vat = fields.Char(string="Requested Tax ID")
    requested_email = fields.Char()
    requested_phone = fields.Char()
    requested_street = fields.Char()
    requested_street2 = fields.Char()
    requested_city = fields.Char()
    requested_zip = fields.Char()
    requested_country_id = fields.Many2one("res.country")

    _access_token_unique = models.Constraint(
        "UNIQUE (access_token)", "Contact request access tokens must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code(
                    "b2b.contact.request"
                ) or _("New")
            partner = self.env["res.partner"].browse(vals.get("partner_id")).exists()
            if partner:
                vals["commercial_partner_id"] = partner.commercial_partner_id.id
        records = super().create(vals_list)
        for record in records:
            if record.partner_id:
                record.message_subscribe(partner_ids=record.partner_id.ids)
        return records

    def action_start(self):
        self.write({"state": "in_progress", "assigned_user_id": self.env.user.id})

    def action_resolve(self):
        self.write({"state": "resolved"})

    def action_close(self):
        self.write({"state": "closed"})
