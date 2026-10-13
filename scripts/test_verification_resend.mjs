// Checks the production countdown; browser clicks are verified separately.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_addons/b2b_website/static/src/js/verification_resend.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replaceAll('export function ', 'function ');
function harness(delay = 60) {
    let now = 1000, callback, starts = 0, clears = 0;
    const button = {disabled: false, textContent: 'Resend Verification Email'};
    const feedback = {hidden: true, textContent: ''};
    const form = {isConnected: true, dataset: {ltResendDelay: String(delay)},
        querySelector: selector => selector.includes('button') ? button : feedback};
    const context = vm.createContext({document: {querySelectorAll: () => [form]}, Date: {now: () => now},
        _t: (value, arg) => value.replace('%s', arg),
        setInterval(fn) {callback = fn; starts++; return 1;}, clearInterval() {clears++;}});
    vm.runInContext(source + '\nglobalThis.initialize = initializeVerificationResend; globalThis.remaining = verificationResendSeconds;', context);
    return {context, button, feedback, form, tick: value => {now = value; callback?.();}, counts: () => ({starts, clears})};
}
const h = harness();
assert.equal(h.context.remaining(2000, 1001), 1);
assert.equal(h.context.remaining(2000, 2000), 0);
assert.equal(h.context.remaining(2000, 3000), 0);
h.context.initialize();
assert.equal(h.button.disabled, true);
assert.equal(h.feedback.hidden, false);
assert.equal(h.feedback.textContent, 'You can resend in 60 seconds.');
h.tick(56001);
assert.equal(h.feedback.textContent, 'You can resend in 5 seconds.');
h.tick(61000);
assert.equal(h.button.disabled, false);
assert.equal(h.button.textContent, 'Resend Verification Email');
assert.equal(h.feedback.textContent, 'You can request another verification email now.');
assert.equal(h.counts().clears, 1);
h.context.initialize();
assert.equal(h.counts().starts, 1);
const none = harness(0);
none.context.initialize();
assert.equal(none.counts().starts, 0);
assert.equal(none.button.disabled, false);
const detached = harness();
detached.context.initialize();
detached.form.isConnected = false;
detached.tick(2000);
assert.equal(detached.counts().clears, 1);
console.log('Verification countdown: 15 assertions passed.');
