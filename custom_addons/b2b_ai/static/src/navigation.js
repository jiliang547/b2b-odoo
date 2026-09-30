/** @odoo-module **/
import { initializePartnerHub } from "@b2b_website/js/partner_hub";
import { isPageUrl, sameAssets } from "@b2b_ai/navigation_policy";

const ASSISTANT = 'owl-component[name="b2b_ai.FloatingAssistant"]';
const EXECUTABLE = 'script:not([type="application/ld+json"]):not([type="application/json"])';

// The native public.interactions service also manages legacy public widgets.
// Retain the chat root; stop/start only the replaced page subtrees.
export class WebsiteNavigator {
    constructor(assistant) {
        this.assistant = assistant;
        this.interactions = assistant.env.services["public.interactions"];
        this.host = document.querySelector(ASSISTANT);
        this.wrap = this.host?.parentElement;
        this.current = location.href;
        this.sequence = 0;
        this.onClick = event => this.click(event);
        this.onSubmit = event => this.submit(event);
        this.onPop = () => this.navigate(new URL(location.href), true);
        this.onScroll = () => {
            if (this.scrollFrame || this.loading) return;
            this.scrollFrame = requestAnimationFrame(() => { this.scrollFrame = null; this.savePosition(); });
        };
    }
    start() {
        if (!this.interactions || this.wrap?.id !== "wrapwrap" || window.top !== window.self) return;
        this.previousScroll = history.scrollRestoration;
        history.scrollRestoration = "manual";
        this.savePosition();
        document.addEventListener("click", this.onClick);
        document.addEventListener("submit", this.onSubmit);
        window.addEventListener("popstate", this.onPop);
        window.addEventListener("scroll", this.onScroll, { passive: true });
        this.started = true;
    }
    stop() {
        this.controller?.abort();
        document.removeEventListener("click", this.onClick);
        document.removeEventListener("submit", this.onSubmit);
        window.removeEventListener("popstate", this.onPop);
        window.removeEventListener("scroll", this.onScroll);
        cancelAnimationFrame(this.scrollFrame);
        if (this.started) history.scrollRestoration = this.previousScroll;
    }
    savePosition() {
        history.replaceState({ ...history.state, partnerHubPage: { x: scrollX, y: scrollY } }, "");
    }
    available() {
        return !this.committing && isPageUrl(new URL(this.current), this.assistant.state.signedIn) && !document.querySelector(
            '.o_website_edit_mode, .o_we_website_top_actions, .modal.show, [data-lt-payment-status], [data-lt-submitting="true"]');
    }
    click(event) {
        if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest?.("a[href]");
        if (!link || link.hasAttribute("download") || (link.target && link.target !== "_self") || link.hasAttribute("data-bs-toggle") || link.closest('[data-no-soft-navigation]')) return;
        let url;
        try { url = new URL(link.href, location.href); } catch { return; }
        if (url.origin !== location.origin || !isPageUrl(url, this.assistant.state.signedIn) || !this.available()) return;
        if (url.pathname === location.pathname && url.search === location.search) return;
        event.preventDefault();
        this.savePosition();
        this.navigate(url);
    }
    compatible(doc) {
        const host = doc.querySelector(ASSISTANT);
        const wrap = doc.querySelector("#wrapwrap");
        const inlineScripts = page => [...page.head.querySelectorAll(EXECUTABLE)]
            .filter(el => !el.src && !el.dataset.src && el.id !== "web.layout.odooscript" &&
                !/^\s*odoo\.__session_info__\s*=/.test(el.textContent))
            .map(el => el.textContent).join("\n");
        return host?.parentElement === wrap && wrap &&
            host.dataset.audience === this.host.dataset.audience &&
            doc.documentElement.lang === document.documentElement.lang &&
            sameAssets(document, doc) && inlineScripts(document) === inlineScripts(doc) && !wrap.querySelector(EXECUTABLE) &&
            !doc.querySelector('base, [data-lt-payment-status], .cf-turnstile, [data-sitekey]');
    }
    submit(event) {
        const form = event.target;
        if (event.defaultPrevented || form.tagName !== "FORM" || form.method.toLowerCase() !== "get" ||
            (form.target && form.target !== "_self") || !this.available()) return;
        const url = new URL(form.action, location.href);
        // Only catalog/knowledge search forms; never replay native transaction forms.
        if (url.origin !== location.origin || !/\/(products|resources|faq)\/?$/.test(url.pathname)) return;
        url.search = new URLSearchParams(new FormData(form, event.submitter)).toString();
        if (!isPageUrl(url, this.assistant.state.signedIn)) return;
        event.preventDefault();
        this.savePosition();
        this.navigate(url);
    }
    async navigate(url, pop = false) {
        const position = pop ? history.state?.partnerHubPage : null;
        if (!isPageUrl(url, this.assistant.state.signedIn) || !this.available()) { location.assign(url.href); return; }
        if (pop && url.pathname === new URL(this.current).pathname && url.search === new URL(this.current).search) {
            this.current = url.href;
            this.scroll(url, position);
            return;
        }
        const sequence = ++this.sequence;
        this.controller?.abort();
        const controller = this.controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);
        this.loading = true;
        document.documentElement.classList.add("lt-ai-navigating");
        try {
            const response = await fetch(url.href, { credentials: "same-origin", cache: "no-store", signal: controller.signal });
            if (sequence !== this.sequence) return;
            const final = new URL(response.url);
            if (!response.ok || !response.headers.get("content-type")?.includes("text/html") || final.origin !== location.origin || !isPageUrl(final, this.assistant.state.signedIn)) {
                location.assign(final.href); return;
            }
            const doc = new DOMParser().parseFromString(await response.text(), "text/html");
            if (sequence !== this.sequence) return;
            if (!this.compatible(doc)) { location.assign(final.href); return; }
            // Verify the session again before retaining private chat across pages.
            if (await this.assistant.bootstrap()) { location.assign(final.href); return; }
            if (sequence !== this.sequence) return;
            this.committing = true;
            const nextWrap = doc.querySelector("#wrapwrap");
            for (const child of [...this.wrap.children]) {
                if (child === this.host) continue;
                this.interactions.stopInteractions(child);
                child.remove();
            }
            for (const node of [...this.wrap.childNodes]) if (node.nodeType !== Node.ELEMENT_NODE) node.remove();
            nextWrap.querySelector(ASSISTANT).remove();
            const children = [...nextWrap.children];
            for (const child of children) this.wrap.insertBefore(document.adoptNode(child), this.host);
            this.wrap.className = nextWrap.className;
            document.body.className = doc.body.className;
            for (const name of Object.keys(document.documentElement.dataset)) delete document.documentElement.dataset[name];
            Object.assign(document.documentElement.dataset, doc.documentElement.dataset);
            // Legacy widgets read main-object through jQuery's data cache.
            window.jQuery?.(document.documentElement).removeData();
            document.title = doc.title;
            const metadata = 'meta[name="description"], meta[name="robots"], meta[property^="og:"], link[rel="canonical"]';
            document.head.querySelectorAll(metadata).forEach(el => el.remove());
            doc.head.querySelectorAll(metadata).forEach(el => document.head.append(document.adoptNode(el)));
            // Keep runtime classes; synchronize server-provided page data attributes.
            for (const name of Object.keys(document.body.dataset)) delete document.body.dataset[name];
            Object.assign(document.body.dataset, doc.body.dataset);
            if (!pop) history.pushState({ partnerHubPage: { x: 0, y: 0 } }, "", final.href + url.hash);
            else if (final.href !== url.href.split("#")[0]) history.replaceState(history.state, "", final.href + url.hash);
            this.current = location.href;
            // The optional staff editor toolbar is outside wrapwrap.
            document.querySelectorAll('a.o_frontend_to_backend_edit_btn[href]').forEach(link => {
                const editor = new URL(link.href, location.href);
                if (editor.origin === location.origin && editor.pathname.startsWith("/@/")) {
                    link.href = "/@" + location.pathname + location.search;
                }
            });
            for (const child of children) await this.interactions.startInteractions(child);
            initializePartnerHub();
            this.assistant.lastSync = 0;
            this.assistant.poll();
            this.scroll(new URL(location.href), position);
            if (!this.host.contains(document.activeElement)) {
                const heading = this.wrap.querySelector("h1");
                if (heading) { heading.tabIndex = -1; heading.focus({ preventScroll: true }); }
            }
            document.dispatchEvent(new CustomEvent("partner-hub:page-ready"));
        } catch (error) {
            if (sequence === this.sequence) location.assign(url.href);
        } finally {
            clearTimeout(timeout);
            if (sequence === this.sequence) {
                this.committing = false;
                this.loading = false;
                document.documentElement.classList.remove("lt-ai-navigating");
            }
        }
    }
    scroll(url, position) {
        requestAnimationFrame(() => {
            if (position) window.scrollTo(position.x, position.y);
            else {
                let target;
                try { target = url.hash && document.getElementById(decodeURIComponent(url.hash.slice(1))); } catch { /* Invalid anchor. */ }
                if (target) target.scrollIntoView(); else window.scrollTo(0, 0);
            }
        });
    }
}
