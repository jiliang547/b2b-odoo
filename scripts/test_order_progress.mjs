// Tests the production interaction's state machine; real UI clicks are also required.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../custom_addons/b2b_yonyou/static/src/progress.js', import.meta.url), 'utf8')
    .replace(/^import .*;\r?\n/gm, '');

function harness() {
    let now = 0, serial = 0, InteractionClass;
    const timers = new Map(), calls = [], replies = [];
    const nodes = {};
    for (const name of ['feedback', 'cooldown', 'panel', 'updated', 'button-label']) {
        nodes[name] = {textContent: '', innerHTML: ''};
    }
    const icon = {classList: {toggle() {}}};
    const button = {disabled: false, setAttribute() {}, querySelector: s => s === 'i' ? icon : nodes['button-label']};
    const root = {isConnected: true, dataset: {refreshSupported: 'true', retryAfter: '0', pending: 'false',
        checkUrl: '/check', refreshUrl: '/refresh', contentKey: 'old', updatedAt: '2026-10-12 01:00:00'},
        querySelector: s => s === '[data-progress-refresh]' ? button : nodes[s.match(/data-progress-([\w-]+)/)[1]]};
    const sandbox = {Interaction: class {registerCleanup(fn) {this.cleanup = fn;}},
        registry: {category: () => ({add: (_name, cls) => {InteractionClass = cls;}})},
        _t: (s, ...args) => args.reduce((t, a) => t.replace('%s', a), s),
        Date: {now: () => now}, AbortController,
        setTimeout: (fn, delay) => {const id = ++serial; timers.set(id, {fn, delay}); return id;},
        clearTimeout: id => timers.delete(id),
        fetch: async url => {
            calls.push(url);
            const result = replies.shift();
            if (result instanceof Error) throw result;
            if (typeof result === 'function') return result();
            return {ok: true, json: async () => ({result})};
        }};
    vm.runInNewContext(source, sandbox);
    const instance = new InteractionClass();
    instance.el = root;
    instance.start();
    return {instance, root, nodes, button, calls, replies, timers, setNow: value => {now = value;}};
}

const result = (overrides = {}) => ({pending: false, refresh: {supported: true, retry_after: 0},
    content_key: 'old', updated_at: '2026-10-12 01:02:00', delayed: false, html: '<p>Cached progress</p>', ...overrides});
const event = {preventDefault() {}};
let count = 0;
async function test(name, run) {await run(); count++; console.log('PASS', name);}

await test('ready page does not poll or query ERP', () => {
    const h = harness(); assert.equal(h.button.disabled, false); assert.equal(h.calls.length, 0);
});
await test('manual click queues once, waits, updates only the panel and not the button', async () => {
    const h = harness(); const original = h.button;
    h.replies.push(result({pending: true})); await h.instance.refresh(event);
    await h.instance.refresh(event);
    assert.deepEqual(h.calls, ['/refresh']); assert.equal(h.button.disabled, true);
    assert.equal(h.nodes['button-label'].textContent, 'Refreshing…');
    h.replies.push(result({content_key: 'new', refresh: {supported: true, retry_after: 60}}));
    await h.instance.check();
    assert.equal(h.nodes.feedback.textContent, 'Progress updated.');
    assert.equal(h.button, original); assert.equal(h.nodes.panel.innerHTML, '<p>Cached progress</p>');
    assert.equal(h.button.disabled, true);
    h.setNow(61000); h.instance.updateButton(); assert.equal(h.button.disabled, false);
});
await test('successful fresh check with identical content says no new updates', async () => {
    const h = harness(); h.replies.push(result({pending: true})); await h.instance.refresh(event);
    h.replies.push(result()); await h.instance.check();
    assert.equal(h.nodes.feedback.textContent, 'Progress checked. No new updates.');
});
await test('joining a lock without a completed check does not claim success', async () => {
    const h = harness(); h.replies.push(result({pending: true})); await h.instance.refresh(event);
    h.replies.push(result({updated_at: h.root.dataset.updatedAt})); await h.instance.check();
    assert.match(h.nodes.feedback.textContent, /No new check has completed/);
});
await test('network errors keep existing cards and are handled inline', async () => {
    const h = harness(); h.nodes.panel.innerHTML = '<p>Original cards</p>';
    h.replies.push(new Error('network')); await h.instance.refresh(event);
    assert.equal(h.nodes.panel.innerHTML, '<p>Original cards</p>');
    assert.match(h.nodes.feedback.textContent, /last available progress has been kept/);
    assert.equal(h.instance.busy, false);
});
await test('server backoff disables refresh without dropping stored data', async () => {
    const h = harness(); h.replies.push(result({delayed: true, refresh: {supported: true, retry_after: 300}}));
    await h.instance.refresh(event); assert.equal(h.button.disabled, true);
    assert.match(h.nodes.cooldown.textContent, /5 minutes/);
    assert.equal(h.nodes.panel.innerHTML, '<p>Cached progress</p>');
});
await test('waiting is bounded and allows checking the existing job again', async () => {
    const h = harness(); h.replies.push(result({pending: true})); await h.instance.refresh(event);
    h.setNow(91000); await h.instance.check();
    assert.match(h.nodes.feedback.textContent, /still being processed/);
    assert.equal(h.instance.waiting, false); assert.equal(h.button.disabled, false);
});
await test('destroyed pages do not mutate DOM after a late response', async () => {
    const h = harness(); let resolve;
    h.replies.push(() => new Promise(r => {resolve = r;}));
    const pending = h.instance.refresh(event);
    h.instance.cleanup(); h.root.isConnected = false;
    const before = h.nodes.panel.innerHTML;
    resolve({ok: true, json: async () => ({result: result()})}); await pending;
    assert.equal(h.nodes.panel.innerHTML, before); assert.equal(h.timers.size, 0);
});
await test('malformed RPC data is not inserted into the page', async () => {
    const h = harness(); h.nodes.panel.innerHTML = 'Safe contents';
    h.replies.push({pending: false, html: '<script>bad</script>'}); await h.instance.refresh(event);
    assert.equal(h.nodes.panel.innerHTML, 'Safe contents');
});
console.log(`${count} interaction tests passed`);
