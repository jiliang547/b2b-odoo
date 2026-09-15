from lxml import etree
from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestCollectionSpreadsheetAccess(TransactionCase):
    def test_finance_order_form_does_not_request_sales_spreadsheets(self):
        finance = mail_new_test_user(self.env, login='uat-spreadsheet-finance',
                                    groups='b2b_website.group_b2b_finance')
        self.assertFalse(finance.has_group('sales_team.group_sale_salesman'))
        view = self.env['sale.order'].with_user(finance).get_view(
            self.env.ref('sale.view_order_form').id, 'form')
        arch = etree.fromstring(view['arch'])
        self.assertFalse(arch.xpath("//field[starts-with(@name, 'spreadsheet_')]"))
