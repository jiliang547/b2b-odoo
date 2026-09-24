from odoo import models


class Registration(models.Model):
    _inherit = 'b2b.registration.application'

    def _mail_get_companies(self, default=False):
        companies = super()._mail_get_companies(default=default)
        for application in self:
            seller = application.resolved_partner_id.b2b_selling_company_id
            if seller:
                companies[application.id] = seller
        return companies
