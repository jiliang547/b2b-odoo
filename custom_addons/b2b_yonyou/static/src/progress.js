/** @odoo-module **/
import { Interaction } from "@web/public/interaction";
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

class OrderProgress extends Interaction {
    static selector = ".lt-order-progress";
    dynamicContent = { "[data-progress-refresh]": { "t-on-click": this.refresh } };

    start() {
        this.stopped = false;
        this.busy = false;
        this.waiting = false;
        this.manualCycle = false;
        this.supported = this.el.dataset.refreshSupported === "true";
        this.contentKey = this.el.dataset.contentKey;
        this.updatedAt = this.el.dataset.updatedAt || false;
        this.setCooldown(Number(this.el.dataset.retryAfter || 0));
        this.registerCleanup(() => {
            this.stopped = true;
            clearTimeout(this.timer);
            clearTimeout(this.cooldownTimer);
            this.controller?.abort();
        });
        if (this.el.dataset.pending === "true") this.beginWaiting();
        else this.updateButton();
    }

    alive() { return !this.stopped && !this.isDestroyed && this.el.isConnected; }

    setFeedback(message) {
        if (this.alive()) this.el.querySelector("[data-progress-feedback]").textContent = message;
    }

    setCooldown(seconds) {
        this.cooldownUntil = Date.now() + Math.max(0, seconds) * 1000;
        this.updateButton();
    }

    updateButton() {
        if (!this.alive()) return;
        clearTimeout(this.cooldownTimer);
        const seconds = Math.max(0, Math.ceil((this.cooldownUntil - Date.now()) / 1000));
        const button = this.el.querySelector("[data-progress-refresh]");
        const pending = this.busy || this.waiting;
        button.disabled = pending || !this.supported || seconds > 0;
        button.setAttribute("aria-busy", String(pending));
        button.querySelector("i").classList.toggle("fa-spin", pending);
        button.querySelector("[data-progress-button-label]").textContent =
            pending ? _t("Refreshing…") : _t("Refresh Progress");
        this.el.querySelector("[data-progress-cooldown]").textContent =
            !pending && this.supported && seconds > 0 ?
                seconds >= 120 ? _t("Refresh available in %s minutes.", Math.ceil(seconds / 60)) :
                seconds >= 60 ? _t("Refresh available in 1 minute.") :
                    _t("Refresh available in %s seconds.", seconds) : "";
        if (seconds > 0) this.cooldownTimer = setTimeout(() => this.updateButton(), 1000);
    }

    beginWaiting() {
        clearTimeout(this.timer);
        this.waiting = true;
        this.deadline = Date.now() + 90000;
        this.updateButton();
        this.schedule();
    }

    schedule() { this.timer = setTimeout(() => this.check(), 3000); }

    stopWaiting(message) {
        this.waiting = false;
        clearTimeout(this.timer);
        this.setFeedback(message);
        this.updateButton();
    }

    async post(url) {
        this.controller = new AbortController();
        const timeout = setTimeout(() => this.controller.abort(), 8000);
        try {
            const response = await fetch(url, {
                method: "POST", credentials: "same-origin", signal: this.controller.signal,
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {}, id: 1 }),
            });
            if (!response.ok) throw new Error("Progress request failed");
            const data = await response.json();
            const result = data.result;
            if (data.error || !result || typeof result.pending !== "boolean" ||
                typeof result.html !== "string" || typeof result.refresh?.supported !== "boolean" ||
                !Number.isFinite(result.refresh.retry_after) || result.refresh.retry_after < 0) {
                throw new Error("Progress request failed");
            }
            return result;
        } finally {
            clearTimeout(timeout);
        }
    }

    applyResult(result) {
        if (!this.alive()) return;
        this.supported = result.refresh.supported;
        this.setCooldown(result.refresh.retry_after);
        // Replace only the escaped QWeb contents, not the interaction/button.
        this.el.querySelector("[data-progress-panel]").innerHTML = result.html;
        this.el.querySelector("[data-progress-updated]").textContent =
            result.updated_at ? result.updated_at + " UTC" : _t("Not checked yet");
        this.el.dataset.pending = String(result.pending);
        if (!result.pending) {
            this.waiting = false;
            if (this.manualCycle) {
                const message = result.delayed ?
                    _t("Updates are temporarily delayed. Your last available progress has been kept.") :
                    !result.refresh.supported ? _t("Order progress is temporarily unavailable.") :
                    this.priorUpdatedAt === result.updated_at ? _t("No new check has completed. Please try again shortly.") :
                    this.priorContentKey === result.content_key ? _t("Progress checked. No new updates.") :
                    _t("Progress updated.");
                this.setFeedback(message);
                this.manualCycle = false;
            }
            this.contentKey = result.content_key;
            this.updatedAt = result.updated_at;
        }
        this.updateButton();
    }

    async refresh(event) {
        event.preventDefault();
        if (!this.alive() || this.busy || this.waiting || !this.supported || Date.now() < this.cooldownUntil) return;
        this.busy = true;
        this.manualCycle = true;
        this.priorContentKey = this.contentKey;
        this.priorUpdatedAt = this.updatedAt;
        this.setFeedback(_t("Checking the latest order progress…"));
        this.updateButton();
        try {
            const result = await this.post(this.el.dataset.refreshUrl);
            if (!this.alive()) return;
            this.applyResult(result);
            if (result.pending) this.beginWaiting();
            else if (result.refresh.retry_after > 0) {
                this.manualCycle = false;
                this.setFeedback(_t("Please wait before requesting another update."));
            }
        } catch {
            if (this.alive()) {
                this.manualCycle = false;
                this.stopWaiting(_t("We could not check for updates. Please try again later. Your last available progress has been kept."));
            }
        } finally {
            this.busy = false;
            this.updateButton();
        }
    }

    async check() {
        if (!this.alive()) return;
        if (Date.now() >= this.deadline) {
            this.manualCycle = false;
            this.stopWaiting(_t("Your update is still being processed. Use Refresh Progress to check again later."));
            return;
        }
        try {
            const result = await this.post(this.el.dataset.checkUrl);
            if (!this.alive()) return;
            this.applyResult(result);
            if (result.pending) this.schedule();
        } catch {
            if (this.alive()) {
                this.manualCycle = false;
                this.stopWaiting(_t("Updates are temporarily delayed. Your last available progress has been kept. Please try again later."));
            }
        }
    }
}
registry.category("public.interactions").add("b2b_yonyou.order_progress", OrderProgress);
