// Execute the production idempotent opener, without creating a payment.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_addons/b2b_website/static/src/js/payment_modal.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '').replace('export async function', 'async function');
const modal = {isConnected: true};
const trigger = {isConnected: true};
let clicks, shows = 0, visible = false, loads = 0;
const nativeModal = {getOrCreateInstance: el => {
    assert.equal(el, modal);
    return {show: () => {shows++; visible = true;}};
}};
const context = vm.createContext({
    document: {getElementById: () => modal, addEventListener: (event, handler, capture) => {
        assert.equal(event, 'click'); assert.equal(capture, true); clicks = handler;
    }},
    window: {Modal: nativeModal, location: {reload: () => {throw Error('Unexpected reload');}}},
    loadBundle: async bundle => {assert.equal(bundle, 'web.assets_frontend_lazy'); loads++; context.window.Modal = nativeModal;},
});
vm.runInContext(source, context);
await context.openPaymentModal(trigger); // Native auto-open.
await context.openPaymentModal(trigger); // First customer click must not toggle closed.
assert.equal(visible, true);
assert.equal(shows, 2);
visible = false; // Native dismiss remains available.
await context.openPaymentModal(trigger);
assert.equal(visible, true);
context.window.Modal = undefined;
await context.openPaymentModal(trigger);
assert.equal(loads, 1);
modal.isConnected = false;
await context.openPaymentModal(trigger);
assert.equal(shows, 4);
modal.isConnected = true;
let prevented = false, stopped = false;
clicks({target: {closest: () => trigger}, preventDefault() {prevented = true;},
    stopImmediatePropagation() {stopped = true;}});
await Promise.resolve();
assert.equal(prevented, true);
assert.equal(stopped, true);
console.log('PASS: native auto-open + first click, native close/reopen, lazy assets, detached page, capture guard');
