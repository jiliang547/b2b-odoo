/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { Checkout } from "@website_sale/interactions/checkout";

const TERMS = new Set(["EXW GUANGZHOU", "FOB GUANGZHOU"]);

patch(Checkout.prototype, {
    async _prepareDeliveryMethods() {
        if (!this.el.querySelector("[data-lt-manual-freight]")) {
            return super._prepareDeliveryMethods(...arguments);
        }
        this.dmRadios = [];
        // Existing current-cart RPC refreshes native taxes/totals after an
        // address change. No carrier is chosen and no freight is created.
        const result = await this.waitFor(this._setDeliveryMethod(null));
        this._updateCartSummaries(result);
        const terms = this.el.querySelector("[data-lt-manual-delivery-terms]");
        if (terms && TERMS.has(result.b2b_delivery_terms)) {
            terms.textContent = result.b2b_delivery_terms;
        }
        this._enableMainButton();
    },
    _updateCartSummary(result, targetEl) {
        if (!this.el.querySelector("[data-lt-manual-freight]")) {
            return super._updateCartSummary(...arguments);
        }
        for (const [name, value] of [
            ["o_order_delivery", result.amount_delivery],
            ["o_order_total_untaxed", result.amount_untaxed],
            ["o_order_total_taxes", result.amount_tax],
        ]) {
            const amount = targetEl.querySelector(`tr[name="${name}"] .monetary_field`);
            if (amount) amount.innerHTML = value;
        }
        targetEl.parentElement.querySelectorAll(
            'tr[name="o_order_total"] .monetary_field, #amount_total_summary.monetary_field'
        ).forEach(amount => { amount.innerHTML = result.amount_total; });
    },
    _showLoadingBadge(radio) {
        const badge = this._getDeliveryPriceBadge(radio);
        if (!badge?.hasAttribute("data-lt-delivery-terms")) {
            return super._showLoadingBadge(...arguments);
        }
        // Keep the label/size stable. Native checkout still disables Continue
        // and validates the chosen carrier while the actual rate is fetched.
    },
    _updateAmountBadge(radio, rateData) {
        const badge = this._getDeliveryPriceBadge(radio);
        if (!badge?.hasAttribute("data-lt-delivery-terms") || !rateData.success) {
            return super._updateAmountBadge(...arguments);
        }
        const label = TERMS.has(rateData.b2b_delivery_terms)
            ? rateData.b2b_delivery_terms : badge.dataset.ltDeliveryTerms;
        if (!TERMS.has(label)) return super._updateAmountBadge(...arguments);
        badge.dataset.ltDeliveryTerms = label;
        badge.textContent = label;
        this._toggleDeliveryMethodRadio(radio);
    },
});
