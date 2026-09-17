/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

const AUTH_FORM_SELECTOR = ".lt-auth-page form[data-captcha]";
const TURNSTILE_SCRIPT_URL = "https://challenges.cloudflare.com/turnstile/v0/api.js";
const VERIFICATION_TIMEOUT = 25000;
const CONFIGURATION_ERROR_CODES = new Set([
    "110100",
    "110110",
    "110200",
    "400020",
    "400070",
]);

let callbackSequence = 0;

function turnstileErrorMessage(code) {
    if (CONFIGURATION_ERROR_CODES.has(String(code || ""))) {
        return _t("Security verification is unavailable. Please contact support.");
    }
    return _t("Security verification could not be completed. Check your connection and try again.");
}

class PartnerHubTurnstileUX {
    constructor(form) {
        this.form = form;
        this.submitButton = form.querySelector('button[type="submit"]');
        this.feedback = null;
        this.timeoutId = null;
        this.container = null;
        this.state = "idle";
        this.observer = new MutationObserver(() => this.synchronize());
        this.observer.observe(form, {
            attributes: true,
            attributeFilter: ["class", "required", "style", "value"],
            childList: true,
            subtree: true,
        });
        this.onTurnstileError = (event) => {
            if (this.isLocked()) {
                this.showFailure(event.detail?.code);
            }
        };
        document.addEventListener("partner-hub:turnstile-error", this.onTurnstileError);
        this.synchronize();
    }

    isLocked() {
        return this.submitButton?.classList.contains("cf_form_disabled");
    }

    isComplete() {
        const validation = this.form.querySelector("input.turnstile_captcha_valid");
        return Boolean(
            validation &&
            !validation.required &&
            validation.getAttribute("value") === "done" &&
            !this.isLocked()
        );
    }

    ensureFeedback() {
        if (this.feedback || !this.submitButton) {
            return;
        }
        this.feedback = document.createElement("div");
        this.feedback.className = "lt-turnstile-feedback";
        this.feedback.setAttribute("role", "status");
        this.feedback.setAttribute("aria-live", "polite");
        this.feedback.hidden = true;
        this.submitButton.before(this.feedback);
    }

    setState(state, message, canRetry = false) {
        this.ensureFeedback();
        if (!this.feedback) {
            return;
        }
        this.state = state;
        this.feedback.className = `lt-turnstile-feedback is-${state}`;
        this.feedback.replaceChildren();

        const messageElement = document.createElement("span");
        messageElement.textContent = message;
        this.feedback.append(messageElement);
        if (canRetry) {
            const retryButton = document.createElement("button");
            retryButton.type = "button";
            retryButton.className = "lt-turnstile-retry";
            retryButton.textContent = _t("Retry verification");
            retryButton.addEventListener("click", () => this.retry());
            this.feedback.append(retryButton);
        }
        this.feedback.hidden = false;
    }

    lockSubmission() {
        if (!this.submitButton) {
            return;
        }
        this.submitButton.classList.add("disabled", "cf_form_disabled");
        this.submitButton.setAttribute("aria-disabled", "true");
        const validation = this.form.querySelector("input.turnstile_captcha_valid");
        if (validation) {
            validation.required = true;
            validation.setAttribute("value", "");
        }
    }

    startTimeout(duration = VERIFICATION_TIMEOUT) {
        window.clearTimeout(this.timeoutId);
        this.timeoutId = window.setTimeout(() => {
            if (this.isLocked() && !this.isComplete()) {
                this.showFailure();
            }
        }, duration);
    }

    showPending(duration = VERIFICATION_TIMEOUT) {
        if (this.state !== "pending") {
            this.setState("pending", _t("Completing security check…"));
        }
        this.startTimeout(duration);
    }

    showFailure(code) {
        window.clearTimeout(this.timeoutId);
        this.lockSubmission();
        this.setState("error", turnstileErrorMessage(code), true);
    }

    showComplete() {
        window.clearTimeout(this.timeoutId);
        this.submitButton?.removeAttribute("aria-disabled");
        this.setState("success", _t("Security check complete."));
    }

    installCallbacks(container) {
        if (container.dataset.ltTurnstileEnhanced === "true") {
            return;
        }
        container.dataset.ltTurnstileEnhanced = "true";
        const suffix = ++callbackSequence;

        const wrapCallback = (attribute, prefix, beforeNative) => {
            const nativeName = container.getAttribute(attribute);
            const enhancedName = `${prefix}_${suffix}`;
            window[enhancedName] = (...args) => {
                beforeNative(...args);
                if (nativeName && typeof window[nativeName] === "function") {
                    window[nativeName](...args);
                }
                this.synchronize();
            };
            container.setAttribute(attribute, enhancedName);
        };

        wrapCallback("data-callback", "partnerHubTurnstileSuccess", () => {});
        wrapCallback("data-before-interactive-callback", "partnerHubTurnstileVisible", () => {
            this.showPending(60000);
        });
        wrapCallback("data-error-callback", "partnerHubTurnstileError", (code) => {
            this.showFailure(code);
        });

        const expiredName = `partnerHubTurnstileExpired_${suffix}`;
        window[expiredName] = () => {
            this.showFailure();
        };
        container.setAttribute("data-expired-callback", expiredName);

        const timeoutName = `partnerHubTurnstileTimeout_${suffix}`;
        window[timeoutName] = () => {
            this.showFailure("110600");
        };
        container.setAttribute("data-timeout-callback", timeoutName);
    }

    synchronize() {
        const container = this.form.querySelector(".s_turnstile_container");
        if (container && container !== this.container) {
            this.container = container;
            this.installCallbacks(container);
        }
        if (this.isComplete()) {
            if (this.state !== "success") {
                this.showComplete();
            }
        } else if (this.isLocked() && this.state === "idle") {
            this.submitButton?.setAttribute("aria-disabled", "true");
            this.showPending();
        }
    }

    renderAfterScriptLoad() {
        if (!this.container || !window.turnstile?.render) {
            this.showFailure();
            return;
        }
        try {
            if (this.container.querySelector("iframe")) {
                window.turnstile.reset(this.container);
            } else {
                window.turnstile.render(this.container);
            }
        } catch (_error) {
            this.showFailure();
        }
    }

    reloadScript() {
        const existingScript = document.getElementById("s_turnstile_remote_script");
        const script = document.createElement("script");
        script.id = "s_turnstile_remote_script";
        script.className = "s_turnstile";
        script.src = TURNSTILE_SCRIPT_URL;
        script.async = true;
        script.defer = true;
        script.addEventListener("load", () => this.renderAfterScriptLoad(), { once: true });
        script.addEventListener("error", () => this.showFailure(), { once: true });
        if (existingScript) {
            existingScript.replaceWith(script);
        } else {
            this.form.append(script);
        }
    }

    retry() {
        this.lockSubmission();
        this.showPending();
        if (window.turnstile?.render) {
            this.renderAfterScriptLoad();
        } else {
            this.reloadScript();
        }
    }
}

function initializeTurnstileUX() {
    document.querySelectorAll(AUTH_FORM_SELECTOR).forEach((form) => {
        if (form.dataset.ltTurnstileUxInitialized === "true") {
            return;
        }
        form.dataset.ltTurnstileUxInitialized = "true";
        new PartnerHubTurnstileUX(form);
    });
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeTurnstileUX, { once: true });
} else {
    initializeTurnstileUX();
}
