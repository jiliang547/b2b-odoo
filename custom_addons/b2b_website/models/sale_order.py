from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError, UserError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _get_lang(self):
        language = super()._get_lang()
        if self.website_id and language and language.startswith("zh_"):
            return self.website_id.default_lang_id.code
        return language

    b2b_pricing_revision = fields.Integer(copy=False, readonly=True)
    b2b_checkout_mode = fields.Selection(
        [("pay_now", "Pay Now"), ("review", "Submit for Review")],
        default="pay_now",
        required=True,
        copy=False,
        tracking=True,
    )
    b2b_review_state = fields.Selection(
        [
            ("none", "Not Requested"),
            ("pending", "Pending Review"),
            ("ready", "Ready for Payment"),
            ("confirmed", "Confirmed"),
        ],
        default="none",
        required=True,
        copy=False,
        tracking=True,
    )
    b2b_change_revision = fields.Integer(copy=False, readonly=True)
    b2b_change_request_ids = fields.One2many(
        "b2b.order.change.request", "order_id", string="Order Change Requests"
    )
    b2b_is_change_revision = fields.Boolean(copy=False, index=True)
    b2b_source_order_id = fields.Many2one("sale.order", copy=False, ondelete="restrict")
    b2b_change_payment_hold = fields.Boolean(
        string="Order Change Hold",
        copy=False,
        tracking=True,
        help="Blocks delivery while an accepted revision still needs payment or finance work.",
    )

    def _b2b_is_trusted_payment_confirmation(self):
        self.ensure_one()
        transaction_ids = self.env.context.get("b2b_payment_transaction_ids") or []
        if not transaction_ids:
            return False
        transactions = self.env["payment.transaction"].sudo().browse(transaction_ids).exists()
        return any(
            self in transaction.sale_order_ids
            and transaction.partner_id.commercial_partner_id
            == self.partner_id.commercial_partner_id
            for transaction in transactions
        )

    def _b2b_check_product_allowed(self, product_id):
        self.ensure_one()
        product = self.env["product.product"].browse(product_id).exists()
        service = self.env["b2b.product.service"]
        if self._b2b_is_trusted_payment_confirmation():
            # The transaction/order/customer relationship was verified above.
            # Change the policy evaluator's user rather than globally bypassing
            # the catalog rules for normal portal requests.
            service = service.with_user(SUPERUSER_ID)
            product = product.with_user(SUPERUSER_ID)
        if not product or not service.is_visible(
            product.product_tmpl_id,
            partner=self.partner_id,
            website=self.website_id,
        ):
            raise AccessError(_("This product is not available to your Partner Hub account."))
        if not self.env.user._is_internal() and not service.can_view_price(
            partner=self.partner_id, website=self.website_id
        ):
            raise AccessError(_("Ordering is not enabled for your Partner Hub account."))

    def _b2b_validate_sale_quantity(self, product_id, quantity):
        self.ensure_one()
        product = self.env["product.product"].browse(product_id).exists()
        if product:
            self.env["b2b.product.service"].validate_sale_quantity(
                product,
                quantity,
                pricelist=self.pricelist_id,
                website=self.website_id,
            )

    def _prepare_order_line_values(self, product_id, quantity, uom_id, **kwargs):
        self.ensure_one()
        if self.website_id and not self.env.user._is_internal():
            self._b2b_check_product_allowed(product_id)
            self._b2b_validate_sale_quantity(product_id, quantity)
        return super()._prepare_order_line_values(
            product_id, quantity, uom_id, **kwargs
        )

    def _verify_updated_quantity(
        self, order_line, product_id, new_qty, uom_id, **kwargs
    ):
        if self.website_id and not self.env.user._is_internal() and new_qty > 0:
            self._b2b_check_product_allowed(product_id)
            self._b2b_validate_sale_quantity(product_id, new_qty)
        return super()._verify_updated_quantity(
            order_line, product_id, new_qty, uom_id, **kwargs
        )

    @api.depends(
        "transaction_ids", "transaction_ids.state", "transaction_ids.amount",
        "transaction_ids.child_transaction_ids.state",
        "transaction_ids.child_transaction_ids.amount",
        "b2b_change_request_ids.state", "b2b_change_request_ids.delta_amount",
        "b2b_change_request_ids.refund_transaction_id",
    )
    def _compute_amount_paid(self):
        super()._compute_amount_paid()
        for order in self.filtered("b2b_change_request_ids"):
            # Native refunds point to their source transaction, but are not
            # necessarily linked to the sales order. Count each refund once.
            refunds = (
                order.transaction_ids.child_transaction_ids
                | order.b2b_change_request_ids.refund_transaction_id
            ).filtered(lambda tx: tx.operation == "refund" and tx.state == "done"
                       and tx.currency_id == order.currency_id
                       and order in tx.source_transaction_id.sale_order_ids)
            unlinked_refunds = refunds - order.transaction_ids
            manual_refunds = order.b2b_change_request_ids.filtered(
                lambda change: change.state == "completed" and change.delta_amount < 0
                and not change.refund_transaction_id
            )
            order.amount_paid -= sum(abs(tx.amount) for tx in unlinked_refunds)
            # Finance Complete attests the external refund when no native
            # transaction exists. Keep its recorded amount for later revisions.
            order.amount_paid += sum(manual_refunds.mapped("delta_amount"))

    def _has_to_be_paid(self):
        self.ensure_one()
        return self.b2b_review_state != "pending" and super()._has_to_be_paid()

    def _has_to_be_signed(self):
        self.ensure_one()
        return self.b2b_review_state != "pending" and super()._has_to_be_signed()

    def action_confirm(self):
        if self.filtered(lambda order: order.b2b_review_state == "pending"):
            raise UserError(_("This order is still under review. Release it for customer payment first."))
        if self.filtered("b2b_is_change_revision"):
            raise UserError(_(
                "A proposed order revision cannot be confirmed as a separate sales order. "
                "Complete it from the related Order Change Request."
            ))
        for order in self.filtered("website_id"):
            if (
                order.website_id.b2b_require_approved_checkout
                and not order.partner_id.commercial_partner_id.b2b_approved
                and not self.env.user._is_internal()
            ):
                raise UserError(
                    _("Your Partner Hub account must be approved before submitting an order.")
                )
            for line in order.order_line.filtered(
                lambda item: not item.display_type and not item.is_delivery
            ):
                order._b2b_check_product_allowed(line.product_id.id)
        result = super().action_confirm()
        self.filtered(
            lambda order: order.b2b_checkout_mode == "review"
            and order.b2b_review_state in ("pending", "ready")
        ).write({"b2b_review_state": "confirmed"})
        return result

    def action_b2b_mark_review_ready(self):
        if not (
            self.env.is_superuser()
            or self.env.user.has_group("b2b_core.group_b2b_manager")
        ):
            raise AccessError(_("Only a B2B Manager can release an order for payment."))
        for order in self:
            if order.state != "sent" or order.b2b_review_state != "pending":
                raise UserError(_("Only orders pending review can be released for payment."))
            for line in order.order_line.filtered(
                lambda item: not item.display_type and not item.is_delivery
            ):
                order._b2b_check_product_allowed(line.product_id.id)
                order._b2b_validate_sale_quantity(
                    line.product_id.id, line.product_uom_qty
                )
            order.write({
                "b2b_review_state": "ready",
                "require_payment": True,
                "prepayment_percent": 1.0,
            })
            order.message_post(
                body=_("The reviewed order is ready for payment."),
                partner_ids=order.partner_id.ids,
            )
        return True


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    b2b_source_order_line_id = fields.Many2one(
        "sale.order.line", copy=False, readonly=True, ondelete="set null"
    )

    @api.model
    def _b2b_check_revision_orders_editable(self, orders):
        revision_orders = orders.filtered("b2b_is_change_revision")
        if not revision_orders:
            return
        frozen_requests = self.env["b2b.order.change.request"].sudo().search([
            ("revision_order_id", "in", revision_orders.ids),
            ("state", "!=", "under_review"),
        ], limit=1)
        if frozen_requests:
            raise UserError(_(
                "This proposal has already been sent to the customer and can no longer be edited."
            ))

    @api.model_create_multi
    def create(self, vals_list):
        order_ids = [vals.get("order_id") for vals in vals_list if vals.get("order_id")]
        self._b2b_check_revision_orders_editable(
            self.env["sale.order"].browse(order_ids).exists()
        )
        return super().create(vals_list)

    def write(self, vals):
        self._b2b_check_revision_orders_editable(self.mapped("order_id"))
        return super().write(vals)

    def unlink(self):
        self._b2b_check_revision_orders_editable(self.mapped("order_id"))
        return super().unlink()


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def _b2b_check_order_change_hold(self):
        held_pickings = self.filtered(
            lambda picking: picking.picking_type_id.code == "outgoing"
            and picking.sale_id.b2b_change_payment_hold
        )
        if held_pickings:
            raise UserError(_(
                "Delivery is on hold until the customer's order adjustment payment or finance review is complete."
            ))

    def button_validate(self):
        self._b2b_check_order_change_hold()
        return super().button_validate()

    def _action_done(self):
        self._b2b_check_order_change_hold()
        return super()._action_done()
