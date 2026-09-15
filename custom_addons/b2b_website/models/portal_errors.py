from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _get_error_html(cls, env, code, values):
        # Keep native authorization, exception handling and status codes intact.
        # Do not alter backend/binary responses or the website editor's 404 tools.
        if str(code) == '404' and getattr(request, 'website', None):
            return 404, env['ir.ui.view']._render_template('b2b_website.portal_not_found', values)
        return super()._get_error_html(env, code, values)
