from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SampleCase


@tagged("post_install", "-at_install")
class TestSampleWorkflow(SampleCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = mail_new_test_user(
            cls.env,
            login="sample-manager",
            groups="b2b_core.group_b2b_manager,b2b_erp_connector.group_b2b_integration_manager",
        )

    def test_approve_creates_paid_sample_quotation(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        managed_sample = sample.with_user(self.manager)
        managed_sample.action_approve()
        self.assertEqual(managed_sample.state, "quotation")
        self.assertTrue(managed_sample.sale_order_id)
        self.assertEqual(managed_sample.sale_order_id.state, "sent")
        self.assertTrue(managed_sample.sale_order_id.require_payment)
        self.assertEqual(managed_sample.sale_order_id.prepayment_percent, 1.0)
        self.assertEqual(managed_sample.sale_order_id.b2b_sample_request_id, managed_sample)
        self.assertEqual(managed_sample.erp_job_count, 0)
        with self.assertRaises(UserError):
            managed_sample.action_approve()

    def test_state_cannot_be_written_directly(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        with self.assertRaises(UserError):
            sample.with_user(self.manager).write({"state": "approved"})
        with self.assertRaises(UserError):
            sample.with_user(self.manager).with_context(
                b2b_state_transition=True
            ).write({"state": "approved"})

    def test_confirmed_sample_order_enters_erp_queue_once(self):
        self.env["ir.config_parameter"].sudo().set_param("b2b_erp.enabled", "True")
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        managed_sample = sample.with_user(self.manager)
        managed_sample.action_approve()
        managed_sample.sale_order_id.sudo().action_confirm()
        self.assertEqual(managed_sample.state, "erp_pending")
        self.assertEqual(managed_sample.erp_job_count, 1)
        self.assertEqual(
            managed_sample.erp_job_ids.idempotency_key,
            "sales_order:%s" % managed_sample.sale_order_id.b2b_integration_key,
        )
