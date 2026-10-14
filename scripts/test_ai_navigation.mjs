// Run with node --test scripts/test_ai_navigation.mjs. No browser or credentials.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
const source = await readFile(new URL('../custom_addons/b2b_ai/static/src/navigation_policy.js', import.meta.url), 'utf8');
const { isPageUrl, sameAssets, hasNativeChatter } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const page = path => isPageUrl(new URL(path, 'https://example.test'));
for (const path of ['/', '/products', '/products/page/2', '/products/speaker-4', '/resources/3', '/faq', '/brands/lucky-tone', '/my', '/my/orders', '/shop/cart', '/shop/checkout', '/shop/payment', '/fr/products', '/products?search=speaker']) {
    test('navigational GET ' + path, () => assert.equal(page(path), true));
}
for (const path of ['/web/login', '/web/session/logout', '/register', '/payment/status', '/payment/paypal/return', '/shop/b2b-submit-order', '/shop/cart/update', '/my/orders/711/collection/proof', '/my/orders/711/collection/pi', '/my/orders/711/cancel', '/my/orders/711?access_token=private', '/my/invoices/2?report_type=pdf', '/products?debug=assets', '/products/resource/3', '/odoo', '/my/orders/711/sign', '/unknown-page']) {
    test('native lifecycle ' + path, () => assert.equal(page(path), false));
}
const doc = assets => ({ querySelectorAll: () => assets.map(attrs => ({ getAttribute: key => attrs[key] || null })) });
test('native lazy-loader src transformation is compatible', () => {
    assert.equal(sameAssets(doc([{src:'/a.js'}, {src:'/b.js'}]), doc([{src:'/a.js'}, {'data-src':'/b.js'}])), true);
});
test('new bundle requires full navigation', () => {
    assert.equal(sameAssets(doc([{src:'/a.js'}]), doc([{src:'/b.js'}])), false);
});
test('asset compatibility alone does not imply page lifecycle compatibility', () => {
    assert.equal(sameAssets(doc([{src:'/a.js'}, {src:'/chatter.js'}]), doc([{src:'/a.js'}])), true);
});
test('signed-in portal links still use server record-token authorization', () => {
    assert.equal(isPageUrl(new URL('https://example.test/my/orders/711?access_token=fixture'), true), false);
    assert.equal(isPageUrl(new URL('https://example.test/my/orders/711?access_token=fixture&report_type=pdf'), true), false);
    assert.equal(isPageUrl(new URL('https://example.test/products?access_token=fixture'), true), false);
});

for (const path of ['/helpdesk/ticket/2', '/my/ticket/2', '/my/tickets/2', '/my/orders/711',
    '/my/orders/711/collection', '/my/orders/711/request-change', '/my/quotes/2',
    '/my/invoices/2', '/my/inquiries/2', '/my/sample-requests/2', '/my/order-changes/2',
    '/fr/my/ticket/2', '/zh_CN/helpdesk/ticket/2']) {
    test('chatter detail always uses native navigation: ' + path, () => assert.equal(page(path), false));
}

const navigatorSource = (await readFile(new URL('../custom_addons/b2b_ai/static/src/navigation.js', import.meta.url), 'utf8'))
    .replace(/^import .*;$/gm, '').replace('export class WebsiteNavigator', 'class WebsiteNavigator');
function fixture(currentChatter = false) {
    const document = { querySelector: selector => selector.includes('.o_portal_chatter') && currentChatter ? {} : null };
    const assigned = [];
    const context = { document, URL, isPageUrl, sameAssets, hasNativeChatter,
        location: { origin: 'https://example.test', href: 'https://example.test/', assign: url => assigned.push(url) }, history: {} };
    vm.createContext(context);
    vm.runInContext(navigatorSource + '\nthis.Navigator = WebsiteNavigator;', context);
    const nav = Object.create(context.Navigator.prototype);
    Object.assign(nav, {current:'https://example.test/', assistant:{state:{signedIn:true}}});
    return {nav, assigned};
}
test('leaving a page containing lazy chatter is blocked even on ordinary URLs', () => {
    assert.equal(fixture(true).nav.available(), false);
    assert.equal(fixture(false).nav.available(), true);
});
test('target chatter is rejected before touching or replacing DOM', () => {
    assert.equal(fixture(false).nav.compatible({querySelector: () => ({})}), false);
});
test('back/forward from detached-risk page uses a native navigation', async () => {
    const {nav, assigned} = fixture(true);
    await nav.navigate(new URL('https://example.test/products'), true);
    assert.deepEqual(assigned, ['https://example.test/products']);
});
test('known detail destination bypasses fetch and DOM replacement', async () => {
    const {nav, assigned} = fixture();
    await nav.navigate(new URL('https://example.test/my/ticket/2'));
    assert.deepEqual(assigned, ['https://example.test/my/ticket/2']);
});
