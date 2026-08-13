from odoo import _, api, models
from odoo.exceptions import UserError


class MockERPAdapter:
    """Deterministic non-production adapter used until the real contract exists."""

    def __init__(self, env):
        self.env = env

    def push_sales_order(self, order, idempotency_key):
        return {
            "success": True,
            "reference": "MOCK-SO-%s" % order.id,
            "idempotency_key": idempotency_key,
        }

    def push_sample_request(self, request_record, idempotency_key):
        return {
            "success": True,
            "reference": "MOCK-SAMPLE-%s" % request_record.id,
            "idempotency_key": idempotency_key,
        }

    def get_order_status(self, order, customer_context):
        return {
            "order_number": order.name,
            "customer_reference": order.client_order_ref or "",
            "status": "mock",
            "current_stage": "Mock ERP Connected",
            "updated_at": order.write_date,
            "timeline": [],
            "tracking_number": None,
        }


class B2BERPService(models.AbstractModel):
    _name = "b2b.erp.service"
    _description = "B2B ERP Adapter Service"

    @api.model
    def is_enabled(self):
        return self.env["ir.config_parameter"].sudo().get_param("b2b_erp.enabled") == "True"

    @api.model
    def _adapter_name(self):
        return self.env["ir.config_parameter"].sudo().get_param("b2b_erp.adapter", "mock")

    @api.model
    def adapter(self):
        adapter_name = self._adapter_name()
        if adapter_name == "mock":
            return MockERPAdapter(self.env)
        raise UserError(_("The configured ERP adapter is not available."))

    @api.model
    def dispatch_job(self, job, reference):
        adapter = self.adapter()
        if job.job_type == "sales_order":
            return adapter.push_sales_order(reference, job.idempotency_key)
        if job.job_type == "sample_request":
            return adapter.push_sample_request(reference, job.idempotency_key)
        raise UserError(_("Unsupported ERP job type."))

    @api.model
    def get_order_status(self, order, customer_context):
        if not self.is_enabled():
            raise UserError(_("ERP order tracking is temporarily unavailable."))
        result = self.adapter().get_order_status(order, customer_context)
        required = {"order_number", "status", "current_stage", "timeline"}
        if not isinstance(result, dict) or not required.issubset(result):
            raise UserError(_("ERP returned an invalid order status response."))
        def safe_text(value, limit=160):
            return str(value or "")[:limit]

        timeline = []
        for event in result.get("timeline", [])[:30] if isinstance(result.get("timeline"), list) else []:
            if isinstance(event, dict):
                timeline.append({
                    "label": safe_text(event.get("label")),
                    "time": safe_text(event.get("time")),
                    "complete": bool(event.get("complete")),
                })
        return {
            "order_number": order.name,
            "status": safe_text(result.get("status")),
            "current_stage": safe_text(result.get("current_stage")),
            "updated_at": result.get("updated_at"),
            "timeline": timeline,
            "tracking_number": safe_text(result.get("tracking_number")) or False,
        }

    @api.model
    def safe_response_summary(self, result):
        allowed = {"success", "reference", "status", "current_stage", "updated_at"}
        return {key: result[key] for key in allowed if key in result}
