// Pure interaction unit tests with stub elements; no browser or live user session.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const source = readFileSync(fileURLToPath(new URL('../custom_addons/b2b_website/static/src/js/partner_hub.js', import.meta.url)), 'utf8');
const functions = source.slice(source.indexOf('function observeCarouselSize('), source.indexOf('function initializeRegistrationContacts('));
class Element {
    constructor(dataset = {}) { this.dataset = dataset; this.events = {}; this.attributes = {}; this.isConnected = true; this.hidden = false; this.classList = {toggle() {}}; }
    addEventListener(name, fn) { (this.events[name] ||= []).push(fn); }
    removeEventListener(name, fn) { this.events[name] = (this.events[name] || []).filter(item => item !== fn); }
    fire(name, event = {}) { (this.events[name] || []).slice().forEach(fn => fn(event)); }
    click() { this.fire('click'); }
    focus() { this.focused = true; }
    setAttribute(name, value) { this.attributes[name] = value; }
    closest() { return null; }
}
const document = new Element();
const tabs = ['recommended', 'special', 'best_seller'].map(name => new Element({pgFeaturedTab: name}));
const tracks = tabs.map(() => Object.assign(new Element(), {
    scrollLeft: 0, clientWidth: 600, scrollWidth: 1800,
    children: Array.from({length: 6}, (_, i) => ({offsetLeft: i * 300})),
    scrollBy(options) { this.scrollLeft += options.left; this.fire('scroll'); },
}));
const panels = tabs.map((tab, index) => Object.assign(new Element({pgFeaturedPanel: tab.dataset.pgFeaturedTab}), {
    hidden: index !== 0, querySelector: () => tracks[index],
}));
const arrows = ['left', 'right'].map(direction => new Element({pgScroll: direction}));
const arrowGroup = new Element();
const pagination = new Element();
const progress = Object.assign(new Element(), {style: {}});
const counter = new Element();
const featured = Object.assign(new Element(), {
    querySelector(selector) { return {'[data-pg-featured-arrows]': arrowGroup, '[data-pg-featured-pagination]': pagination, '[data-pg-featured-progress]': progress, '[data-pg-featured-counter]': counter}[selector] || null; },
    querySelectorAll(selector) { return selector === '[data-pg-featured-tab]' ? tabs : selector === '[data-pg-featured-panel]' ? panels : arrows; },
});
const carouselArrows = ['left', 'right'].map(direction => new Element({pgCarouselScroll: direction}));
const carouselTrack = Object.assign(new Element(), {
    scrollLeft: 0, clientWidth: 1000, scrollWidth: 2000,
    scrollBy(options) { this.scrollLeft += options.left; this.fire('scroll'); },
});
const carousel = Object.assign(new Element(), {querySelector: () => carouselTrack, querySelectorAll: () => carouselArrows});
document.querySelectorAll = selector => selector === '[data-pg-featured]' ? [featured] : [carousel];
const observers = [];
class ResizeObserver {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe() {}
    disconnect() { this.disconnected = true; }
}
const context = vm.createContext({document, ResizeObserver, Math});
vm.runInContext(functions + '\ninitializeFeaturedProducts(); initializeHorizontalCarousels();', context);
assert.equal(arrows[0].disabled, true);
assert.equal(pagination.hidden, false);
assert.equal(counter.textContent, '1\u00a0\u2013\u00a02 / 6');
assert.ok(Math.abs(Number.parseFloat(progress.style.width) - 100 / 3) < 1e-8);
arrows[1].click();
assert.equal(tracks[0].scrollLeft, 480);
assert.equal(arrows[0].disabled, false);
assert.equal(counter.textContent, '3\u00a0\u2013\u00a04 / 6');
tabs[1].click();
assert.deepEqual(panels.map(panel => panel.hidden), [true, false, true]);
assert.deepEqual(tabs.map(tab => tab.tabIndex), [-1, 0, -1]);
assert.equal(arrows[0].disabled, true);
arrows[1].click();
assert.equal(tracks[1].scrollLeft, 480);
assert.equal(tracks[0].scrollLeft, 480);
let prevented = false;
tabs[1].fire('keydown', {key: 'End', preventDefault() { prevented = true; }});
assert.equal(prevented, true);
assert.equal(tabs[2].focused, true);
assert.deepEqual(panels.map(panel => panel.hidden), [true, true, false]);
tabs[2].fire('keydown', {key: 'ArrowRight', preventDefault() {}});
assert.equal(tabs[0].focused, true);
tracks[0].scrollLeft = tracks[0].scrollWidth - tracks[0].clientWidth;
tracks[0].fire('scroll');
assert.equal(counter.textContent, '5\u00a0\u2013\u00a06 / 6');
tracks[0].scrollWidth = tracks[0].clientWidth;
tracks[0].fire('scroll');
assert.equal(pagination.hidden, true);
assert.equal(arrowGroup.hidden, true);
assert.equal(carouselArrows[0].disabled, true);
carouselArrows[1].click();
assert.equal(carouselTrack.scrollLeft, 750);
assert.equal(carouselArrows[0].disabled, false);
carouselTrack.scrollLeft = 1000;
carouselTrack.fire('scroll');
assert.equal(carouselArrows[1].disabled, true);
featured.isConnected = carousel.isConnected = false;
document.fire('partner-hub:page-ready');
assert.ok(observers.every(observer => observer.disconnected));
assert.equal(document.events['partner-hub:page-ready'].length, 0);
console.log('Homepage interaction units passed: tabs, keyboard, active-track arrows, boundaries, soft-navigation cleanup.');
