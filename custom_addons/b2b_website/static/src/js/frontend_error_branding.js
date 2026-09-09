/** @odoo-module **/

import { browser } from "@web/core/browser/browser";
import {
    UncaughtClientError,
    UncaughtPromiseError,
    ThirdPartyScriptError,
} from "@web/core/errors/error_service";
import { _t } from "@web/core/l10n/translation";
import {
    ConnectionLostError,
    RequestEntityTooLargeError,
    RPCError,
    rpc,
} from "@web/core/network/rpc";
import { registry } from "@web/core/registry";

const SESSION_EXPIRED = "odoo.http.SessionExpiredException";
const FORBIDDEN = "werkzeug.exceptions.Forbidden";
const LOGOUT_SELECTOR = 'a[href^="/web/session/logout"]';
const LOGOUT_GRACE_PERIOD = 15000;

let intentionalLogout = false;
let logoutResetTimer = null;
let connectionNotificationRemove = null;

function redirectToLogin() {
    const returnPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
    window.location.assign(`/web/login?redirect=${encodeURIComponent(returnPath)}`);
}

function markIntentionalLogout(event) {
    if (!event.target.closest?.(LOGOUT_SELECTOR)) {
        return;
    }
    intentionalLogout = true;
    browser.clearTimeout(logoutResetTimer);
    logoutResetTimer = browser.setTimeout(() => {
        intentionalLogout = false;
    }, LOGOUT_GRACE_PERIOD);
}

document.addEventListener("click", markIntentionalLogout, true);

function preventUnhandled(error) {
    error.unhandledRejectionEvent?.preventDefault();
}

function exceptionName(originalError) {
    return originalError?.exceptionName || originalError?.data?.name || "";
}

function addNotification(env, message, options = {}) {
    env.services.notification.add(message, {
        type: "warning",
        ...options,
    });
}

function showSessionEnded(env) {
    addNotification(
        env,
        _t("Your Partner Hub session is no longer active. Please sign in again to continue."),
        {
            title: _t("Session Ended"),
            sticky: true,
            buttons: [
                {
                    text: _t("Sign In Again"),
                    click: redirectToLogin,
                    close: true,
                },
            ],
        }
    );
}

function showAccessCouldNotBeConfirmed(env) {
    addNotification(env, _t("Please refresh the page or sign in again."), {
        title: _t("Access Could Not Be Confirmed"),
        sticky: true,
        buttons: [
            {
                text: _t("Sign In Again"),
                click: redirectToLogin,
                close: true,
            },
        ],
    });
}

const notificationTitles = {
    "odoo.exceptions.AccessDenied": _t("Access Could Not Be Confirmed"),
    "odoo.exceptions.AccessError": _t("Access Could Not Be Confirmed"),
    "odoo.exceptions.MissingError": _t("Information Not Available"),
    "odoo.exceptions.UserError": _t("Action Not Available"),
    "odoo.exceptions.ValidationError": _t("Please Review the Information"),
    "odoo.exceptions.Warning": _t("Please Review the Information"),
};

function partnerHubErrorHandler(env, error, originalError) {
    if (originalError instanceof ConnectionLostError) {
        preventUnhandled(error);
        if (connectionNotificationRemove) {
            return true;
        }
        connectionNotificationRemove = env.services.notification.add(
            _t("We lost the connection and are trying to reconnect."),
            { title: _t("Connection Interrupted"), sticky: true, type: "warning" }
        );
        let delay = 2000;
        browser.setTimeout(function checkConnection() {
            rpc("/web/webclient/version_info", {})
                .then(() => {
                    connectionNotificationRemove?.();
                    connectionNotificationRemove = null;
                    env.services.notification.add(_t("You are back online."), {
                        title: _t("Connection Restored"),
                        type: "info",
                    });
                })
                .catch(() => {
                    delay = delay * 1.5 + 500 * Math.random();
                    browser.setTimeout(checkConnection, delay);
                });
        }, delay);
        return true;
    }

    if (originalError instanceof RequestEntityTooLargeError) {
        preventUnhandled(error);
        addNotification(env, _t("Please choose a smaller file and try again."), {
            title: _t("File Too Large"),
        });
        return true;
    }

    if (originalError instanceof RPCError) {
        preventUnhandled(error);
        const name = exceptionName(originalError);
        if (intentionalLogout && (name === SESSION_EXPIRED || name === FORBIDDEN)) {
            return true;
        }
        if (name === SESSION_EXPIRED) {
            showSessionEnded(env);
            return true;
        }
        if (name === FORBIDDEN) {
            showAccessCouldNotBeConfirmed(env);
            return true;
        }
        if (name === "504" || String(originalError.code) === "504") {
            addNotification(env, _t("The request took too long. Please try again."), {
                title: _t("Request Timed Out"),
            });
            return true;
        }
        if (notificationTitles[name]) {
            addNotification(
                env,
                originalError.data?.message || originalError.message || _t("Please try again."),
                { title: notificationTitles[name] }
            );
            return true;
        }
        addNotification(env, _t("We could not complete the request. Please try again."), {
            title: _t("Something Went Wrong"),
        });
        return true;
    }

    if (
        error instanceof UncaughtClientError ||
        error instanceof UncaughtPromiseError ||
        error instanceof ThirdPartyScriptError
    ) {
        preventUnhandled(error);
        console.error("Partner Hub frontend error", originalError || error);
        addNotification(env, _t("Please refresh the page and try again."), {
            title: _t("Something Went Wrong"),
        });
        return true;
    }
    return false;
}

registry.category("error_handlers").add("partnerHubErrorHandler", partnerHubErrorHandler, {
    sequence: -20,
});

// Keep the canonical notification registry branded as a fallback for any
// framework path that bypasses the frontend error handler above.
registry.category("error_notifications").add(
    SESSION_EXPIRED,
    {
        title: _t("Session Ended"),
        message: _t("Your Partner Hub session is no longer active. Please sign in again to continue."),
        type: "warning",
        sticky: true,
        buttons: [
            { text: _t("Sign In Again"), click: redirectToLogin, close: true },
        ],
    },
    { force: true }
);
registry.category("error_notifications").add(
    FORBIDDEN,
    {
        title: _t("Access Could Not Be Confirmed"),
        message: _t("Please refresh the page or sign in again."),
        type: "warning",
        sticky: true,
        buttons: [
            { text: _t("Sign In Again"), click: redirectToLogin, close: true },
        ],
    },
    { force: true }
);
registry.category("error_notifications").add(
    "504",
    {
        title: _t("Request Timed Out"),
        message: _t("The request took too long. Please try again."),
        type: "warning",
    },
    { force: true }
);
