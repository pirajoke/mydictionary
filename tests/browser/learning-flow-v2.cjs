// Public controller behavior: status/resume, explicit review, completion undo.
const assert = require("node:assert/strict");
const {test} = require("node:test");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");
const source = fs.readFileSync(path.resolve(__dirname, "../../mydictionary/static/miniapp-swipe.js"), "utf8");
const flush = async () => {for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve));};
const bootstrap = {locale: "en", settings: {active_pack_id: "en-basics-100"}, features: {ai: false, voice: false, checkout: false}};
const sessionId = "90000000-0000-4000-8000-000000000001";
const operationId = "90000000-0000-4000-8000-000000000002";
const deck = {session_id: sessionId, pack_id: "en-basics-100", language: "en", tts_locale: "en-US", mode: "new", counts: {new: 2, forgotten: 0, total: 2}, queue: [4, 7], cards: [
  {word_index: 4, target: "first", meaning: "first meaning", transcription: "/first/", kind: "new"},
  {word_index: 7, target: "second", meaning: "second meaning", transcription: "/second/", kind: "new"},
]};
function fixture() {
  class Element {
    constructor(id = "") {
      this.id = id; this.textContent = ""; this.hidden = false; this.disabled = false;
      this.dataset = {}; this.attributes = {}; this.listeners = {}; this.children = []; this.style = {};
      const classes = new Set();
      this.classList = {add: (...v) => v.forEach(x => classes.add(x)), remove: (...v) => v.forEach(x => classes.delete(x)), contains: v => classes.has(v), toggle: (v, force) => {const add = force === undefined ? !classes.has(v) : force; add ? classes.add(v) : classes.delete(v); return add;}};
    }
    addEventListener(type, listener) {(this.listeners[type] ||= []).push(listener);}
    setAttribute(name, value) {this.attributes[name] = String(value);}
    getAttribute(name) {return this.attributes[name] ?? null;}
    removeAttribute(name) {delete this.attributes[name];}
    replaceChildren(...nodes) {this.children = nodes;}
    append(...nodes) {this.children.push(...nodes);}
    focus() {document.activeElement = this;}
    closest() {return null;}
    querySelectorAll() {return [];}
    setPointerCapture() {}
    releasePointerCapture() {}
    async click() {
      if (this.disabled) return;
      for (const listener of this.listeners.click || []) await listener({target: this, currentTarget: this, preventDefault() {}});
      await flush();
    }
  }
  const names = "trainer card target meaning transcription reveal speak again know undo status retry summary start count progress kind controls modes title hint language examples grammar pronunciation-status ipa-toggle resume pause".split(" ");
  const elements = Object.fromEntries(names.map(name => [`swipe-${name}`, new Element(`swipe-${name}`)]));
  const modes = ["mix", "forgotten", "new"].map(mode => {const node = new Element(); node.dataset.swipeMode = mode; return node;});
  const document = {documentElement: {lang: "en", dir: "ltr"}, getElementById: id => elements[id] || null,
    querySelectorAll: selector => selector.includes("data-swipe-mode") ? modes : [], createElement: () => new Element(), addEventListener() {}};
  const requests = [], responses = [];
  const fetch = async (url, options) => {
    requests.push({url, options, body: JSON.parse(options.body)});
    assert(responses.length, `Unexpected request ${url}`);
    const response = await responses.shift();
    if (response.httpStatus) return {ok: false, status: response.httpStatus, json: async () => response.body || {}};
    return {ok: true, status: 200, json: async () => response};
  };
  const window = {Telegram: {WebApp: {initData: "signed"}}, matchMedia: () => ({matches: true}), addEventListener() {}, crypto, fetch};
  const context = {window, document, fetch, crypto, console, setTimeout, clearTimeout, AbortController, Event, navigator: {onLine: true}, requestAnimationFrame: callback => callback()};
  vm.createContext(context); vm.runInContext(source, context);
  window.LexiSwipe.configure(bootstrap);
  return {api: window.LexiSwipe, elements, requests, responses};
}

test("AC1/3 configure is passive; refresh reads status; entry resumes the existing queue", async () => {
  const f = fixture();
  assert.equal(f.requests.length, 0);
  f.responses.push({counts: {new: 1, forgotten: 1, total: 2}, resume: {session_id: sessionId, mode: "new"}});
  await f.api.refresh();
  assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/status");
  assert.deepEqual(f.requests.at(-1).body, {});
  assert.equal(f.requests.at(-1).options.headers["X-Telegram-Init-Data"], "signed");
  f.responses.push({...deck, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: operationId});
  await f.api.enter(); await flush();
  assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/resume");
  assert.deepEqual(f.requests.at(-1).body, {session_id: sessionId});
  assert.equal(f.elements["swipe-target"].textContent, "second");
  assert.equal(f.elements["swipe-undo"].disabled, false);
  assert.equal(f.requests.length, 2, "resume does not start or grade a session");
});

test("AC1/EC1 auto entry prioritizes due review, otherwise new; explicit empty review remains empty", async () => {
  for (const [forgotten, requested, expected] of [[2, "auto", "forgotten"], [0, "auto", "new"], [0, "forgotten", "forgotten"]]) {
    const f = fixture();
    const counts = {new: 2, forgotten, total: forgotten + 2};
    f.responses.push({counts, resume: null}); await f.api.refresh();
    f.responses.push(requested === "forgotten" ? {...deck, mode: expected, session_id: null, cards: [], queue: [], counts} : {...deck, mode: expected, counts});
    await f.api.enter(requested); await flush();
    assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/deck");
    assert.deepEqual(f.requests.at(-1).body, {mode: expected});
    assert.equal(f.requests.length, 2, "empty review must never silently start new cards");
    if (requested === "forgotten") {
      assert(f.elements["swipe-status"].textContent.trim());
      assert(f.elements["swipe-know"].disabled);
    }
  }
});

test("AC5 last-answer undo remains actionable after completion and restores the card", async () => {
  const f = fixture();
  f.responses.push({counts: deck.counts, resume: {session_id: sessionId, mode: "new"}}); await f.api.refresh();
  f.responses.push({...deck, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: operationId}); await f.api.enter();
  f.responses.push({session_id: sessionId, queue: [], reviewed: 2, known: 2, again: 0, undo_operation_id: operationId}, {completed: true, reviewed: 2, known: 2, again: 0, earned_xp: 40});
  await f.elements["swipe-know"].click();
  assert.equal(f.elements["swipe-summary"].hidden, false);
  assert.equal(f.elements["swipe-undo"].disabled, false, "completed last rating can be corrected");
  f.responses.push({session_id: sessionId, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: null});
  await f.elements["swipe-undo"].click();
  assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/undo");
  assert.deepEqual(f.requests.at(-1).body, {session_id: sessionId, operation_id: operationId});
  assert.equal(f.elements["swipe-summary"].hidden, true);
  assert.equal(f.elements["swipe-target"].textContent, "second");
  assert.equal(f.elements["swipe-know"].disabled, false);
});

test("ERR2 delayed resume cannot install a previous language's cards", async () => {
  const f = fixture();
  f.responses.push({counts: deck.counts, resume: {session_id: sessionId, mode: "new"}}); await f.api.refresh();
  let resolve;
  f.responses.push(new Promise(done => {resolve = done;}));
  const pending = f.api.enter(); await flush();
  f.api.configure({...bootstrap, settings: {active_pack_id: "de-basics-100"}});
  resolve({...deck, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: operationId});
  await pending; await flush();
  assert.notEqual(f.elements["swipe-target"].textContent, "second");
  assert.equal(f.elements["swipe-know"].disabled, true);
});

test("AC6 opening IPA disclosure does not reveal the meaning", async () => {
  const f = fixture();
  f.responses.push({counts: deck.counts, resume: null}); await f.api.refresh();
  f.responses.push(deck); await f.api.enter();
  assert.equal(f.elements["swipe-meaning"].hidden, true);
  // The real template places a native <summary> inside the swipe card. Model
  // its closest() ancestry so the same pointer handlers run as a browser tap.
  const summary = {closest(selector) {
    return selector.split(",").some(item => ["summary", "details", "#swipe-ipa"].includes(item.trim())) ? summary : null;
  }};
  const card = f.elements["swipe-card"];
  const event = {target: summary, pointerId: 1, pointerType: "touch", isPrimary: true, button: 0, clientX: 120, clientY: 100};
  for (const listener of card.listeners.pointerdown || []) await listener(event);
  for (const listener of card.listeners.pointerup || []) await listener(event);
  await flush();
  assert.equal(f.elements["swipe-meaning"].hidden, true,
    "Opening pronunciation symbols must not trigger the card reveal gesture");
  assert.equal(f.requests.length, 2, "Pronunciation disclosure does not grade a card");
});

for (const status of [404, 409]) {
  test(`AC3/ERR2 resume ${status} invalidates cached status before the next explicit entry`, async () => {
    const f = fixture();
    f.responses.push({counts: deck.counts, resume: {session_id: sessionId, mode: "new"}});
    await f.api.refresh();
    f.responses.push({httpStatus: status, body: {error: status === 404 ? "session_not_found" : "session_expired"}});
    await f.api.enter(); await flush();
    assert.equal(f.requests.length, 2, "Failed resume must not automatically start a new lesson");
    assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/resume");
    assert.equal(f.elements["swipe-know"].disabled, true);
    assert(f.elements["swipe-status"].textContent.trim(), "The terminal failure has visible recovery copy");

    // Only the user's next entry authorizes another attempt. Refresh discovers
    // no pending session and then starts the ordinary available new-word deck.
    const freshSessionId = "90000000-0000-4000-8000-000000000003";
    f.responses.push({counts: deck.counts, resume: null}, {...deck, session_id: freshSessionId});
    let entryError;
    try { await f.api.enter(); } catch (error) { entryError = error; }
    await flush();
    assert.equal(f.requests[2].url, "/miniapp/api/swipe/status",
      "The next entry must revalidate status instead of retrying the rejected session");
    assert.ifError(entryError);
    assert.equal(f.requests.filter(request => request.url.endsWith("/resume")).length, 1);
    assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/deck");
    assert.deepEqual(f.requests.at(-1).body, {mode: "new"});
    assert.equal(f.elements["swipe-target"].textContent, "first");
  });
}

test("AC2 choose words pauses the visible card and preserves its resumable server queue", async () => {
  const f = fixture();
  f.responses.push({counts: deck.counts, resume: null}); await f.api.refresh();
  f.responses.push(deck); await f.api.enter();
  const rated = {session_id: sessionId, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: operationId};
  f.responses.push(rated); await f.elements["swipe-know"].click();
  assert.equal(f.elements["swipe-target"].textContent, "second");
  assert.equal(typeof f.api.choose, "function", "The native chooser must be available from profile and Telegram entry routes");

  const beforeChoose = f.requests.length;
  f.responses.push({counts: {new: 1, forgotten: 0, total: 1}, resume: {session_id: sessionId, mode: "new"}});
  await f.api.choose(); await flush();
  assert.deepEqual(f.requests.slice(beforeChoose).map(request => request.url), ["/miniapp/api/swipe/status"],
    "Choosing words refreshes status without starting, grading, or completing a lesson");
  assert.equal(f.elements["swipe-trainer"].dataset.active, "false");
  assert.equal(f.elements["swipe-controls"].hidden, true);
  assert.equal(f.elements["swipe-know"].disabled, true);
  assert.equal(f.elements["swipe-resume"].hidden, false);
  assert.equal(f.elements["swipe-resume"].disabled, false);

  f.responses.push({...deck, ...rated});
  await f.api.enter(); await flush();
  assert.equal(f.requests.at(-1).url, "/miniapp/api/swipe/resume");
  assert.deepEqual(f.requests.at(-1).body, {session_id: sessionId});
  assert.equal(f.elements["swipe-target"].textContent, "second", "Resume returns to the saved queue head");
  assert.equal(f.elements["swipe-undo"].disabled, false);
});

test("AC2 the Choose words action invokes the chooser even during an active lesson", () => {
  const mainSource = fs.readFileSync(path.resolve(__dirname, "../../mydictionary/static/miniapp.js"), "utf8");
  const start = mainSource.indexOf("  function openAction(action) {");
  const end = mainSource.indexOf("\n  function openDictionary", start);
  assert(start >= 0 && end > start, "The actual native action dispatcher must be present");
  const calls = [];
  const context = {
    payload: {}, node: id => id,
    activateTab: id => calls.push(["tab", id]),
    window: {LexiSwipe: {choose: () => calls.push(["choose"]), enter: mode => calls.push(["enter", mode])}},
  };
  vm.runInNewContext(mainSource.slice(start, end) + '\nopenAction("words");', context);
  assert.deepEqual(calls, [["tab", "tab-words"], ["choose"]],
    "Selecting the Words tab alone leaves chooser controls hidden behind an active card");
});
