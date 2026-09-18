import logging
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    tickets = env['helpdesk.ticket'].with_context(active_test=False).search([('b2b_request_type', '!=', False)])
    for ticket in tickets:
        if ticket.b2b_service_step:
            continue
        order = ticket.b2b_sale_order_id
        if not order:
            logging.getLogger(__name__).warning('Service ticket %s needs manual order/company review', ticket.id)
            continue
        team = env['helpdesk.team']._b2b_team_for_company(order.company_id)
        # Preserve historical closure reasons. Do not relabel an old cancelled
        # case as a successful repair or invent shipping evidence.
        old_stage = ticket.stage_id
        step = 'submitted' if old_stage == env.ref('helpdesk.stage_new') else 'review'
        stage = old_stage if old_stage.fold else env.ref('b2b_website.service_' + step)
        if stage not in team.stage_ids:
            team.stage_ids = [(4, stage.id)]
        ticket.with_context(tracking_disable=True, mail_notrack=True).write({
            'team_id': team.id, 'stage_id': stage.id,
            'product_id': ticket.b2b_product_id.id,
        })
        ticket.message_subscribe(partner_ids=ticket.partner_id.ids)
