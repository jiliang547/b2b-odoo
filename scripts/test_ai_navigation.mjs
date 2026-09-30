// Run with node --test scripts/test_ai_navigation.mjs. No browser or credentials.
import { readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
import test from 'node:test';
const source = await readFile(new URL('../custom_addons/b2b_ai/static/src/navigation_policy.js', import.meta.url), 'utf8');
const { isPageUrl, sameAssets } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const page = path => isPageUrl(new URL(path, 'https://example.test'));
for (const path of ['/', '/products', '/products/page/2', '/products/speaker-4', '/resources/3', '/faq', '/brands/lucky-tone', '/my', '/my/orders', '/my/orders/711', '/my/orders/711/collection', '/my/orders/711/request-change', '/shop/cart', '/shop/checkout', '/shop/payment', '/fr/products', '/products?search=speaker']) {
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
test('native lazy chatter assets do not force a reload when leaving orders', () => {
    assert.equal(sameAssets(doc([{src:'/a.js'}, {src:'/chatter.js'}]), doc([{src:'/a.js'}])), true);
});
test('signed-in portal links still use server record-token authorization', () => {
    assert.equal(isPageUrl(new URL('https://example.test/my/orders/711?access_token=fixture'), true), true);
    assert.equal(isPageUrl(new URL('https://example.test/my/orders/711?access_token=fixture&report_type=pdf'), true), false);
    assert.equal(isPageUrl(new URL('https://example.test/products?access_token=fixture'), true), false);
});
