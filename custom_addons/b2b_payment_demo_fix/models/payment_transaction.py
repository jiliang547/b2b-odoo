from odoo import models


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    _B2B_DEMO_STATE_ALIASES = {
        "完成": "done",
        "成功": "done",
        "进行中": "pending",
        "处理中": "pending",
        "取消": "cancel",
        "已取消": "cancel",
        "错误": "error",
        "失败": "error",
    }

    def _b2b_normalize_demo_payment_data(self, payment_data):
        """Restore technical demo states altered by localized QWeb translations."""
        normalized_data = dict(payment_data or {})
        state = normalized_data.get("simulated_state")
        if isinstance(state, str):
            normalized_data["simulated_state"] = self._B2B_DEMO_STATE_ALIASES.get(
                state.strip(), state.strip()
            )
        return normalized_data

    def _apply_updates(self, payment_data):
        if self.provider_code == "demo":
            payment_data = self._b2b_normalize_demo_payment_data(payment_data)
        return super()._apply_updates(payment_data)
