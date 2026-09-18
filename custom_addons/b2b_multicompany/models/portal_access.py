"""Keep native portal ownership rules while allowing routed customer orders."""
from odoo import api, models
from odoo.fields import Domain


class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    def _compute_domain(self, model_name, mode='read'):
        domain = super()._compute_domain(model_name, mode)
        user = self.env.user
        if mode != 'read' or model_name not in ('sale.order', 'sale.order.line', 'helpdesk.ticket') or not user.share or user._is_public():
            return domain
        if model_name == 'helpdesk.ticket':
            own_ticket = Domain.AND([
                Domain('b2b_request_type', '!=', False),
                Domain('partner_id.commercial_partner_id', '=', user.partner_id.commercial_partner_id.id),
            ])
            allowed = set(self.env.companies.ids) | {False}
            def allow_own_ticket(condition):
                if condition.field_expr == 'company_id' and condition.operator == 'in' and set(condition.value) == allowed:
                    return condition | own_ticket
                return condition
            # Preserve native follower and portal-team visibility rules.
            return domain.map_conditions(allow_own_ticket)
        prefix = 'order_id.' if model_name == 'sale.order.line' else ''
        own_routed = Domain.AND([
            Domain(prefix + 'b2b_routed_company', '=', True),
            Domain(prefix + 'partner_id.commercial_partner_id', '=', user.partner_id.commercial_partner_id.id),
            Domain(prefix + 'b2b_is_change_revision', '=', False),
        ])
        allowed = set(self.env.companies.ids)

        def allow_own_routed(condition):
            # Extend only the native active-company gate. All other native
            # and custom portal record rules remain intersected. No sudo,
            # no change to the visitor's company access, and no write grant.
            if condition.field_expr == 'company_id' and (
                condition.operator == 'in' and set(condition.value) == allowed
                or condition.operator == '=' and {condition.value} == allowed
            ):
                return condition | own_routed
            return condition

        return domain.map_conditions(allow_own_routed)
