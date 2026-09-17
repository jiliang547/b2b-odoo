from odoo.addons.mail.tests.common import mail_new_test_user
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger
from unittest.mock import patch

from odoo.addons.b2b_erp_connector.services.erp_service import B2BERPError


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

    def test_integration_role_does_not_receive_business_manager_permissions(self):
        self.assertTrue(self.manager.has_group("b2b_core.group_b2b_operator"))
        self.assertFalse(self.manager.has_group("b2b_core.group_b2b_manager"))
        self.assertFalse(
            self.manager.has_group("b2b_core.group_b2b_special_price_manager")
        )

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

    @mute_logger("odoo.addons.b2b_erp_connector.models.integration_job")
    def test_partial_success_without_reference_is_retried(self):
        job = self.env["b2b.integration.job"].enqueue(
            "sales_order", self.order, "test-partial-response"
        )
        with patch.object(type(self.env["b2b.erp.service"]), "dispatch_job", return_value={"success": True}):
            self.assertFalse(job._process_locked())
        self.assertEqual(job.state, "failed")

    @mute_logger("odoo.addons.b2b_erp_connector.models.integration_job")
    def test_non_retryable_adapter_error_goes_directly_to_dead_letter(self):
        job = self.env["b2b.integration.job"].enqueue(
            "sales_order", self.order, "test-non-retryable"
        )
        error = B2BERPError("http_401", "ERP rejected the credentials.", retryable=False)
        with patch.object(type(self.env["b2b.erp.service"]), "dispatch_job", side_effect=error):
            self.assertFalse(job._process_locked())
        self.assertEqual(job.state, "dead")
        self.assertFalse(job.next_retry_at)
