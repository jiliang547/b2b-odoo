from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([
        ("b2b_sample_request_id", "!=", False),
        ("state", "!=", "cancel"),
        ("transaction_ids.state", "in", ["done", "authorized"]),
    ])
    recovery_transactions = env["payment.transaction"]
    for order in orders:
        completed = order.transaction_ids.filtered(
            lambda tx: tx.state in ("done", "authorized")
            and tx.operation not in ("refund", "validation")
        )
        if not completed:
            continue
        # A final Demo result makes an older Demo-pending attempt safe to
        # close. Never infer or alter a real provider's pending state.
        order._b2b_resolve_safe_demo_payment_conflicts()
        if order.state in ("draft", "sent"):
            unprocessed = completed.filtered(lambda tx: not tx.is_post_processed)
            unprocessed.write({"last_state_change": fields.Datetime.now()})
            recovery_transactions |= unprocessed
    if recovery_transactions:
        env.ref("payment.cron_post_process_payment_tx")._trigger()
