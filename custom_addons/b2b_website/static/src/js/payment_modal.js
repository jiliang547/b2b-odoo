/** @odoo-module **/
import { loadBundle } from "@web/core/assets";

// Both native prepayment auto-open and the customer's click target the same
// Bootstrap trigger. toggle() can close the modal while the lazy interactions
// start. Keep the native modal, form and dismiss controls; opening is idempotent.
export async function openPaymentModal(trigger) {
    const modal = document.getElementById("modalaccept");
    if (!modal || !trigger.isConnected) return;
    if (!window.Modal) await loadBundle("web.assets_frontend_lazy");
    if (modal.isConnected && trigger.isConnected && window.Modal) {
        window.Modal.getOrCreateInstance(modal).show(trigger);
    }
}

document.addEventListener("click", event => {
    const trigger = event.target.closest?.('[data-bs-toggle="modal"][data-bs-target="#modalaccept"]');
    if (!trigger || !document.getElementById("modalaccept")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    openPaymentModal(trigger).catch(() => {
        // A failed asset load must not create a transaction or a second modal.
        window.location.reload();
    });
}, true);
