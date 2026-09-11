/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { PaymentForm } from "@payment/interactions/payment_form";

patch(PaymentForm.prototype, {
    async submitForm(event) {
        event.preventDefault();
        event.stopPropagation();
        if (this.b2bPaymentSubmitting) return;
        this.b2bPaymentSubmitting = true;
        try {
            this.el.querySelector('[data-b2b-payment-error]')?.remove();
            const radio = this.el.querySelector('input[name="o_payment_radio"]:checked');
            if (!radio) {
                this._displayErrorDialog(_t("Please Review the Information"), _t("Please select an option."));
                return;
            }
            this._disableButton();
            // Modal/default selection can outlive its initial provider setup.
            // Let the selected provider choose direct/redirect/token via the native hook.
            await this.waitFor(this._expandInlineForm(radio));
            await super.submitForm(...arguments);
        } catch (error) {
            // Native transaction handling already reports RPC errors. Unexpected
            // client failures must also release the button and blocking overlay.
            this._enableButton();
            console.error("Partner Hub payment could not continue", error);
            const message = _t("Please refresh the page and try again.");
            let alert = this.el.querySelector('[data-b2b-payment-error]');
            if (!alert) {
                alert = document.createElement("div");
                alert.dataset.b2bPaymentError = "";
                alert.className = "alert alert-danger mt-3";
                alert.setAttribute("role", "alert");
                this.el.appendChild(alert);
            }
            // Keep this recovery visible even if the global notification UI failed.
            alert.textContent = message;
        } finally {
            this.b2bPaymentSubmitting = false;
        }
    },
});
