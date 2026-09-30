from odoo.tests import tagged
from odoo.addons.b2b_website.tests.test_collection import B2BCollectionCommon


@tagged('post_install', '-at_install')
class TestYonyouCollectionTrigger(B2BCollectionCommon):
    def test_deposit_queues_whole_order_once_and_balance_does_not_requeue(self):
        config = self.env.ref('b2b_yonyou.connection').sudo()
        config.order_sync = False
        order = self._order('b30')
        config.write({'enabled': True, 'test_mode': True, 'management_org': '999',
                      'default_use_org': '999', 'sales_org': '999', 'order_sync': True})
        self._receipt(order, 20).action_confirm_receipt()
        self.assertEqual(order.state, 'sent')
        self.assertFalse(order.b2b_erp_job_ids)
        self._receipt(order, 10).action_confirm_receipt()
        self.assertEqual(order.state, 'sale')
        job = order.b2b_erp_job_ids
        self.assertEqual(len(job), 1)
        self.assertTrue(job.yonyou_order)
        self.assertEqual(order.sudo().yonyou_source['total'], 100)
        self.assertEqual(order.amount_paid, 30)
        key = order.sudo().yonyou_key
        self._receipt(order, 70).action_confirm_receipt()
        self.assertEqual(order.b2b_erp_job_ids, job)
        self.assertEqual(order.sudo().yonyou_key, key)
        self.assertFalse(order.yonyou_manual_review)
        self.assertEqual(order.b2b_balance, 0)
