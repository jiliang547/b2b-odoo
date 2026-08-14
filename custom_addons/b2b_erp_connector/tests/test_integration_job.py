from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestIntegrationJob(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = mail_new_test_user(
            cls.env,
            login="erp-job-manager",
            groups="b2b_erp_connector.group_b2b_integration_manager",
        )
        cls.partner = cls.env["res.partner"].create({"name": "ERP Customer"})
        cls.order = cls.env["sale.order"].create({"partner_id": cls.partner.id})

    def test_enqueue_is_idempotent(self):
        Job = self.env["b2b.integration.job"]
        first = Job.enqueue("sales_order", self.order, "test-order-key")
        second = Job.enqueue("sales_order", self.order, "test-order-key")
        self.assertEqual(first, second)

    def test_mock_job_processes_successfully(self):
        job = self.env["b2b.integration.job"].enqueue(
            "sales_order", self.order, "test-order-success"
        )
        self.assertTrue(job._process_locked())
        self.assertEqual(job.state, "success")
        self.assertTrue(job.safe_response_summary.get("reference"))

    def test_missing_reference_fails_safely_and_can_retry(self):
        job = self.env["b2b.integration.job"].create({
            "job_type": "sales_order",
            "reference_model": "sale.order",
            "reference_id": 999999999,
            "reference_name": "Missing",
            "idempotency_key": "test-missing-reference",
        })
        self.assertFalse(job._process_locked())
        self.assertEqual(job.state, "failed")
        self.assertNotIn("http", (job.last_error or "").lower())
        job.with_user(self.manager).action_retry()
        self.assertEqual(job.state, "pending")

    def test_manager_cannot_forge_system_job_state(self):
        job = self.env["b2b.integration.job"].enqueue(
            "sales_order", self.order, "test-protected-state"
        )
        with self.assertRaises(AccessError):
            job.with_user(self.manager).with_context(b2b_job_write=True).write({
                "state": "success"
            })
