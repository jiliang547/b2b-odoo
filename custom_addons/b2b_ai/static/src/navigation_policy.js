/** @odoo-module **/
// Only navigational GETs. Unknown routes, downloads, auth and payment actions
// deliberately keep the native browser lifecycle. Never intercept POSTs.
const PUBLIC_PAGES = new Set(["/", "/partner-home", "/products", "/shop", "/resources", "/brands",
    "/about", "/solutions", "/contact", "/contactus", "/faq", "/shipping", "/warranty",
    "/repair-service", "/samples", "/service-center", "/service", "/privacy", "/terms-of-use", "/sample/request"]);

export function isPageUrl(url, signedIn = false) {
    const path = url.pathname.replace(/^\/(?!my\/)[a-z]{2}(?:_[A-Z]{2})?(?=\/)/, "").replace(/\/$/, "") || "/";
    if ([...url.searchParams.keys()].some(key => /^(?:download|report_type|token|debug|enable_editor|edit_translations|fw|payment_status|redirect)$/.test(key))) return false;
    // Native portal links may include a record token even for the signed-in owner.
    // Keep native server authorization, no HTML cache, and verify chat identity.
    if (url.searchParams.has("access_token") && !(signedIn && /^\/my\/(orders|invoices|ticket)\/\d+$/.test(path))) return false;
    return PUBLIC_PAGES.has(path) ||
        /^\/(?:products|shop)\/(?:page\/\d+|[^/]+-\d+)$/.test(path) ||
        /^\/(?:resources|brands)\/[^/]+$/.test(path) ||
        /^\/my(?:\/(?:home|account|addresses|company(?:\/change|\/users)?|orders|quotes|invoices|inquiries|messages|tickets|sample-requests|order-changes)(?:\/page\/\d+)?)?$/.test(path) ||
        /^\/my\/(?:orders|quotes|invoices|inquiries|ticket|tickets|sample-requests|order-changes)\/\d+(?:\/collection|\/request-change|\/erp-status)?$/.test(path) ||
        /^\/shop\/(?:cart|checkout|address|payment)$/.test(path);
}

export function sameAssets(current, next) {
    const urls = doc => new Set([...doc.querySelectorAll('script[src], script[data-src], head link[rel="stylesheet"]')]
        .map(el => el.getAttribute('src') || el.getAttribute('data-src') || el.getAttribute('href')));
    const loaded = urls(current);
    // Odoo lazily loads chatter/provider libraries. They can remain cached;
    // every bundle required by the destination must already be available.
    return [...urls(next)].every(url => loaded.has(url));
}
