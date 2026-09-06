"use strict";
const CACHE = "lexi-dictionary-__DICTIONARY_REVISION__";
const SHELL = "/dictionary/";
const ASSETS = [SHELL, "/static/dictionary.css", "/static/dictionary.js", "/dictionary/manifest.webmanifest"];
self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) {
      if (/^lexi-dictionary-[a-f0-9]{16}$/.test(key) && key !== CACHE) await caches.delete(key);
    }
    await self.clients.claim();
  })());
});
self.addEventListener("message", (event) => {
  if (event.data !== "SAVE_OFFLINE" || !event.ports[0]) return;
  event.waitUntil((async () => {
    try {
      const cache = await caches.open(CACHE);
      await cache.addAll(ASSETS);
      event.ports[0].postMessage({ok:true});
    } catch (_) { event.ports[0].postMessage({ok:false}); }
  })());
});
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Never cache authentication, Mini App, admin, downloads, or external requests.
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !ASSETS.includes(url.pathname)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const key = url.pathname;
    const cached = await cache.match(key);
    // App shell/assets form one version. Refresh them only with a new worker.
    if (cached) return cached;
    return fetch(event.request);
  })());
});
