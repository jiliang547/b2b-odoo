from unittest.mock import patch

from odoo import Command
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError
from odoo.addons.website_sale.tests.common import MockRequest
from ..controllers import website_sale


@tagged('post_install', '-at_install')
class TestCheckoutRecovery(TransactionCase):
    def test_frontend_error_templates_keep_brand_shell_and_hide_raw_errors(self):
        frontend_env = self.env(context=dict(self.env.context, lang='en_US'))
        website = frontend_env['website'].search([], limit=1)
        with MockRequest(frontend_env, website=website, url_root='http://localhost:18073/') as req:
            req.is_frontend = True
            req.is_frontend_multilang = False
            for code in ('4xx', '400', '403', '404', '422'):
                with self.subTest(code=code):
                    rendered = frontend_env['ir.ui.view']._render_template('http_routing.' + code, {
                        'website': website, 'editable': False, 'debug': '',
                        'error_message': 'PRIVATE-ERP-ERROR', 'main_object': website,
                    })
                    self.assertIn('Partner Hub navigation', rendered)
                    self.assertIn('lt-footer', rendered)
                    self.assertNotIn('PRIVATE-ERP-ERROR', rendered)
                    self.assertNotIn('Your information has not been partially changed', rendered)

    def test_failed_review_submission_rolls_back_and_keeps_cart(self):
        website = self.env['website'].search([], limit=1)
        partner = self.env['res.partner'].create({'name': 'Review error test customer'})
        product = self.env['product.product'].create({'name': 'Review error test product'})
        order = self.env['sale.order'].create({'partner_id': partner.id, 'website_id': website.id,
            'order_line': [Command.create({'product_id': product.id, 'product_uom_qty': 1, 'price_unit': 10})]})
        def fail(controller, record):
            record.client_order_ref = 'SHOULD-ROLL-BACK'
            raise ValidationError('PRIVATE-ERP-ERROR')
        with MockRequest(self.env, website=website, sale_order_id=order.id) as req, \
                patch.object(website_sale, '_can_checkout', return_value=True), \
                patch.object(type(order), '_is_cart_ready', return_value=True), \
                patch.object(website_sale.PartnerHubWebsiteSale, '_submit_review_order', fail), \
                patch.object(website_sale, 'render_checkout_error', return_value='SAFE NOTICE'):
            req.cart = order
            result = website_sale.PartnerHubWebsiteSale.shop_submit_for_review.__wrapped__(
                website_sale.PartnerHubWebsiteSale())
            self.assertEqual(result, 'SAFE NOTICE')
            self.assertFalse(order.client_order_ref)
            self.assertEqual(order.state, 'draft')
            self.assertEqual(req.cart.id, order.id)
