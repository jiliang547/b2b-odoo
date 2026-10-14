/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

export function passwordPolicyError(value, minimum, letterNumber, message) {
    if (!value) return _t("Please enter a password.");
    // Python's native policy counts Unicode characters, not UTF-16 code units.
    if ([...value].length < minimum
        || (letterNumber && (!/[A-Za-z]/.test(value) || !/[0-9]/.test(value)))) {
        return message;
    }
    return "";
}

export function initializePasswordValidation() {
    for (const password of document.querySelectorAll("input[data-lt-password-policy]")) {
        const form = password.form;
        if (!form || form.dataset.ltPasswordsInitialized) continue;
        form.dataset.ltPasswordsInitialized = "1";
        const confirmation = form.querySelector("input[data-lt-password-confirm]");
        const show = (field, message) => {
            field.setCustomValidity(message);
            field.setAttribute("aria-invalid", message ? "true" : "false");
            const error = form.querySelector(`#${field.id}_error`);
            if (error) error.textContent = message;
        };
        const validatePassword = () => {
            const message = passwordPolicyError(password.value,
                Number(password.dataset.ltPasswordPolicy),
                password.dataset.ltLetterNumber === "1", password.dataset.ltPasswordMessage);
            show(password, message);
            return !message;
        };
        const validateConfirmation = () => {
            if (!confirmation) return true;
            const message = !confirmation.value ? _t("Please confirm your password.")
                : confirmation.value !== password.value
                    ? _t("Passwords do not match; please retype them.") : "";
            show(confirmation, message);
            return !message;
        };
        password.addEventListener("blur", validatePassword);
        password.addEventListener("input", () => {
            if (password.value) validatePassword();
            else show(password, "");
            if (confirmation?.value) validateConfirmation();
        });
        confirmation?.addEventListener("blur", validateConfirmation);
        confirmation?.addEventListener("input", validateConfirmation);
        // Constraint validation precedes submit. Suppress browser-language
        // popups and show our field-level English/translatable feedback.
        form.addEventListener("invalid", (event) => {
            if (event.target !== password && event.target !== confirmation) return;
            event.preventDefault();
            if (event.target === password) validatePassword();
            else validateConfirmation();
        }, true);
        form.addEventListener("submit", (event) => {
            const passwordOK = validatePassword();
            const confirmationOK = validateConfirmation();
            if (!passwordOK || !confirmationOK) {
                event.preventDefault();
                event.stopImmediatePropagation();
                (passwordOK ? confirmation : password).focus();
            }
        }, true);
    }
}
