import uuid

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    b2b_integration_key = fields.Char(
        copy=False, readonly=True, index=True,
        groups="b2b_erp_connector.group_b2b_integration_manager",
    )
    b2b_erp_reference = fields.Char(
        copy=False, readonly=True, index=True,
        groups="b2b_core.group_b2b_operator",
    )
    b2b_erp_job_ids = fields.One2many(
        "b2b.integration.job",
        compute="_compute_b2b_erp_jobs",
        string="ERP Jobs",
        groups="b2b_core.group_b2b_operator",
    )
    b2b_erp_job_count = fields.Integer(
        compute="_compute_b2b_erp_jobs", groups="b2b_core.group_b2b_operator"
    )

    def _compute_b2b_erp_jobs(self):
        Job = self.env["b2b.integration.job"]
        jobs = Job.search([
            ("reference_model", "=", self._name),
            ("reference_id", "in", self.ids),
        ])
        jobs_by_order = {}
        for job in jobs:
            jobs_by_order.setdefault(job.reference_id, Job)
            jobs_by_order[job.reference_id] |= job
        for order in self:
            order_jobs = jobs_by_order.get(order.id, Job)
            order.b2b_erp_job_ids = order_jobs
            order.b2b_erp_job_count = len(order_jobs)

    def action_confirm(self):
        result = super().action_confirm()
        if self.env["b2b.erp.service"].is_enabled():
            for order in self.filtered(
                lambda item: item.website_id
                or item.partner_id.commercial_partner_id.b2b_approved
            ):
                order._b2b_enqueue_erp_sync()
        return result

    def _b2b_enqueue_erp_sync(self):
        self.ensure_one()
        order = self.sudo()
        if not order.b2b_integration_key:
            order.b2b_integration_key = str(uuid.uuid4())
        # Confirmation may originate from a Portal checkout. The order and
        # customer were authorized by website_sale before this scoped enqueue.
        return self.env["b2b.integration.job"].sudo().enqueue(
            "sales_order",
            order,
            "sales_order:%s" % order.b2b_integration_key,
            request_summary={
                "order": order.name,
                "customer": order.partner_id.commercial_partner_id.display_name,
                "line_count": len(order.order_line),
            },
        )

    def _b2b_on_erp_job_success(self, job, result):
        self.ensure_one()
        reference = result.get("reference")
        if reference:
            self.b2b_erp_reference = str(reference)[:128]

    def action_view_b2b_erp_jobs(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id(
            "b2b_erp_connector.action_b2b_integration_jobs"
        )
        action["domain"] = [
            ("reference_model", "=", self._name),
            ("reference_id", "=", self.id),
        ]
        return action
