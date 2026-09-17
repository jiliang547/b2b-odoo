"""Customer-first backend defaults; source documents remain authoritative."""
from odoo import api, fields, models, _
from odoo.exceptions import AccessError, ValidationError


class Partner(models.Model):
    _inherit = 'res.partner'

    def _b2b_backend_seller(self):
        self.ensure_one()
        self.check_access('read')
        customer = self.sudo().commercial_partner_id
        brand = customer.b2b_account_brand_id
        seller = customer.b2b_selling_company_id or brand.b2b_selling_company_id
        if not seller:
            return self.env['res.company']
        if not brand or brand.b2b_selling_company_id != seller:
            raise ValidationError(_('Assign an account brand matching this customer’s selling company first.'))
        if not self.env.su and seller.id not in self.env.user.company_ids.ids:
            raise AccessError(_('You do not have permission to operate this customer’s selling company.'))
        if not self.env.su and seller.id not in self.env.companies.ids:
            raise ValidationError(_('Select this customer’s selling company in the top-right company selector. You may keep all authorized companies selected.'))
        return self.env['res.company'].browse(seller.id)

    def _b2b_backend_website(self, website=None):
        seller = self._b2b_backend_seller()
        if not seller:
            return self.env['website']
        if website:
            candidates = website
        else:
            candidates = self.env['website'].search([('b2b_selling_company_ids', 'in', seller.ids)])
        if len(candidates) != 1:
            raise ValidationError(_('Select the Partner Hub Website for this quotation. There must be one explicitly selected or uniquely configured website.'))
        if candidates._b2b_configured_seller(self) != seller:
            raise ValidationError(_('The selected website does not match the customer’s selling company.'))
        return candidates


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    b2b_backend_order = fields.Boolean(copy=False, readonly=True)

    @api.onchange('partner_id', 'website_id')
    def _onchange_b2b_backend_customer(self):
        if self._origin.id or not self.partner_id or self.b2b_is_change_revision or not self.env.user._is_internal():
            return
        seller = self.partner_id._b2b_backend_seller()
        if not seller:
            if self.b2b_backend_order:
                raise ValidationError(_('Create a new quotation for a customer without a Partner Hub brand assignment.'))
            return
        if self.order_line and self.company_id != seller:
            raise ValidationError(_('Choose the customer before adding products. Create a new quotation to change its selling company.'))
        website = self.partner_id._b2b_backend_website(self.website_id)
        self.company_id = seller
        self.website_id = website
        self.b2b_backend_order = True
        self._compute_pricelist_id()
        self._compute_payment_term_id()
        self._compute_fiscal_position_id()
        if self.team_id.company_id and self.team_id.company_id != seller:
            self.team_id = False

    @api.depends('partner_id', 'company_id', 'website_id', 'b2b_backend_order')
    def _compute_pricelist_id(self):
        super()._compute_pricelist_id()
        for order in self.filtered(lambda o: o.b2b_backend_order and o.state == 'draft' and o.partner_id and o.website_id):
            candidates = order._b2b_backend_prices()
            order.pricelist_id = candidates.filtered(lambda p: p == order.pricelist_id)[:1] or candidates[:1]

    def _b2b_backend_prices(self):
        self.ensure_one()
        return self.env['product.pricelist'].search([
            ('active', '=', True), ('website_id', '=', self.website_id.id),
            ('b2b_effective_partner_id', '=', self.partner_id.commercial_partner_id.id),
            ('company_id', 'in', [False, self.company_id.id]),
        ])

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        for original in vals_list:
            vals = dict(original)
            customer = self.env['res.partner'].browse(vals.get('partner_id'))
            # The native form marks customer-first quotations on onchange.
            # Unmarked imports, internal supply and legacy native creation
            # retain their explicit original workflow, even for Hub contacts.
            backend = self.env.user._is_internal() and not vals.get('b2b_is_change_revision') and vals.get('b2b_backend_order')
            if backend and customer and customer._b2b_backend_seller():
                website = customer._b2b_backend_website(self.env['website'].browse(vals.get('website_id')))
                seller = customer._b2b_backend_seller()
                if vals.get('company_id') and vals['company_id'] != seller.id:
                    raise ValidationError(_('This quotation belongs to the customer’s selling company. Re-select the customer before saving.'))
                vals.update(website_id=website.id, company_id=seller.id, b2b_backend_order=True)
                vals.setdefault('user_id', self.env.user.id)
                if vals.get('team_id') and self.env['crm.team'].browse(vals['team_id']).company_id not in (seller, self.env['res.company']):
                    vals['team_id'] = False
            else:
                vals['b2b_backend_order'] = False
            prepared.append(vals)
        orders = super().create(prepared)
        for order in orders.filtered('b2b_backend_order'):
            if not order.pricelist_id or order.pricelist_id not in order._b2b_backend_prices():
                raise ValidationError(_('Configure and select this customer’s effective website pricelist before saving the quotation.'))
            order._b2b_start_collection()
        return orders

    def write(self, vals):
        if 'b2b_backend_order' in vals:
            raise ValidationError(_('The quotation origin cannot be changed.'))
        if vals.get('partner_id'):
            customer = self.env['res.partner'].browse(vals['partner_id']).commercial_partner_id
            if any(order.partner_id.commercial_partner_id != customer for order in self.filtered('b2b_backend_order')):
                raise ValidationError(_('Create a new quotation for a different customer. Existing collection instructions must not be reassigned.'))
        result = super().write(vals)
        if {'pricelist_id', 'partner_id'}.intersection(vals):
            for order in self.filtered('b2b_backend_order'):
                if order.pricelist_id not in order._b2b_backend_prices():
                    raise ValidationError(_('Select an effective pricelist belonging to this customer and website.'))
        return result


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.model_create_multi
    def create(self, vals_list):
        company_id = self.env.context.get('b2b_bank_setup_company_id')
        if not company_id:
            return super().create(vals_list)
        # The web client can restore the global company context. Native journal
        # creation fills company_id before ORM defaults, so default_company_id
        # alone is not sufficient when the readonly field is omitted on save.
        company = self.env['res.company'].browse(company_id).exists()
        if not company or company not in self.env.user.company_ids:
            raise AccessError(_('You do not have access to this bank company.'))
        values = [dict(vals) for vals in vals_list]
        for vals in values:
            if vals.get('company_id') and vals['company_id'] != company.id:
                raise ValidationError(_('The journal company must match Bank Configuration Company. Return to Business Setup to select another company.'))
            vals['company_id'] = company.id
        return super(AccountJournal, self.with_company(company)).create(values)


class AccountMove(models.Model):
    _inherit = 'account.move'

    @api.onchange('partner_id')
    def _onchange_b2b_customer_company(self):
        # Suggestions only on empty, standalone customer invoices. Invoices
        # from orders, reversals, imports and posted documents keep their source.
        if (self._origin.id or self.move_type != 'out_invoice' or not self.partner_id
                or self.invoice_line_ids or self.invoice_origin or self.reversed_entry_id
                or self.env.context.get('default_company_id') or self.env.context.get('default_journal_id')):
            return
        seller = self.partner_id._b2b_backend_seller()
        if seller and self.company_id != seller:
            self.company_id = seller
            self.journal_id = self.with_company(seller)._search_default_journal()


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    @api.onchange('partner_id')
    def _onchange_b2b_customer_company(self):
        # Refunds, vendor payments and source-driven registration must not be
        # redirected using a customer's newer assignment.
        if (self._origin.id or self.partner_type != 'customer' or self.payment_type != 'inbound'
                or not self.partner_id or self.move_id or self.b2b_evidence_id
                or self.env.context.get('default_company_id') or self.env.context.get('default_journal_id')
                or self.env.context.get('active_model') == 'account.move'):
            return
        seller = self.partner_id._b2b_backend_seller()
        if seller and self.company_id != seller:
            self.company_id = seller
            self._compute_journal_id()
        if seller:
            journals = self.partner_id.sudo().commercial_partner_id.b2b_account_brand_id.b2b_collection_journal_ids.filtered(
                lambda j: j.company_id == seller and j.active and j.bank_account_id
                and (j.currency_id or seller.currency_id) == self.currency_id)
            if len(journals) == 1:
                self.journal_id = self.env['account.journal'].browse(journals.id)


class OrderChange(models.Model):
    _inherit = 'b2b.order.change.request'

    def action_b2b_open_bank_refund(self):
        self.ensure_one()
        self.check_access('write')
        self._check_finance()
        if self.refund_payment_id:
            self.refund_payment_id.check_access('read')
            return {'type': 'ir.actions.act_window', 'res_model': 'account.payment',
                    'view_mode': 'form', 'res_id': self.refund_payment_id.id, 'target': 'new'}
        if self.state != 'finance_review' or not self.collection_adjustment or self.refund_amount <= 0 or self.refund_transaction_id:
            raise ValidationError(_('Use this action only for a bank refund awaiting finance review.'))
        order = self.order_id
        return {'type': 'ir.actions.act_window', 'name': _('Register Actual Bank Refund'),
                'res_model': 'account.payment', 'view_mode': 'form', 'target': 'new',
                'context': dict(self.env.context, default_company_id=order.company_id.id,
                    default_partner_id=self.commercial_partner_id.id, default_partner_type='customer',
                    default_payment_type='outbound', default_currency_id=self.currency_id.id,
                    default_amount=self.refund_amount, default_journal_id=order.b2b_receiving_journal_id.id,
                    default_memo='%s / %s' % (order.name, self.name))}
