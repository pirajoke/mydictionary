// Deterministic public UI contract. No browser dependency, no test-only module API.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");

const modulePath = path.resolve(__dirname, "../../mydictionary/static/miniapp-swipe.js");
assert(fs.existsSync(modulePath), "AC6: a real request-driven swipe controller is required");
const source = fs.readFileSync(modulePath, "utf8");
assert(!/\.(?:innerHTML|outerHTML)\s*=|insertAdjacentHTML|localStorage/.test(source), "AC7: no learner-content HTML or durable browser storage");

class Element {
  constructor(id = "") {
    this.id = id; this.textContent = ""; this.hidden = false; this.disabled = false;
    this.dataset = {}; this.attributes = {}; this.listeners = {}; this.children = [];
    this.tagName = ["swipe-reveal", "swipe-speak", "swipe-again", "swipe-know", "swipe-undo", "swipe-retry", "swipe-start"].includes(id) ? "BUTTON" : "DIV";
    this.style = {}; this.tabIndex = 0;
    const classes = new Set();
    this.classList = {add: (...v) => v.forEach(x => classes.add(x)), remove: (...v) => v.forEach(x => classes.delete(x)), contains: v => classes.has(v), toggle: (v, force) => {const add = force === undefined ? !classes.has(v) : force; add ? classes.add(v) : classes.delete(v); return add;}};
  }
  addEventListener(name, listener) { (this.listeners[name] ||= []).push(listener); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  removeAttribute(name) { delete this.attributes[name]; }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  replaceChildren(...nodes) { this.children = nodes; }
  focus() { document.activeElement = this; }
  querySelectorAll() { return []; }
  closest(selector) {
    if (selector.includes("button") && (this.tagName === "BUTTON" || this.dataset.swipeMode)) return this;
    return selector.includes("data-swipe-mode") && this.dataset.swipeMode ? this : null;
  }
  getBoundingClientRect() { return {width: 320, height: 350, left: 0, top: 0}; }
  setPointerCapture() {}
  releasePointerCapture() {}
  dispatch(name, values = {}) {
    const event = {type: name, target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}, ...values};
    return Promise.all((this.listeners[name] || []).map(listener => listener(event)));
  }
}
const ids = ["swipe-trainer", "swipe-card", "swipe-target", "swipe-meaning", "swipe-transcription", "swipe-reveal", "swipe-speak", "swipe-again", "swipe-know", "swipe-undo", "swipe-status", "swipe-retry", "swipe-summary", "swipe-start", "swipe-count", "swipe-progress", "swipe-kind", "swipe-controls", "swipe-modes", "swipe-title", "swipe-hint"];
const elements = Object.fromEntries(ids.map(id => [id, new Element(id)]));
const modes = ["mix", "forgotten", "new"].map(mode => {const node = new Element(); node.dataset.swipeMode = mode; return node;});
const document = {
  readyState: "complete", activeElement: null,
  documentElement: {lang: "en", dir: "ltr"},
  getElementById: id => elements[id] || null,
  querySelector: selector => selector.startsWith("#") ? elements[selector.slice(1)] : null,
  querySelectorAll: selector => selector.includes("data-swipe-mode") ? modes : [],
  createElement: () => new Element(),
  addEventListener: () => {},
};
const requests = [];
let nextResponse, failNext = false;
const queuedResponses = [];
const speech = [];
const window = {
  AbortController, Event,
  Telegram: {WebApp: {initData: "signed", HapticFeedback: {impactOccurred() {}, notificationOccurred() {}}}},
  speechSynthesis: {cancel() {}, getVoices: () => [], speak: utterance => speech.push(utterance)},
  matchMedia: () => ({matches: true, addEventListener() {}}),
  addEventListener() {}, crypto,
};
async function fetch(url, options = {}) {
  requests.push({url, options, body: options.body ? JSON.parse(options.body) : null});
  if (failNext) {failNext = false; throw new Error("offline");}
  const result = nextResponse || queuedResponses.shift(); nextResponse = null;
  assert(result, `Unexpected request ${url}`);
  return {ok: true, status: 200, json: async () => result};
}
const context = {window, document, fetch, navigator: {onLine: true}, crypto, console, setTimeout, clearTimeout, AbortController, Event,
  requestAnimationFrame: callback => callback(),
  SpeechSynthesisUtterance: class {constructor(text) {this.text = text;}},
};
window.fetch = fetch;
vm.createContext(context);
vm.runInContext(source, context, {filename: modulePath});
assert.equal(typeof window.LexiSwipe?.configure, "function", "AC6: bootstrap must configure the public controller");
const flush = async () => {for (let i = 0; i < 5; i++) await new Promise(resolve => setImmediate(resolve));};
const click = async id => {assert(elements[id].listeners.click?.length, `${id} must be wired`); await elements[id].dispatch("click"); await flush();};
const sessionId = "90000000-0000-4000-8000-000000000001";
const realTarget = "<img src=x onerror=alert(1)>";
const deck = {session_id: sessionId, pack_id: "en-basics-100", language: "en", tts_locale: "en-US", mode: "mix", counts: {new: 2, forgotten: 0, total: 2}, queue: [4, 7], cards: [
  {word_index: 4, target: realTarget, meaning: "Curated first meaning", transcription: "/ˈwɜːd/", kind: "new"},
  {word_index: 7, target: "second real word", meaning: "Curated second meaning", transcription: "/ˈsekənd/", kind: "new"},
]};
const bootstrap = {locale: "en", copy: {}, features: {ai: false, voice: false, checkout: false}, settings: {active_pack_id: "en-basics-100"}, progress: {xp: 0}};

(async () => {
  window.LexiSwipe.configure(bootstrap);
  await flush();
  // Configure does not itself write learner progress or require disabled paid features.
  assert.equal(requests.length, 0);
  nextResponse = deck;
  await click("swipe-start");
  assert.equal(requests.at(-1).url, "/miniapp/api/swipe/deck");
  assert.deepEqual(requests.at(-1).body, {mode: "mix"});
  assert.equal(requests.at(-1).options.headers["X-Telegram-Init-Data"], "signed");
  assert.equal(elements["swipe-target"].textContent, realTarget, "AC6/7: render returned real target with textContent");
  assert(elements["swipe-meaning"].hidden || elements["swipe-card"].getAttribute("aria-expanded") === "false", "AC6: meaning is unrevealed initially");
  await click("swipe-reveal");
  assert.equal(elements["swipe-meaning"].textContent, "Curated first meaning");
  assert(!elements["swipe-meaning"].hidden, "AC6: reveal exposes actual meaning");
  await click("swipe-speak");
  assert.equal(speech.at(-1).text, realTarget);
  assert.equal(speech.at(-1).lang, "en-US");

  // Offline grade does not advance. Retry must reuse the operation identifier.
  failNext = true;
  await click("swipe-know");
  const failed = requests.at(-1);
  assert.equal(failed.url, "/miniapp/api/swipe/rate");
  assert.equal(failed.body.word_index, 4);
  assert.equal(failed.body.knew, true);
  assert.match(failed.body.operation_id, /^[0-9a-f-]{36}$/i);
  assert.equal(elements["swipe-target"].textContent, realTarget, "AC7: no optimistic advance on failure");
  assert(elements["swipe-status"].textContent.trim(), "AC7: error is visible");
  assert(!elements["swipe-retry"].hidden, "AC7: retry is actionable");
  nextResponse = {session_id: sessionId, queue: [7], reviewed: 1, known: 1, again: 0, undo_operation_id: failed.body.operation_id};
  await click("swipe-retry");
  assert.deepEqual(requests.at(-1).body, failed.body, "AC7: retry uses the same exact operation");
  assert.equal(elements["swipe-target"].textContent, "second real word");
  nextResponse = {session_id: sessionId, queue: [4, 7], reviewed: 0, known: 0, again: 0, undo_operation_id: null};
  await click("swipe-undo");
  assert.equal(requests.at(-1).url, "/miniapp/api/swipe/undo");
  assert.deepEqual(requests.at(-1).body, {session_id: sessionId, operation_id: failed.body.operation_id});
  assert.equal(elements["swipe-target"].textContent, realTarget);

  // AC6: native pointer gestures persist equivalent left-again/right-know ratings.
  const card = elements["swipe-card"];
  assert(card.listeners.pointerdown?.length && card.listeners.pointerup?.length, "AC6: pointer swipes must be wired");
  async function drag(fromX, toX, target = card) {
    const pointer = {pointerId: 1, pointerType: "touch", isPrimary: true, button: 0, clientY: 100, target};
    await card.dispatch("pointerdown", {...pointer, clientX: fromX});
    await card.dispatch("pointermove", {...pointer, clientX: toX});
    await card.dispatch("pointerup", {...pointer, clientX: toX});
    await flush();
  }
  const beforeControlDrag = requests.length;
  await drag(220, 70, elements["swipe-reveal"]);
  assert.equal(requests.length, beforeControlDrag, "AC6: button controls are not a drag area");
  for (const knew of [false, true]) {
    const gestureOperation = crypto.randomUUID();
    nextResponse = {session_id: sessionId, queue: knew ? [7] : [7, 4], reviewed: 1, known: knew ? 1 : 0, again: knew ? 0 : 1, undo_operation_id: gestureOperation};
    const beforeGesture = requests.length;
    await drag(160, knew ? 300 : 20);
    assert.equal(requests.length, beforeGesture + 1, "AC6: each gesture persists exactly one assessment");
    assert.equal(requests.at(-1).url, "/miniapp/api/swipe/rate");
    assert.equal(requests.at(-1).body.word_index, 4);
    assert.equal(requests.at(-1).body.knew, knew, knew ? "AC6: right gesture knows" : "AC6: left gesture repeats");
    nextResponse = {session_id: sessionId, queue: [4, 7], reviewed: 0, known: 0, again: 0, undo_operation_id: null};
    await click("swipe-undo");
    assert.deepEqual(requests.at(-1).body, {session_id: sessionId, operation_id: gestureOperation});
  }

  // Equivalent buttons and keyboard send persisted left-again/right-know assessments.
  nextResponse = {session_id: sessionId, queue: [7, 4], reviewed: 1, known: 0, again: 1, undo_operation_id: crypto.randomUUID()};
  await click("swipe-again");
  assert.equal(requests.at(-1).body.knew, false);
  assert(elements["swipe-card"].listeners.keydown?.length, "AC7: keyboard controls must be wired");
  nextResponse = {session_id: sessionId, queue: [4], reviewed: 2, known: 1, again: 1, undo_operation_id: crypto.randomUUID()};
  await elements["swipe-card"].dispatch("keydown", {key: "ArrowRight"}); await flush();
  assert.equal(requests.at(-1).body.knew, true);
  assert.equal(requests.at(-1).body.word_index, 7);

  nextResponse = {session_id: sessionId, queue: [], reviewed: 3, known: 2, again: 1, undo_operation_id: crypto.randomUUID()};
  queuedResponses.push({completed: true, reviewed: 3, known: 2, again: 1, earned_xp: 47});
  await click("swipe-know");
  assert.equal(requests.at(-1).url, "/miniapp/api/swipe/complete", "AC6: empty authoritative queue completes real session");
  assert.deepEqual(requests.at(-1).body, {session_id: sessionId});
  assert(!elements["swipe-summary"].hidden, "AC6: completion summary is visible");
  assert.match(elements["swipe-summary"].textContent, /47/, "AC6: summary renders earned server XP");

  // Localization is verified by rendered actionable text, not an unused map.
  const labels = new Set();
  for (const locale of ["en", "fr", "de", "ja", "ar", "zh", "ru", "es"]) {
    window.LexiSwipe.configure({...bootstrap, locale}); await flush();
    for (const id of ["swipe-start", "swipe-reveal", "swipe-again", "swipe-know", "swipe-undo", "swipe-retry"]) {
      assert(elements[id].textContent.trim(), `AC7: ${locale} ${id} localized text`);
    }
    labels.add(elements["swipe-know"].textContent);
  }
  assert(labels.size >= 7, "AC7: supported locales must not silently fall back to English");
  nextResponse = {...deck, session_id: null, cards: [], queue: [], counts: {new: 0, forgotten: 0, total: 0}};
  await click("swipe-start");
  assert(elements["swipe-status"].textContent.trim(), "AC7/EC1: empty deck has visible explanation");
  assert(elements["swipe-card"].hidden || elements["swipe-know"].disabled, "AC7/EC1: empty deck cannot be graded");
  // Auth-disabled and empty states cannot offer writable assessments.
  window.Telegram.WebApp.initData = "";
  window.LexiSwipe.configure(bootstrap); await flush();
  const beforeAuthClick = requests.length;
  await click("swipe-start");
  assert.equal(requests.length, beforeAuthClick, "AC7: absent signed identity fails closed");
  assert(elements["swipe-status"].textContent.trim());
  console.log("PASS AC6/AC7 real cards/reveal/speech/grade/retry/undo/pointer/keyboard/eight locales/auth");
})().catch(error => {console.error(error); process.exitCode = 1;});
