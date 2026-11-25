/** 真正執行 app.js 的事件與 fetch；以小型 DOM 替身驗證載入競態與模式。 */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source = readFileSync(new URL('../../site/assets/app.js', import.meta.url), 'utf8');
const old = {date: '2026-11-24', generated_at: '2026-11-24T08:00:00+08:00', content: 'data/old.html', status: 'verified'};
const latest = {date: '2026-11-25', generated_at: '2026-11-25T08:00:00+08:00', content: 'data/latest.html', status: 'verified'};
const newer = {date: '2026-11-26', generated_at: '2026-11-26T08:00:00+08:00', content: 'data/newer.html', status: 'partial'};
const settle = async () => { for (let i = 0; i < 8; i++) await new Promise(resolve => setImmediate(resolve)); };

function setup({list = [latest, old], search = '', index = true} = {}) {
  class Element {
    constructor() { this.listeners = {}; this.textContent = ''; this.value = ''; this.children = []; this.disabled = false; this.hidden = false;
      this.classList = {toggle() {}}; }
    addEventListener(name, fn) { this.listeners[name] = fn; }
    replaceChildren(...nodes) { this.children = nodes; }
    append(...nodes) { this.children.push(...nodes); }
    async event(name) { await this.listeners[name]?.(); await settle(); }
  }
  const elements = Object.fromEntries(['site-status', 'report-picker', 'print-report', 'latest-report', 'report-content', 'delivery-status', 'toolbar'].map(name => [name, new Element()]));
  elements['report-content'].children = ['STALE INDEX SNAPSHOT'];
  const docEvents = {}, winEvents = {}, timers = [], requests = [];
  const location = {href: 'https://example.com/' + search};
  const document = {title: '', body: {dataset: {index: String(index)}}, visibilityState: 'visible',
    querySelector: selector => elements[selector.replace(/^[#.]/, '')] || null, querySelectorAll: () => [],
    createElement: () => new Element(), addEventListener: (name, fn) => { docEvents[name] = fn; }};
  let currentList = list, failManifest = false;
  const deferred = new Map();
  const context = vm.createContext({document, location, URL, Date, Intl, AbortSignal,
    history: {replaceState: (_a, _b, url) => { location.href = String(url); }},
    window: {print() {}, addEventListener: (name, fn) => { winEvents[name] = fn; }},
    Option: class { constructor(text, value) { this.text = text; this.value = value; } },
    DOMParser: class { parseFromString(text) { return {querySelectorAll: () => [], body: {childNodes: [text]}}; } },
    setInterval: fn => { timers.push(fn); },
    fetch: async (url, options) => {
      requests.push({url, options});
      if (url === 'data/reports.json') {
        if (failManifest) throw new Error('synthetic offline');
        return {ok: true, json: async () => currentList};
      }
      if (deferred.has(url)) return deferred.get(url);
      if (/^data\/(old|latest|newer)\.html$/.test(url)) return {ok: true, text: async () => url};
      return {ok: false, json: async () => null};
    }
  });
  vm.runInContext(source, context);
  return {elements, document, location, requests, deferred, setList: list => { currentList = list; },
    offline: () => { failManifest = true; }, tick: async () => { for (const fn of timers) await fn(); await settle(); },
    focus: async () => { await winEvents.focus?.(); await settle(); },
    visibility: async () => { await docEvents.visibilitychange?.(); await settle(); }};
}

test('stale index loads latest content, not just latest date label; sorting is explicit', async () => {
  const f = setup({list: [old, latest]}); await settle();
  assert.equal(f.elements['report-content'].children[0], latest.content);
  assert.equal(f.elements['report-picker'].value, latest.content);
  assert.match(f.elements['site-status'].textContent, /最新模式/);
  assert.ok(f.requests.some(r => r.url === 'data/reports.json' && r.options.cache === 'no-store'));
  assert.equal(new URL(f.location.href).searchParams.has('report'), false);
});

test('latest mode follows new publication and partial status across date changes', async () => {
  const f = setup(); await settle(); f.setList([newer, latest, old]); await f.tick();
  assert.equal(f.elements['report-content'].children[0], newer.content);
  assert.match(f.elements['site-status'].textContent, /部分資料未確認/);
});

test('history selection survives timers/focus; return-to-latest clears pinned URL', async () => {
  const f = setup(); await settle();
  f.elements['report-picker'].value = old.content; await f.elements['report-picker'].event('change');
  f.setList([newer, latest, old]); await f.tick(); await f.focus();
  assert.equal(f.elements['report-content'].children[0], old.content);
  assert.equal(new URL(f.location.href).searchParams.get('report'), old.content);
  await f.elements['latest-report'].event('click');
  assert.equal(f.elements['report-content'].children[0], newer.content);
  assert.equal(new URL(f.location.href).searchParams.has('report'), false);
});

test('explicit history link stays pinned on startup and background polling', async () => {
  const f = setup({search: '?report=data/old.html'}); await settle();
  assert.equal(f.elements['report-content'].children[0], old.content);
  f.setList([newer, latest, old]); await f.tick();
  assert.equal(f.elements['report-content'].children[0], old.content);
});

test('offline refresh retains readable snapshot and states failure', async () => {
  const f = setup(); await settle(); f.offline(); await f.tick();
  assert.equal(f.elements['report-content'].children[0], latest.content);
  assert.match(f.elements['site-status'].textContent, /保留目前內容/);
});

test('older slow request cannot overwrite a newer historical selection', async () => {
  const f = setup(); await settle();
  let resolve; f.deferred.set(old.content, new Promise(r => { resolve = r; }));
  f.elements['report-picker'].value = old.content;
  const pending = f.elements['report-picker'].listeners.change();
  f.elements['report-picker'].value = latest.content;
  await f.elements['report-picker'].event('change');
  resolve({ok: true, text: async () => 'late old response'}); await pending; await settle();
  assert.equal(f.elements['report-content'].children[0], latest.content);
});

test('hidden page does not poll; foreground refreshes latest; archive never polls', async () => {
  const f = setup(); await settle(); f.setList([newer, latest, old]); f.document.visibilityState = 'hidden'; await f.tick();
  assert.equal(f.elements['report-content'].children[0], latest.content);
  f.document.visibilityState = 'visible'; await f.visibility();
  assert.equal(f.elements['report-content'].children[0], newer.content);
  const archive = setup({index: false}); await settle(); await archive.tick();
  assert.equal(archive.requests.length, 0);
});
