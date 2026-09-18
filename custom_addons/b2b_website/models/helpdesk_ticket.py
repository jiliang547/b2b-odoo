from odoo import _, api, Command, fields, models
from odoo.exceptions import AccessError, ValidationError


SERVICE_STEPS = [
    ('submitted', 'Submitted'), ('review', 'Under Review'),
    ('approved', 'Awaiting Customer Shipment'), ('transit', 'Return in Transit'),
    ('received', 'Received'), ('processing', 'Inspection / Repair / Replacement'),
    ('shipped', 'Shipped Back'), ('completed', 'Completed'), ('rejected', 'Rejected'),
]


class HelpdeskStage(models.Model):
    _inherit = 'helpdesk.stage'

    b2b_service_step = fields.Selection(SERVICE_STEPS, string='Partner service step')


class HelpdeskTeam(models.Model):
    _inherit = 'helpdesk.team'

    b2b_partner_service = fields.Boolean(copy=False)

    @api.model
    def _b2b_team_for_company(self, company):
        # Team company is required natively and ticket.company_id is related.
        # Serialize provisioning; two first submissions must not create duplicates.
        self.env.cr.execute('SELECT id FROM res_company WHERE id = %s FOR UPDATE', [company.id])
        teams = self.sudo().with_company(company)
        team = teams.search([('b2b_partner_service', '=', True), ('company_id', '=', company.id)], limit=1)
        if not team:
            stages = [self.env.ref('b2b_website.service_' + step).id for step, _label in SERVICE_STEPS]
            team = teams.create({
                'name': 'Partner Support — %s' % company.name,
                'company_id': company.id, 'b2b_partner_service': True,
                'privacy_visibility': 'portal', 'allow_portal_ticket_closing': False,
                'stage_ids': [Command.set(stages)],
                'use_product_returns': True, 'use_product_replacements': True,
                'use_product_repairs': True,
            })
        return team


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
    b2b_model_number = fields.Char(string="Model Number", index=True)
    b2b_sale_order_id = fields.Many2one(
        "sale.order", string="Original Sales Order", ondelete="set null", index=True
    )
    b2b_contact_name = fields.Char(string="Submitted Contact")
    b2b_company_name = fields.Char(string="Submitted Company")
    b2b_contact_phone = fields.Char(string="Submitted Phone")
    b2b_contact_email = fields.Char(string="Submitted Email")
    b2b_submitted_at = fields.Datetime(string="Partner Submission Time", readonly=True)
    b2b_service_step = fields.Selection(related='stage_id.b2b_service_step', string='Service Progress')
    b2b_return_instructions = fields.Text(string='Return address and instructions', tracking=True)
    b2b_return_deadline = fields.Date(string='Return by', tracking=True)
    b2b_return_carrier = fields.Char(string='Customer return carrier', tracking=True)
    b2b_return_tracking = fields.Char(string='Customer return tracking', tracking=True)
    b2b_return_date = fields.Date(string='Customer shipped on', tracking=True)
    b2b_receipt_note = fields.Text(string='Receipt / inspection record', tracking=True)
    b2b_resolution_note = fields.Text(string='Customer resolution / rejection reason', tracking=True)
    b2b_outbound_carrier = fields.Char(string='Ship-back carrier', tracking=True)
    b2b_outbound_tracking = fields.Char(string='Ship-back tracking', tracking=True)
    b2b_outbound_date = fields.Date(string='Shipped back on', tracking=True)
    b2b_fulfilment_mode = fields.Selection([('external', 'External ERP / manual'), ('odoo', 'Odoo inventory')],
                                         compute='_compute_b2b_fulfilment_mode')

    @api.depends('b2b_sale_order_id')
    def _compute_b2b_fulfilment_mode(self):
        for ticket in self:
            order = ticket.b2b_sale_order_id
            ticket.b2b_fulfilment_mode = ('odoo' if getattr(order, 'b2b_fulfilment_mode', False) == 'odoo' else 'external')

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            if vals.get('b2b_request_type') and vals.get('b2b_sale_order_id'):
                order = self.env['sale.order'].sudo().browse(vals['b2b_sale_order_id']).exists()
                partner = self.env['res.partner'].sudo().browse(vals.get('partner_id')).exists()
                if not order or not partner or partner.commercial_partner_id != order.partner_id.commercial_partner_id:
                    raise ValidationError(_('The service customer must belong to the original order customer.'))
                team = self.env['helpdesk.team']._b2b_team_for_company(order.company_id)
                vals.update(team_id=team.id, stage_id=self.env.ref('b2b_website.service_submitted').id,
                            sale_order_id=order.id, product_id=vals.get('b2b_product_id'))
            prepared.append(vals)
        tickets = super().create(prepared)
        for ticket in tickets.filtered('b2b_request_type'):
            ticket.sudo().message_subscribe(partner_ids=ticket.partner_id.ids)
        return tickets

    def _b2b_check_staff(self):
        if not self.env.su and (self.env.user.share or not (
            self.env.user.has_group('b2b_core.group_b2b_after_sales')
            or self.env.user.has_group('b2b_core.group_b2b_manager')
            or self.env.user.has_group('helpdesk.group_helpdesk_manager')
        )):
            raise AccessError(_('After-sales permission is required.'))
        self.check_access('write')

    def _track_subtype(self, init_values):
        self.ensure_one()
        if self.b2b_service_step and 'stage_id' in init_values:
            # Retain native audit tracking; the public progress comment below
            # is the single customer notification, avoiding duplicate emails.
            return self.env.ref('mail.mt_note')
        return super()._track_subtype(init_values)

    def _b2b_validate_step(self, step):
        self.ensure_one()
        transitions = {
            'submitted': {'review', 'rejected'}, 'review': {'approved', 'rejected'},
            'approved': {'transit'}, 'transit': {'received'},
            'received': {'processing'}, 'processing': {'shipped'},
            'shipped': {'completed'}, 'completed': set(), 'rejected': set(),
        }
        if step == self.b2b_service_step:
            return
        if step not in transitions.get(self.b2b_service_step, set()):
            raise ValidationError(_('Complete the current service step before moving to the next stage.'))
        if step == 'approved' and not (self.b2b_return_instructions or '').strip():
            raise ValidationError(_('Enter the return address and instructions before approval.'))
        if step == 'rejected' and not (self.b2b_resolution_note or '').strip():
            raise ValidationError(_('Enter a customer-facing rejection reason first.'))
        if step == 'transit':
            if not all([self.b2b_return_carrier, self.b2b_return_tracking, self.b2b_return_date]):
                raise ValidationError(_('Enter the return carrier, tracking number and shipment date.'))
            if self.b2b_return_date > fields.Date.today():
                raise ValidationError(_('Shipment date cannot be in the future.'))
        if step == 'received':
            if not (self.b2b_receipt_note or '').strip():
                raise ValidationError(_('Record the received quantity and condition first.'))
            if self.b2b_fulfilment_mode == 'odoo':
                returns = self.picking_ids.filtered(lambda p: not p.is_replacement and p.state != 'cancel')
                if not returns or any(p.state != 'done' for p in returns):
                    raise ValidationError(_('Validate all linked native return receipts first.'))
        if step == 'shipped':
            if not all([self.b2b_outbound_carrier, self.b2b_outbound_tracking, self.b2b_outbound_date, self.b2b_resolution_note]):
                raise ValidationError(_('Enter the resolution, ship-back carrier, tracking number and date first.'))
            if self.b2b_outbound_date > fields.Date.today():
                raise ValidationError(_('Shipment date cannot be in the future.'))
            if self.b2b_fulfilment_mode == 'odoo':
                deliveries = self.picking_ids.filtered(lambda p: p.is_replacement and p.state != 'cancel')
                if not deliveries or any(p.state != 'done' for p in deliveries):
                    raise ValidationError(_('Validate all linked outbound deliveries first.'))
                repairs = self.repair_ids.filtered(lambda r: r.state != 'cancel')
                if self.b2b_request_type == 'repair' and (not repairs or any(r.state != 'done' for r in repairs)):
                    raise ValidationError(_('Complete all linked native repairs first.'))

    def write(self, vals):
        managed = self.filtered(lambda t: t.b2b_request_type and t.b2b_service_step)
        protected = {key for key in vals if key.startswith('b2b_')} | ({'stage_id', 'team_id', 'partner_id'} & vals.keys())
        if managed and protected:
            managed._b2b_check_staff()
        if managed and {'team_id', 'partner_id', 'b2b_sale_order_id', 'b2b_request_type', 'b2b_product_id'} & vals.keys():
            for ticket in managed:
                for name in {'team_id', 'partner_id', 'b2b_sale_order_id', 'b2b_request_type', 'b2b_product_id'} & vals.keys():
                    current = ticket[name].id if name.endswith('_id') else ticket[name]
                    if vals[name] != current:
                        raise ValidationError(_('An active service request keeps its original customer, order and sales company.'))
        changed = managed.filtered(lambda t: 'stage_id' in vals and t.stage_id.id != vals['stage_id'])
        if 'stage_id' in vals:
            step = self.env['helpdesk.stage'].browse(vals['stage_id']).b2b_service_step
            for ticket in changed:
                ticket._b2b_validate_step(step)
        result = super().write(vals)
        if 'stage_id' in vals:
            for ticket in changed:
                ticket.message_post(body=_('Service progress: %s', ticket.stage_id.name),
                                    message_type='comment', subtype_xmlid='mail.mt_comment')
        return result

    def _b2b_step(self, step):
        self.ensure_one()
        self._b2b_check_staff()
        self.env.cr.execute('SELECT id FROM helpdesk_ticket WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        self.write({'stage_id': self.env.ref('b2b_website.service_' + step).id})
        return True

    def action_b2b_review(self):
        return self._b2b_step('review')

    def action_b2b_approve(self):
        return self._b2b_step('approved')

    def action_b2b_reject(self):
        return self._b2b_step('rejected')

    def action_b2b_received(self):
        return self._b2b_step('received')

    def action_b2b_process(self):
        return self._b2b_step('processing')

    def action_b2b_ship(self):
        self._b2b_check_staff()
        self.ensure_one()
        if self.b2b_fulfilment_mode == 'odoo':
            delivery = self.picking_ids.filtered(lambda p: p.is_replacement and p.state == 'done').sorted('id')[-1:]
            if delivery and delivery.carrier_tracking_ref:
                self.write({'b2b_outbound_carrier': delivery.carrier_id.name or self.b2b_outbound_carrier,
                            'b2b_outbound_tracking': delivery.carrier_tracking_ref,
                            'b2b_outbound_date': fields.Date.to_date(delivery.date_done)})
        return self._b2b_step('shipped')

    def action_b2b_complete(self):
        return self._b2b_step('completed')

    def _b2b_submit_tracking(self, carrier, tracking, shipped_on):
        self.ensure_one()
        if self.b2b_service_step != 'approved':
            raise ValidationError(_('Return shipping details can only be submitted after approval. Refresh this page to see the latest progress.'))
        if not carrier.strip() or not tracking.strip() or len(carrier) > 120 or len(tracking) > 160:
            raise ValidationError(_('Enter a valid carrier and tracking number.'))
        self.write({'b2b_return_carrier': carrier.strip(), 'b2b_return_tracking': tracking.strip(), 'b2b_return_date': shipped_on})
        self._b2b_step('transit')

    def action_repair_order_form(self):
        if any(t.b2b_service_step and t.b2b_fulfilment_mode == 'external' for t in self):
            raise ValidationError(_('Record the repair result from your warehouse or ERP in Receipt and Resolution.'))
        return super().action_repair_order_form()

    def action_create_replacement(self):
        if any(t.b2b_service_step and t.b2b_fulfilment_mode == 'external' for t in self):
            raise ValidationError(_('Record the confirmed dispatch in Ship Back, then confirm shipment.'))
        return super().action_create_replacement()
