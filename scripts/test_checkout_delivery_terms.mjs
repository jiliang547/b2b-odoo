import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_addons/b2b_website/static/src/js/checkout_delivery_terms.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '');
let count = 0;
function harness(marked = true, manual = false) {
    const badge = {dataset: {ltDeliveryTerms: 'EXW GUANGZHOU'}, textContent: 'EXW GUANGZHOU',
        hasAttribute: () => marked};
    class Checkout {
        constructor() {this.el = {querySelector: selector => manual ? (selector.includes('delivery-terms') ? badge : {}) : null};}
        async _prepareDeliveryMethods() {this.nativePrepare = true;}
        _updateCartSummary() {this.nativeSummary = true;}
        async _setDeliveryMethod(dm) {this.requestedCarrier = dm; return {b2b_delivery_terms:'FOB GUANGZHOU', success:true};}
        waitFor(promise) {return promise;}
        _updateCartSummaries(result) {this.summaryResult = result;}
        _enableMainButton() {this.continueEnabled = true;}
        _getDeliveryPriceBadge() {return badge;}
        _showLoadingBadge() {this.loading = true; badge.textContent = 'Loading';}
        _updateAmountBadge(_radio, rate) {this.native = true; badge.textContent = rate.success ? 'Free' : rate.error_message;}
        _toggleDeliveryMethodRadio() {this.enabled = true;}
    }
    vm.runInNewContext(source, {Checkout, patch(prototype, extension) {
        Object.setPrototypeOf(extension, Object.assign({}, prototype, {
            _showLoadingBadge: prototype._showLoadingBadge,
            _updateAmountBadge: prototype._updateAmountBadge,
            _prepareDeliveryMethods: prototype._prepareDeliveryMethods,
            _updateCartSummary: prototype._updateCartSummary,
        }));
        Object.assign(prototype, extension);
    }});
    return {checkout: new Checkout(), badge};
}
function check(name, fn) {fn(); count++; console.log('PASS '+name);}
check('free-delivery response preserves EXW rather than showing Free', () => {
    const {checkout, badge} = harness();
    checkout._updateAmountBadge({}, {success:true, is_free_delivery:true, b2b_delivery_terms:'EXW GUANGZHOU'});
    assert.equal(badge.textContent, 'EXW GUANGZHOU'); assert.equal(checkout.enabled, true); assert.equal(checkout.native, undefined);
});
check('updated server threshold switches the existing badge to FOB', () => {
    const {checkout, badge} = harness();
    checkout._updateAmountBadge({}, {success:true, amount_delivery:'$ 1000', b2b_delivery_terms:'FOB GUANGZHOU'});
    assert.equal(badge.textContent, 'FOB GUANGZHOU'); assert.equal(badge.dataset.ltDeliveryTerms, 'FOB GUANGZHOU');
});
check('after-delivery pricing does not override the agreed display terms', () => {
    const {checkout, badge} = harness();
    checkout._updateAmountBadge({}, {success:true, compute_price_after_delivery:true, b2b_delivery_terms:'EXW GUANGZHOU'});
    assert.equal(badge.textContent, 'EXW GUANGZHOU');
});
check('loading keeps the displayed terms and stable badge size', () => {
    const {checkout, badge} = harness(); checkout._showLoadingBadge({});
    assert.equal(badge.textContent, 'EXW GUANGZHOU'); assert.equal(checkout.loading, undefined);
});
check('missing or invalid response copy cannot insert HTML into the badge', () => {
    const {checkout, badge} = harness();
    checkout._updateAmountBadge({}, {success:true, b2b_delivery_terms:'<img onerror=bad>'});
    assert.equal(badge.textContent, 'EXW GUANGZHOU');
});
check('native carrier errors still surface and do not enable selection', () => {
    const {checkout, badge} = harness();
    checkout._updateAmountBadge({}, {success:false, error_message:'Carrier unavailable'});
    assert.equal(badge.textContent, 'Carrier unavailable'); assert.equal(checkout.native, true); assert.equal(checkout.enabled, undefined);
});
check('unmarked native checkout badges retain native price and loading behavior', () => {
    const {checkout, badge} = harness(false); checkout._showLoadingBadge({});
    assert.equal(checkout.loading, true);
    checkout._updateAmountBadge({}, {success:true, is_free_delivery:true}); assert.equal(badge.textContent, 'Free');
});
async function asyncCheck(name, fn) {await fn(); count++; console.log('PASS '+name);}
await asyncCheck('manual mode refreshes totals without selecting any carrier', async () => {
    const {checkout, badge} = harness(true, true);
    await checkout._prepareDeliveryMethods();
    assert.equal(checkout.requestedCarrier, null);
    assert.equal(checkout.dmRadios.length, 0);
    assert.equal(checkout.continueEnabled, true);
    assert.equal(badge.textContent, 'FOB GUANGZHOU');
    assert.equal(checkout.nativePrepare, undefined);
});
await asyncCheck('automatic mode retains native carrier initialization', async () => {
    const {checkout} = harness(); await checkout._prepareDeliveryMethods();
    assert.equal(checkout.nativePrepare, true);
    assert.equal(checkout.requestedCarrier, undefined);
});
check('manual summary tolerates absent freight row and updates native amounts', () => {
    const {checkout} = harness(true, true);
    const subtotal = {}, tax = {}, total = {};
    const target = {querySelector: selector => selector.includes('untaxed') ? subtotal : selector.includes('taxes') ? tax : null,
        parentElement: {querySelectorAll: () => [total]}};
    checkout._updateCartSummary({amount_untaxed:'$100',amount_tax:'$13',amount_total:'$113'},target);
    assert.equal(subtotal.innerHTML,'$100'); assert.equal(tax.innerHTML,'$13'); assert.equal(total.innerHTML,'$113');
});
check('manual summary also updates operator-entered freight', () => {
    const {checkout} = harness(true, true);
    const freight = {};
    checkout._updateCartSummary({amount_delivery:'$600'}, {querySelector: selector => selector.includes('delivery') ? freight : null,
        parentElement: {querySelectorAll: () => []}});
    assert.equal(freight.innerHTML,'$600');
});
console.log(count+' delivery display checks passed');
