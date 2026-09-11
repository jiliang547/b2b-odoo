// Focused unit checks for the production patch; actual click tests complement these.
// Usage: node scripts/test_payment_form.mjs <path-to-odoo-addons>
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import vm from 'node:vm';

const addonRoot = process.argv[2];
assert.ok(addonRoot, 'Pass the installed Odoo addons path');
const nativePatch = readFileSync(resolve(addonRoot, 'web/static/src/core/utils/patch.js'), 'utf8');
const implementation = readFileSync(new URL('../custom_addons/b2b_website/static/src/js/payment_form.js', import.meta.url), 'utf8');
const events = () => ({ preventDefault() {}, stopPropagation() {} });
let calls = 0;
class PaymentForm {
    async submitForm() { calls++; this.submittedFlow = this.flow; if (this.failSubmit) throw Error('transaction failed'); }
    async _expandInlineForm() { if (this.gate) await this.gate; if (this.failInit) throw Error('provider failed'); this.flow = this.providerFlow; }
    _disableButton() { this.disabled = true; }
    _enableButton() { this.disabled = false; this.unblocked = true; }
    _displayErrorDialog() { this.dialogShown = true; }
    waitFor(promise) { return promise; }
}
const context = vm.createContext({
    PaymentForm,
    _t: value => value,
    console: { error() {} },
    document: { createElement: () => ({ dataset: {}, setAttribute() {} }) },
});
vm.runInContext(nativePatch.replace('export function patch', 'function patch'), context);
vm.runInContext(implementation.replace(/^import .*;\r?$/gm, ''), context);
function form(flow = 'direct') {
    const instance = new PaymentForm();
    instance.providerFlow = flow;
    instance.flow = 'redirect'; // Reproduce stale initial context.
    instance.radio = {};
    instance.el = {
        querySelector(selector) {
            return selector.includes('o_payment_radio') ? instance.radio : instance.alert;
        },
        appendChild(alert) {
            instance.alert = alert;
            alert.remove = () => { instance.alert = undefined; };
        },
    };
    return instance;
}

for (const flow of ['direct', 'redirect', 'token']) {
    const instance = form(flow);
    await instance.submitForm(events());
    assert.equal(instance.submittedFlow, flow);
}
for (const failure of ['failInit', 'failSubmit']) {
    const instance = form();
    instance[failure] = true;
    await instance.submitForm(events());
    assert.equal(instance.disabled, false);
    assert.equal(instance.unblocked, true);
    assert.equal(instance.b2bPaymentSubmitting, false);
    assert.match(instance.alert.textContent, /refresh/);
    instance[failure] = false;
    await instance.submitForm(events());
    assert.equal(instance.submittedFlow, 'direct');
    assert.equal(instance.alert, undefined);
}
const absent = form();
absent.radio = null;
const previousCalls = calls;
await absent.submitForm(events());
assert.equal(absent.dialogShown, true);
assert.equal(calls, previousCalls);

const duplicate = form();
let release;
duplicate.gate = new Promise(resolve => { release = resolve; });
const first = duplicate.submitForm(events());
await duplicate.submitForm(events());
const callsBeforeRelease = calls;
release();
await first;
assert.equal(calls, callsBeforeRelease + 1);
console.log('PASS: 7 payment patch scenarios (provider flow x3, failure/retry x2, no selection, duplicate submit)');
