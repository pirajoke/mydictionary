// Standalone fixture: no running app, production mutation, or network dependency.
// Requires the project .venv Python and Playwright on Node's module search path.
const assert = require("node:assert/strict");
const {execFileSync} = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const http = require("node:http");
const path = require("node:path");
const {chromium} = require("playwright");

const root = path.resolve(__dirname, "../..");
const ownCache = /^lexi-dictionary-[a-f0-9]{16}$/;
const allowedPaths = ["/dictionary/", "/static/dictionary.css", "/static/dictionary.js", "/dictionary/manifest.webmanifest"];

async function main() {
  // Render the actual template and public projection without initializing a DB.
  const python = process.env.DICTIONARY_TEST_PYTHON || path.join(root, ".venv/bin/python");
  const rendered = JSON.parse(execFileSync(python, ["-c", `
import json
from jinja2 import Environment, FileSystemLoader, select_autoescape
from mydictionary.catalog import load_catalog
from mydictionary.dictionary import build_dictionary_data, dictionary_content_security_policy, dictionary_manifest
env = Environment(loader=FileSystemLoader("mydictionary/templates"), autoescape=select_autoescape())
html = env.get_template("dictionary.html").render(
    dictionary_data=build_dictionary_data(load_catalog()), dictionary_css=None,
    dictionary_js=None, dictionary_defaults=None, offline_download=False,
    dictionary_csp=dictionary_content_security_policy().replace("frame-ancestors 'none'; ", ""))
print(json.dumps({"html": html, "manifest": dictionary_manifest()}))
`], {cwd:root, encoding:"utf8", maxBuffer:2 * 1024 * 1024}));
  const [javascript, css, worker] = await Promise.all(
    ["dictionary.js", "dictionary.css", "dictionary-sw.js"].map(name =>
      fs.readFile(path.join(root, "mydictionary/static", name), "utf8"))
  );
  assert(worker.includes("__DICTIONARY_REVISION__"), "Fixture must use the real revisioned worker");

  function fixture(marker) {
    // Only in-memory fixture content changes. The same real app and worker run
    // for both versions; independent markers prove each cached asset upgraded.
    const html = rendered.html
      .replace("<body ", `<body data-fixture-shell="${marker}" `)
      .replace(/(<script id="dictionary-data" type="application\/json">)([\s\S]*?)(<\/script>)/,
        (_, start, body, end) => {
          const data = JSON.parse(body);
          const english = data.packs.find(pack => pack.target_language === "en");
          english.entries.find(entry => entry.entry_id === "hello").target = `hello-fixture-${marker}`;
          // All injected fixture values are constant alphanumeric strings.
          return start + JSON.stringify(data).replaceAll("<", "\\u003c") + end;
        });
    const js = javascript + `\ndocument.body.dataset.fixtureAsset = "${marker}";\n`;
    const style = css + `\n:root { --fixture-revision: ${marker}; }\n`;
    const manifest = JSON.stringify(rendered.manifest);
    const revision = crypto.createHash("sha256")
      .update(JSON.stringify({html, js, style, manifest, worker})).digest("hex").slice(0, 16);
    return {html, js, style, manifest, revision};
  }

  const version1 = fixture("v1");
  const version2 = fixture("v2");
  let current = version1;
  const requests = [];
  const server = http.createServer((request, response) => {
    const pathname = new URL(request.url, "http://fixture.invalid").pathname;
    requests.push({pathname, revision:current.revision});
    const routes = {
      "/dictionary/": ["text/html; charset=utf-8", current.html],
      "/static/dictionary.js": ["application/javascript", current.js],
      "/static/dictionary.css": ["text/css", current.style],
      "/dictionary/manifest.webmanifest": ["application/manifest+json", current.manifest],
      "/dictionary/sw.js": ["application/javascript", worker.replaceAll("__DICTIONARY_REVISION__", current.revision)],
      "/admin/login": ["text/plain", "fixture-admin-not-for-cache"],
    };
    response.setHeader("Cache-Control", "no-store");
    if (pathname === "/dictionary/sw.js") response.setHeader("Service-Worker-Allowed", "/dictionary/");
    const route = routes[pathname];
    response.statusCode = route ? 200 : 404;
    response.setHeader("Content-Type", route ? route[0] : "text/plain");
    response.end(route ? route[1] : "not found");
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const base = `http://127.0.0.1:${server.address().port}`;
  let browser;
  try {
    browser = await chromium.launch({headless:true});
    const context = await browser.newContext({locale:"en-US"});
    const errors = [];
    const external = [];
    context.on("page", page => {
      page.on("pageerror", error => errors.push(error.message));
      page.on("request", request => {
        if (new URL(request.url()).origin !== base) external.push(request.url());
      });
    });
    const page = await context.newPage();
    await page.goto(`${base}/dictionary/?target=en&native=ru&ui=en`);
    await page.locator(".word-row").first().waitFor();
    await page.locator("#save-offline").click();
    await page.waitForFunction(() => document.getElementById("offline-status").textContent.includes("Dictionary saved"));

    const oldCache = `lexi-dictionary-${version1.revision}`;
    const newCache = `lexi-dictionary-${version2.revision}`;
    assert.deepEqual((await page.evaluate(() => caches.keys())).filter(key => ownCache.test(key)), [oldCache]);
    assert.equal(await page.locator("body").getAttribute("data-fixture-shell"), "v1");
    assert.equal(await page.locator("body").getAttribute("data-fixture-asset"), "v1");
    await page.evaluate(async () => {
      const cache = await caches.open("unrelated-app-cache");
      await cache.put("/fixture-unrelated", new Response("preserve unrelated application"));
      await fetch("/admin/login");
    });

    // A real browser update must activate v2 even while a v1 tab is open.
    current = version2;
    assert.match(await page.evaluate(() => fetch("/static/dictionary.js").then(response => response.text())), /fixtureAsset = "v1"/);
    await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration("/dictionary/");
      if (!registration) throw new Error("Missing installed worker");
      let timer;
      let onControllerChange;
      const controlledByUpdate = new Promise((resolve, reject) => {
        onControllerChange = resolve;
        navigator.serviceWorker.addEventListener("controllerchange", onControllerChange, {once:true});
        timer = setTimeout(() => reject(new Error("Updated worker did not take control")), 12000);
      });
      try {
        await registration.update();
        await controlledByUpdate;
      } finally {
        clearTimeout(timer);
        navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
      }
    });
    await page.waitForFunction(async ({oldCache, newCache}) => {
      const keys = await caches.keys();
      const registration = await navigator.serviceWorker.getRegistration("/dictionary/");
      return keys.includes(newCache) && !keys.includes(oldCache) && registration?.active?.state === "activated";
    }, {oldCache, newCache});
    await page.reload();
    await page.waitForFunction(() => document.body.dataset.fixtureAsset === "v2");
    const shell = await page.locator("body").getAttribute("data-fixture-shell");
    if (shell !== "v2") {
      const cacheBodies = await page.evaluate(async () => {
        const values = [];
        for (const key of await caches.keys()) {
          const cache = await caches.open(key);
          const response = await cache.match("/dictionary/");
          values.push({key, marker:response ? (await response.text()).match(/data-fixture-shell="(.*?)"/)?.[1] : null});
        }
        return values;
      });
      assert.equal(shell, "v2", JSON.stringify({requests, cacheBodies, expectedHtmlMarker:version2.html.includes('data-fixture-shell="v2"')}));
    }
    assert.equal(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--fixture-revision").trim()), "v2");
    await page.locator("#dictionary-query").fill("hello-fixture-v2");
    assert.match(await page.locator("#dictionary-results").innerText(), /hello-fixture-v2/);

    const cacheReceipt = await page.evaluate(async () => {
      const keys = await caches.keys();
      const owned = keys.filter(key => /^lexi-dictionary-[a-f0-9]{16}$/.test(key));
      const paths = [];
      for (const key of owned) {
        const cache = await caches.open(key);
        paths.push(...(await cache.keys()).map(request => new URL(request.url).pathname));
      }
      const unrelated = await caches.open("unrelated-app-cache");
      return {owned, paths, unrelated:await (await unrelated.match("/fixture-unrelated")).text()};
    });
    assert.deepEqual(cacheReceipt.owned, [newCache]);
    assert.deepEqual(cacheReceipt.paths.sort(), [...allowedPaths].sort());
    assert.equal(cacheReceipt.unrelated, "preserve unrelated application");

    await context.setOffline(true);
    await page.close();
    const offline = await context.newPage();
    await offline.goto(`${base}/dictionary/?target=en&native=ru&ui=en`);
    await offline.waitForFunction(() => document.body.dataset.fixtureAsset === "v2");
    assert.equal(await offline.locator("body").getAttribute("data-fixture-shell"), "v2");
    assert.equal(await offline.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--fixture-revision").trim()), "v2");
    await offline.locator("#dictionary-query").fill("hello-fixture-v2");
    assert.match(await offline.locator("#dictionary-results").innerText(), /привет/);
    assert.equal(await offline.evaluate(() => fetch("/admin/login").then(() => true).catch(() => false)), false,
      "Admin requests must not be served from dictionary cache");
    assert.deepEqual(errors, []);
    assert.deepEqual(external, []);
    console.log(JSON.stringify({ok:true, oldRevision:version1.revision, newRevision:version2.revision,
      checks:["real worker v1 install", "v2 upgrade with old tab open", "new shell/JS/CSS/content",
        "old own cache removed", "unrelated cache preserved", "cold v2 offline lookup", "admin excluded"],
      remainingOwnCaches:cacheReceipt.owned}));
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
