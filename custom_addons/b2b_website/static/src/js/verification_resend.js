/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

export function verificationResendSeconds(deadline, now) {
    return Math.max(0, Math.ceil((deadline - now) / 1000));
}

export function initializeVerificationResend() {
    for (const form of document.querySelectorAll("form[data-lt-resend-delay]")) {
        if (form.dataset.ltResendInitialized) continue;
        form.dataset.ltResendInitialized = "1";
        const delay = Math.max(0, Number(form.dataset.ltResendDelay) || 0);
        if (!delay) continue;
        const button = form.querySelector('button[type="submit"]');
        const feedback = form.querySelector("[data-lt-resend-timer]");
        if (!button || !feedback) continue;
        const deadline = Date.now() + delay * 1000;
        const update = () => {
            if (!form.isConnected) return false;
            const remaining = verificationResendSeconds(deadline, Date.now());
            // Never change the label, dimensions or Turnstile lock classes.
            button.disabled = remaining > 0;
            feedback.hidden = false;
            feedback.textContent = remaining
                ? _t("You can resend in %s seconds.", remaining)
                : _t("You can request another verification email now.");
            return remaining > 0;
        };
        update();
        const timer = setInterval(() => {
            if (!update()) clearInterval(timer);
        }, 1000);
    }
}
