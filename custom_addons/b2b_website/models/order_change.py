from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


OPEN_STATES = (
    "submitted",
    "under_review",
    "customer_confirmation",
    "balance_due",
    "finance_review",
    "applying",
)


class B2BOrderChangeRequest(models.Model):
    _name = "b2b.order.change.request"
    _description = "B2B Order Change Request"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _mail_post_access = "read"

    name = fields.Char(default=lambda self: _("New"), readonly=True, copy=False, index=True)
    order_id = fields.Many2one(
        "sale.order", required=True, ondelete="restrict", index=True, tracking=True
    )
    revision_order_id = fields.Many2one(
        "sale.order", string="Proposed Revision", readonly=True, copy=False, ondelete="restrict"
    )
    partner_id = fields.Many2one(
        "res.partner", related="order_id.partner_id", store=True, readonly=True, index=True
    )
    commercial_partner_id = fields.Many2one(
        "res.partner",
        related="order_id.partner_id.commercial_partner_id",
        store=True,
        readonly=True,
        index=True,
    )
    website_id = fields.Many2one(
        "website", related="order_id.website_id", store=True, readonly=True
    )
    currency_id = fields.Many2one(
        "res.currency", related="order_id.currency_id", store=True, readonly=True
    )
    state = fields.Selection(
        [
            ("submitted", "Submitted"),
            ("under_review", "Under Review"),
            ("customer_confirmation", "Customer Confirmation"),
            ("balance_due", "Balance Due"),
            ("finance_review", "Finance Review"),
            ("applying", "Applying"),
            ("completed", "Completed"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="submitted",
        required=True,
        tracking=True,
        index=True,
    )
    requested_changes = fields.Text(required=True)
    customer_note = fields.Text()
    rejection_reason = fields.Text()
    assigned_user_id = fields.Many2one("res.users", tracking=True)
    original_amount = fields.Monetary(readonly=True, copy=False)
    proposed_amount = fields.Monetary(readonly=True, copy=False)
    delta_amount = fields.Monetary(readonly=True, copy=False)
    original_snapshot = fields.Json(readonly=True, copy=False)
    revision_number = fields.Integer(readonly=True, copy=False)
    customer_confirmed_at = fields.Datetime(readonly=True, copy=False)
    completed_at = fields.Datetime(readonly=True, copy=False)
    finance_reference = fields.Char(
        help="Credit note, payment provider refund, bank transfer, or other accounting reference."
    )
    finance_note = fields.Text()
    adjustment_move_id = fields.Many2one(
        "account.move", string="Credit / Additional Invoice", copy=False, ondelete="set null"
    )
    refund_transaction_id = fields.Many2one(
        "payment.transaction", string="Refund Transaction", copy=False, ondelete="set null"
    )
    has_posted_invoice = fields.Boolean(compute="_compute_financial_context")
    has_delivered_items = fields.Boolean(compute="_compute_financial_context")

    def write(self, vals):
        # Finance needs write access to record the native accounting/refund
        # evidence, but that must not silently grant authority over the sales
        # proposal or workflow state.
        if (
            not self.env.is_superuser()
            and not self.env.context.get("b2b_finance_workflow")
            and self.env.user.has_group("account.group_account_invoice")
            and not self.env.user.has_group("b2b_core.group_b2b_manager")
        ):
            finance_fields = {
                "adjustment_move_id",
                "finance_note",
                "finance_reference",
                "refund_transaction_id",
            }
            if set(vals) - finance_fields:
                raise AccessError(_(
                    "Finance users can only record the accounting or refund details."
                ))
        return super().write(vals)

    @api.depends("order_id.invoice_ids.state", "order_id.order_line.qty_delivered")
    def _compute_financial_context(self):
        for request in self:
            request.has_posted_invoice = bool(
                request.order_id.invoice_ids.filtered(lambda move: move.state == "posted")
            )
            request.has_delivered_items = any(
                line.qty_delivered > 0
                for line in request.order_id.order_line.filtered(lambda line: not line.display_type)
            )

    @api.model
    def _snapshot_order(self, order):
        return {
            "amount_untaxed": order.amount_untaxed,
            "amount_tax": order.amount_tax,
            "amount_total": order.amount_total,
            "currency": order.currency_id.name,
            "lines": [
                {
                    "line_id": line.id,
                    "product_id": line.product_id.id,
                    "name": line.name,
                    "quantity": line.product_uom_qty,
                    "uom_id": line.product_uom_id.id,
                    "price_unit": line.price_unit,
                    "discount": line.discount,
                    "tax_ids": line.tax_ids.ids,
                    "display_type": line.display_type,
                }
                for line in order.order_line
            ],
        }

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals.get("order_id") for vals in vals_list if vals.get("order_id")]
        if len(order_ids) != len(set(order_ids)):
            raise ValidationError(_("Only one open change request is allowed per order."))
        if order_ids:
            # Serialize submissions for the same order.  The portal/controller
            # check is useful feedback, while this row lock closes the race
            # where two browser tabs submit at nearly the same time.
            self.env.cr.execute(
                "SELECT id FROM sale_order WHERE id = ANY(%s) FOR UPDATE",
                [order_ids],
            )
        for vals in vals_list:
            order = self.env["sale.order"].browse(vals.get("order_id")).exists()
            if not order or order.state not in ("sale", "done"):
                raise ValidationError(_("Only confirmed orders can be changed through this workflow."))
            if order.currency_id.compare_amounts(order.amount_paid, order.amount_total) < 0:
                raise ValidationError(_("This order has not been fully paid yet."))
            if any(line.qty_delivered > 0 for line in order.order_line):
                raise ValidationError(_(
                    "This order has already been delivered. Use the return or replacement workflow instead."
                ))
            if self.search_count([("order_id", "=", order.id), ("state", "in", OPEN_STATES)], limit=1):
                raise ValidationError(_("Another order change request is already open for this order."))
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].sudo().next_by_code(
                    "b2b.order.change.request"
                ) or _("New")
            vals.setdefault("original_amount", order.amount_total)
            vals.setdefault("original_snapshot", self._snapshot_order(order))
            vals.setdefault("revision_number", order.b2b_change_revision + 1)
            if not vals.get("assigned_user_id"):
                assigned_user = order.user_id.filtered(
                    lambda user: user.has_group("b2b_core.group_b2b_manager")
                )
                if not assigned_user:
                    manager_group = self.env.ref("b2b_core.group_b2b_manager")
                    assigned_user = self.env["res.users"].sudo().search([
                        ("active", "=", True),
                        ("share", "=", False),
                        ("all_group_ids", "in", manager_group.ids),
                    ], limit=1)
                vals["assigned_user_id"] = assigned_user.id
        records = super().create(vals_list)
        for request in records:
            followers = request.partner_id | request.assigned_user_id.partner_id
            if followers:
                request.message_subscribe(partner_ids=followers.ids)
            if request.assigned_user_id:
                request.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=request.assigned_user_id.id,
                    summary=_("Review order change %(request)s", request=request.name),
                )
            request.order_id.message_post(
                body=_("Order change request %(request)s was submitted.", request=request.name)
            )
        return records

    def _check_operator(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("b2b_core.group_b2b_operator")
        ):
            raise AccessError(_("Only a B2B operator can review order changes."))

    def _check_manager(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("b2b_core.group_b2b_manager")
        ):
            raise AccessError(_("Only a B2B Manager can approve order changes."))

    def _check_finance(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("account.group_account_invoice")
        ):
            raise AccessError(_("Only an authorized finance user can complete this adjustment."))

    def action_start_review(self):
        self._check_manager()
        for request in self:
            if request.state != "submitted":
                raise ValidationError(_("Only submitted requests can enter review."))
            order = request.order_id.sudo()
            if any(line.qty_delivered > 0 for line in order.order_line):
                raise ValidationError(_("Delivered orders must use the return or replacement workflow."))
            revision = order.copy({
                "origin": _("%(order)s / %(request)s", order=order.name, request=request.name),
                "state": "draft",
                "website_id": False,
                "transaction_ids": [Command.clear()],
                "require_payment": False,
                "require_signature": False,
                "b2b_is_change_revision": True,
                "b2b_source_order_id": order.id,
                "b2b_checkout_mode": "pay_now",
                "b2b_review_state": "none",
            })
            for source_line, revision_line in zip(order.order_line, revision.order_line):
                revision_line.b2b_source_order_line_id = source_line.id
            request.write({
                "revision_order_id": revision.id,
                "state": "under_review",
                "assigned_user_id": self.env.user.id,
            })
        return True

    def action_open_revision(self):
        self.ensure_one()
        self._check_manager()
        if not self.revision_order_id or self.state != "under_review":
            raise ValidationError(_("Start the review before editing the proposed order."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Proposed Revision %(request)s", request=self.name),
            "res_model": "sale.order",
            "res_id": self.revision_order_id.id,
            "view_mode": "form",
            "views": [(self.env.ref("b2b_website.view_order_form_b2b_proposal").id, "form")],
            "target": "new",
        }

    def action_send_proposal(self):
        self._check_manager()
        for request in self:
            if request.state != "under_review" or not request.revision_order_id:
                raise ValidationError(_("Prepare the proposed revision before sending it."))
            if any(line.qty_delivered > 0 for line in request.order_id.sudo().order_line):
                raise ValidationError(_("Delivered orders must use the return or replacement workflow."))
            proposed_amount = request.revision_order_id.sudo().amount_total
            request.write({
                "proposed_amount": proposed_amount,
                "delta_amount": proposed_amount - request.original_amount,
                "state": "customer_confirmation",
            })
            request.activity_ids.filtered(
                lambda activity: activity.activity_type_id
                == self.env.ref("mail.mail_activity_data_todo")
            ).action_feedback(feedback=_("Revision proposal sent to the customer."))
            request.message_post(
                body=_("The revised order proposal is ready for customer confirmation."),
                partner_ids=request.partner_id.ids,
            )
        return True

    def action_reject(self):
        self._check_manager()
        for request in self:
            if request.state not in ("submitted", "under_review", "customer_confirmation"):
                raise ValidationError(_("This request can no longer be rejected."))
            if not request.rejection_reason:
                raise ValidationError(_("Enter a rejection reason before rejecting the request."))
            request.write({"state": "rejected"})
            request.activity_ids.action_feedback(feedback=_("Order change rejected."))
            request.message_post(
                body=_("Your order change request was declined: %(reason)s", reason=request.rejection_reason),
                partner_ids=request.partner_id.ids,
            )
        return True

    @api.model
    def _revision_line_values(self, line):
        return {
            "name": line.name,
            "product_id": line.product_id.id,
            "product_uom_qty": line.product_uom_qty,
            "product_uom_id": line.product_uom_id.id,
            "price_unit": line.price_unit,
            "discount": line.discount,
            "tax_ids": [Command.set(line.tax_ids.ids)],
            "sequence": line.sequence,
            "display_type": line.display_type,
        }

    def _apply_revision(self):
        self.ensure_one()
        order = self.order_id
        revision = self.revision_order_id
        if order.locked:
            raise ValidationError(_("Unlock the sales order before applying an approved change."))
        if any(line.qty_delivered > 0 for line in order.order_line):
            raise ValidationError(_("The order was delivered while this request was open."))

        revision_sources = revision.order_line.mapped("b2b_source_order_line_id")
        for source_line in order.order_line - revision_sources:
            if source_line.qty_invoiced:
                source_line.product_uom_qty = 0
            else:
                source_line.unlink()

        for line in revision.order_line:
            source = line.b2b_source_order_line_id.filtered(lambda item: item.order_id == order)
            values = self._revision_line_values(line)
            if source and source.product_id == line.product_id and source.display_type == line.display_type:
                source.write(values)
            else:
                if source:
                    if source.qty_invoiced:
                        source.product_uom_qty = 0
                    else:
                        source.unlink()
                values["order_id"] = order.id
                self.env["sale.order.line"].create(values)

        order.write({"b2b_change_revision": self.revision_number})
        order.message_post(body=_(
            "Approved order change %(request)s applied as revision %(revision)s.",
            request=self.name,
            revision=self.revision_number,
        ))

    def action_customer_accept(self):
        self._check_customer_action()
        for request in self.sudo():
            if request.state != "customer_confirmation":
                raise ValidationError(_("This proposal is not awaiting customer confirmation."))
            request.write({"state": "applying", "customer_confirmed_at": fields.Datetime.now()})
            request.order_id.b2b_change_payment_hold = True
            request._apply_revision()
            delta = request.delta_amount
            if request.currency_id.is_zero(delta):
                next_state = "finance_review" if request.has_posted_invoice else "completed"
            elif delta > 0:
                next_state = "balance_due"
            else:
                next_state = "finance_review"
            values = {"state": next_state}
            if next_state == "completed":
                values["completed_at"] = fields.Datetime.now()
                request.order_id.b2b_change_payment_hold = False
            request.write(values)
            request.message_post(body=_("The customer accepted the revised order proposal."))
            if next_state == "finance_review":
                request._schedule_finance_review_activity()
        return True

    def action_customer_cancel(self):
        self._check_customer_action()
        for request in self.sudo():
            if request.state != "customer_confirmation":
                raise ValidationError(_("Only a proposal awaiting confirmation can be declined."))
            request.write({"state": "cancelled"})
            request.message_post(body=_("The customer declined the revised order proposal."))
        return True

    def _check_customer_action(self):
        user = self.env.user
        if user._is_public() or user._is_internal() or any(
            request.sudo().commercial_partner_id
            != user.partner_id.commercial_partner_id
            for request in self.sudo()
        ):
            raise AccessError(_("This order change does not belong to your company."))

    def _on_order_payment_updated(self):
        for request in self.filtered(lambda item: item.state == "balance_due"):
            order = request.order_id
            if order.currency_id.compare_amounts(order.amount_paid, order.amount_total) >= 0:
                next_state = "finance_review" if request.has_posted_invoice else "completed"
                values = {"state": next_state}
                if next_state == "completed":
                    values["completed_at"] = fields.Datetime.now()
                    order.b2b_change_payment_hold = False
                request.write(values)
                request.message_post(body=_("The additional payment has been received."))
                if next_state == "finance_review":
                    request._schedule_finance_review_activity()

    def _schedule_finance_review_activity(self):
        finance_group = self.env.ref("account.group_account_invoice")
        finance_user = self.env["res.users"].sudo().search([
            ("active", "=", True),
            ("share", "=", False),
            ("all_group_ids", "in", finance_group.ids),
        ], limit=1)
        if finance_user:
            for request in self:
                request.activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=finance_user.id,
                    summary=_("Complete financial adjustment %(request)s", request=request.name),
                    note=_(
                        "Verify the additional invoice, credit note, or refund, then record its reference."
                    ),
                )

    def action_finance_complete(self):
        self._check_finance()
        for request in self:
            if request.state != "finance_review":
                raise ValidationError(_("This request is not awaiting finance review."))
            if not request.finance_reference:
                raise ValidationError(_("Record the accounting or refund reference first."))
            if request.delta_amount < 0 and request.refund_transaction_id:
                refund = request.refund_transaction_id
                if refund.state != "done":
                    raise ValidationError(_("The selected refund transaction is not completed."))
                if (
                    refund.operation != "refund"
                    or request.order_id not in refund.source_transaction_id.sale_order_ids
                    or refund.currency_id != request.currency_id
                    or refund.partner_id.commercial_partner_id != request.commercial_partner_id
                    or request.currency_id.compare_amounts(abs(refund.amount), abs(request.delta_amount))
                ):
                    raise ValidationError(_(
                        "Select a completed refund for this order, customer and currency "
                        "whose amount matches the refund difference."
                    ))
            request.with_context(b2b_finance_workflow=True).write({
                "state": "completed",
                "completed_at": fields.Datetime.now(),
            })
            request.order_id.b2b_change_payment_hold = False
            request.activity_ids.filtered(
                lambda activity: activity.user_id == self.env.user
                and activity.activity_type_id == self.env.ref("mail.mail_activity_data_todo")
            ).action_feedback(feedback=_("Financial adjustment completed."))
            request.message_post(
                body=_(
                    "Finance completed the order adjustment. Reference: %(reference)s",
                    reference=request.finance_reference,
                ),
                partner_ids=request.partner_id.ids,
            )
        return True
