"""Small shared form component, not a second ERP personnel directory."""
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from .config import MANAGER, check_role, notification

PRINCIPAL_INPUTS = {'yonyou_salesperson', 'yonyou_department'}


class Principal(models.AbstractModel):
    _name = 'b2b.yonyou.principal.mixin'
    _description = 'ERP Customer Principal Selection'

    yonyou_salesperson = fields.Char(string='ERP Salesperson Code', groups=MANAGER, copy=False)
    yonyou_department = fields.Char(string='ERP Department Code', groups=MANAGER, copy=False)
    yonyou_principal_snapshot = fields.Json(readonly=True, groups=MANAGER, copy=False)
    yonyou_principal_result = fields.Char(string='Salesperson Verification Result', readonly=True, groups=MANAGER, copy=False)
    yonyou_salesperson_name = fields.Char(string='ERP Salesperson Name', compute='_compute_principal', groups=MANAGER)
    yonyou_department_name = fields.Char(string='ERP Department Name', compute='_compute_principal', groups=MANAGER)
    yonyou_principal_status = fields.Selection([('unverified', 'Not Verified'), ('verified', 'Verified'),
        ('stale', 'Changed — Verify Again')], string='Salesperson Verification', compute='_compute_principal', groups=MANAGER)

    def _principal_locked(self):
        return False

    def _principal_fingerprint(self):
        company = self._principal_company()
        config = self._erp_connection()
        return hashlib.sha256(json.dumps([self.yonyou_salesperson, self.yonyou_department,
            company.id, config._org(company), config.revision]).encode()).hexdigest()

    def _principal_company(self):
        return self._erp_company()

    @api.depends('yonyou_salesperson', 'yonyou_department', 'yonyou_principal_snapshot')
    def _compute_principal(self):
        for rec in self:
            snapshot = rec.yonyou_principal_snapshot or {}
            # Don't query ERP, or require a company, merely to display a form.
            valid = bool(snapshot) and snapshot.get('fingerprint') == rec._principal_fingerprint()
            rec.yonyou_principal_status = 'verified' if valid else 'stale' if snapshot else 'unverified'
            rec.yonyou_salesperson_name = snapshot.get('salesperson_name') if valid else False
            rec.yonyou_department_name = snapshot.get('department_name') if valid else False

    def _store_principal(self, result):
        self._erp_store({'yonyou_salesperson': result.get('salesperson'),
                         'yonyou_department': result.get('department')})
        if not result.get('salesperson') or not result.get('department'):
            self._erp_store({'yonyou_principal_snapshot': False,
                'yonyou_principal_result': _('Configure one default salesperson and department in the ERP customer using organization, then Verify & Refresh.')})
            return
        result = dict(result, fingerprint=self._principal_fingerprint())
        self._erp_store({'yonyou_principal_snapshot': result,
            'yonyou_principal_result': _('%(person)s — %(name)s | %(department)s — %(dept_name)s | ERP organization %(org)s',
                person=result.get('salesperson') or '?', name=result.get('salesperson_name') or '',
                department=result.get('department') or '?', dept_name=result.get('department_name') or '', org=result['org'])})

    def _verify_principal(self):
        self.ensure_one()
        company = self._erp_company()
        if not company:
            raise UserError(_('Select a brand linked to a selling company first.'))
        if not self.env.su and company not in self.env.user.company_ids:
            raise UserError(_('You do not have access to this selling company.'))
        result = self.env['b2b.yonyou.client']._principal(self.yonyou_salesperson, self.yonyou_department,
            self._erp_connection()._org(company))
        self._store_principal(result)
        return result

    def action_yonyou_verify_principal(self):
        self.ensure_one()
        check_role(self)
        if self._principal_locked():
            raise UserError(_('This assignment is locked. For an existing ERP customer, use Verify & Refresh; change its salesperson in ERP first.'))
        try:
            self._verify_principal()
        except UserError as exc:
            self._erp_store({'yonyou_principal_snapshot': False, 'yonyou_principal_result': str(exc)})
            return notification(str(exc), True)
        return notification(_('Salesperson and department verified for the selling organization.'))
