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

    def test_approve_enqueues_idempotent_erp_job(self):
        sample = self.env["b2b.sample.request"].with_user(self.portal_user).create(
            self.sample_values()
        )
        managed_sample = sample.with_user(self.manager)
        managed_sample.action_approve()
        self.assertEqual(managed_sample.state, "erp_pending")
        self.assertEqual(managed_sample.erp_job_count, 1)
        self.assertEqual(
            managed_sample.erp_job_ids.idempotency_key,
            "sample_request:%s" % managed_sample.request_uuid,
        )

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
