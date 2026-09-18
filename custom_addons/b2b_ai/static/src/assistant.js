/** @odoo-module **/
import { Component, onMounted, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

const STORAGE = "partner-hub-ai-window-v2";
const FACTS = ["application", "location", "zones", "mounting", "environment", "network", "model", "requirements"];

export class FloatingAssistant extends Component {
    static template = "b2b_ai.FloatingAssistant";
    static props = {};
    setup() {
        this.state = useState({ loaded: false, enabled: true, signedIn: false, ready: false,
            open: false, expanded: false, busy: false, polling: false, panel: "chat",
            project: null, projects: [], draft: "", facts: {}, error: "", notice: "", confirmDelete: false });
        this.input = useRef("input"); this.history = useRef("history"); this.launcher = useRef("launcher");
        useEffect(() => {
            if (this.history.el) this.history.el.scrollTop = this.history.el.scrollHeight;
        }, () => [this.state.project?.id, this.state.project?.revision,
            this.state.project?.turns.map(t => t.state).join("|"), this.state.panel, this.state.open]);
        this.factKeys = FACTS;
        this.identity = null; this.pending = null; this.restoreId = null; this.lastSync = 0;
        this.focus = () => this.run(async () => { await this.bootstrap(); });
        this.logout = (event) => {
            if (event.target.closest?.('a[href^="/web/session/logout"]')) this.clearPrivateState();
        };
        onMounted(() => {
            window.addEventListener("focus", this.focus);
            document.addEventListener("click", this.logout, true);
            this.run(async () => { await this.bootstrap(true); if (this.state.open && this.state.signedIn) await this.restore(); });
            this.timer = setInterval(() => this.poll(), 4000);
        });
        onWillUnmount(() => {
            this.destroyed = true; clearInterval(this.timer);
            window.removeEventListener("focus", this.focus); document.removeEventListener("click", this.logout, true);
        });
    }
    get thinking() { return this.state.project?.turns.some(t => ["queued", "running"].includes(t.state)) || false; }
    get canSend() { return this.state.ready && !this.state.busy && !this.thinking && !!this.state.draft.trim() && !this.pending; }
    get loginUrl() {
        const next = location.pathname.startsWith("/web/") ? "/my" : location.pathname + location.search;
        return "/web/login?redirect=" + encodeURIComponent(next);
    }
    label(key) { return key.charAt(0).toUpperCase() + key.slice(1); }
    safeUrl(url) { return typeof url === "string" && url.startsWith("/") && !url.startsWith("//") ? url : "/contact"; }
    save() {
        try { sessionStorage.setItem(STORAGE, JSON.stringify({ identity: this.identity, at: Date.now(), open: this.state.open,
            expanded: this.state.expanded, id: this.state.project?.id || this.restoreId, draft: this.state.draft, pending: this.pending })); } catch { /* Storage may be disabled. */ }
    }
    clearPrivateState() {
        this.pending = null; this.restoreId = null;
        Object.assign(this.state, { project: null, projects: [], draft: "", facts: {}, panel: "chat", error: "", notice: "", confirmDelete: false });
        try { sessionStorage.removeItem(STORAGE); } catch { /* No persistent private history. */ }
    }
    async bootstrap(initial = false) {
        const response = await fetch("/ai-assistant/bootstrap", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error("We could not connect to the assistant. Please retry.");
        const data = await response.json();
        const changed = this.identity && this.identity !== data.identity;
        if (changed) this.clearPrivateState();
        this.identity = data.identity; this.csrf = data.csrf;
        Object.assign(this.state, { loaded: true, enabled: data.enabled, signedIn: data.signed_in, ready: data.ready });
        if (initial) {
            let saved;
            try { saved = JSON.parse(sessionStorage.getItem(STORAGE) || "null"); } catch { /* Ignore corrupt storage. */ }
            if (saved?.identity === this.identity && Date.now() - saved.at < 86400000) {
                Object.assign(this.state, { open: !!saved.open, expanded: !!saved.expanded, draft: typeof saved.draft === "string" ? saved.draft : "" });
                this.restoreId = saved.id; this.pending = saved.pending;
            } else this.clearPrivateState();
            if (new URL(location.href).searchParams.get("ai") === "open") this.state.open = true;
        }
        if (!this.state.signedIn) this.clearPrivateState();
        this.save(); return changed;
    }
    async run(work) {
        if (this.state.busy) return;
        this.state.busy = true; this.state.error = "";
        try { await work(); } catch (error) { this.state.error = error.message || "Please try again or contact our team."; }
        finally { this.state.busy = false; this.save(); }
    }
    async api(action, payload = {}) {
        const body = new FormData(); body.set("csrf_token", this.csrf); body.set("action", action); body.set("payload", JSON.stringify(payload));
        const response = await fetch("/ai-assistant/api", { method: "POST", body, credentials: "same-origin" });
        if (response.status === 401 || !response.headers.get("content-type")?.includes("application/json")) {
            this.clearPrivateState(); await this.bootstrap(); throw new Error("Your session may have expired. Please sign in again.");
        }
        const result = await response.json();
        if (!response.ok || !result.ok) {
            const error = new Error(result.message || "The assistant is unavailable. Please retry.");
            error.rejected = response.status === 400; throw error;
        }
        return result.data;
    }
    showProject(project, scroll = false) {
        const changed = this.state.project?.revision !== project.revision || this.state.project?.id !== project.id;
        this.state.project = project; this.restoreId = project.id;
        if (this.state.panel !== "facts") this.state.facts = { ...project.facts };
        if (scroll || changed) requestAnimationFrame(() => { if (this.history.el) this.history.el.scrollTop = this.history.el.scrollHeight; });
        this.save();
    }
    async restore() {
        this.state.projects = await this.api("list");
        if (this.restoreId && this.state.projects.some(p => p.id === this.restoreId)) {
            this.showProject(await this.api("get", { session_id: this.restoreId }), true);
            if (this.pending?.session_id === this.restoreId) await this.deliver();
        } else { this.state.project = null; this.restoreId = null; this.pending = null; }
    }
    toggle() {
        this.state.open = !this.state.open; this.save();
        if (!this.state.open) return;
        this.run(async () => { await this.bootstrap(); if (this.state.signedIn) await this.restore(); requestAnimationFrame(() => this.input.el?.focus()); });
    }
    close() { this.state.open = false; this.save(); this.launcher.el?.focus(); }
    expand() { this.state.expanded = !this.state.expanded; this.save(); }
    keydown(event) { if (event.key === "Escape" && this.state.open) { event.stopPropagation(); this.close(); } }
    inputChanged(event) { this.state.draft = event.target.value; this.save(); }
    example(text) { this.state.draft = text; this.save(); requestAnimationFrame(() => this.input.el?.focus()); }
    newConversation() {
        this.run(async () => {
            if (this.pending) throw new Error("Retry the unconfirmed message before starting another conversation.");
            this.showProject(await this.api("new")); this.state.draft = ""; this.state.panel = "chat"; this.state.notice = "";
        });
    }
    select(id) {
        this.run(async () => {
            if (this.pending) throw new Error("Retry the unconfirmed message first.");
            this.showProject(await this.api("get", { session_id: id }), true); this.state.panel = "chat"; this.state.draft = ""; this.state.notice = "";
        });
    }
    showHistory() { this.run(async () => { this.state.projects = await this.api("list"); this.state.panel = "history"; }); }
    showFacts() { this.state.facts = { ...this.state.project.facts }; this.state.panel = "facts"; this.state.confirmDelete = false; }
    back() { this.state.panel = "chat"; }
    saveFacts(event) {
        event.preventDefault(); this.run(async () => {
            this.showProject(await this.api("facts", { session_id: this.state.project.id, revision: this.state.project.revision, facts: this.state.facts }));
            this.state.panel = "chat"; this.state.notice = "Project requirements saved.";
        });
    }
    archive() {
        if (!this.state.confirmDelete) { this.state.confirmDelete = true; return; }
        this.run(async () => { await this.api("delete", { session_id: this.state.project.id }); this.clearPrivateState(); this.state.notice = "Conversation archived."; });
    }
    async deliver() {
        if (!this.pending) return;
        const pending = this.pending;
        try {
            const project = await this.api("ask", pending); this.pending = null;
            if (this.state.draft.trim() === pending.text) this.state.draft = "";
            this.showProject(project, true); this.state.notice = "";
        } catch (error) {
            if (error.rejected) this.pending = null;
            else this.state.notice = "Delivery is not confirmed. Retrying uses the same message ID.";
            throw error;
        } finally { this.save(); }
    }
    retry() { this.run(async () => { await this.bootstrap(); if (this.pending) await this.deliver(); else if (this.state.signedIn) await this.restore(); }); }
    send(event) {
        event.preventDefault(); if (!this.canSend) return;
        this.run(async () => {
            if (!this.state.project) this.showProject(await this.api("new"));
            this.pending = { session_id: this.state.project.id, text: this.state.draft.trim(), key: crypto.randomUUID(), revision: this.state.project.revision };
            this.save(); await this.deliver();
        });
    }
    async poll() {
        if (!this.state.open || this.state.busy || this.state.polling || document.hidden || this.destroyed) return;
        if (Date.now() - this.lastSync < (this.thinking ? 4000 : 30000)) return;
        this.lastSync = Date.now();
        this.state.polling = true;
        try {
            if (await this.bootstrap() || !this.state.signedIn) return;
            if (this.state.project && this.state.panel === "chat") {
                const id = this.state.project.id;
                const project = await this.api("get", { session_id: id });
                // A slow poll must not restore an older conversation/revision
                // over a new chat or an explicitly saved requirement.
                if (!this.state.busy && this.state.project?.id === id && project.revision >= this.state.project.revision) this.showProject(project);
            }
        } catch (error) { this.state.error = error.message || "Connection interrupted. Please retry."; }
        finally { this.state.polling = false; }
    }
}
registry.category("public_components").add("b2b_ai.FloatingAssistant", FloatingAssistant);
