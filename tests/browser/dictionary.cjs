// Run against the local, isolated OfflineDictionaryTest app; requires Playwright.
const {chromium} = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

(async () => {
  const base = process.env.DICTIONARY_TEST_URL || "http://127.0.0.1:53947";
  const output = await fs.mkdtemp(path.join(os.tmpdir(), "lexi-dictionary-browser-"));
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:390,height:844},locale:"ru-RU",colorScheme:"dark",acceptDownloads:true});
  const page = await context.newPage();
  const errors = [];
  const external = [];
  page.on("pageerror",error=>errors.push(error.message));
  page.on("request",request=>{if(new URL(request.url()).origin!==new URL(base).origin)external.push(request.url());});
  try {
    await page.goto(`${base}/dictionary/?target=de&native=ru&ui=ru`);
    await page.locator(".word-row").first().waitFor();
    assert.equal(await page.locator("#target-language").inputValue(),"de");
    await page.locator("#dictionary-query").fill("школа");
    assert.match(await page.locator("#dictionary-results").innerText(),/Schule/);
    await page.locator(".save-word").first().click();
    await page.reload();
    assert.equal(await page.locator("#saved-count").innerText(),"1");
    await page.locator("#view-saved").click();
    assert.equal(await page.locator(".word-row").count(),1);
    await page.locator("#start-practice").click();
    assert.equal(await page.locator("#dictionary-results").isVisible(),false);
    await page.locator("#practice-input").fill("школа");
    await page.locator("#check-answer").click();
    assert.match(await page.locator("#practice-feedback").innerText(),/Верно/);
    await page.locator("#next-word").click();
    assert.match(await page.locator("#practice-question").innerText(),/1 из 1/);
    await page.locator("#close-practice").click();
    await page.locator("#view-all").click();
    const codes = ["en","fr","de","ar","zh","ru","es"];
    for (const target of codes) {
      await page.locator("#target-language").selectOption(target);
      for (const native of codes.filter(code=>code!==target)) {
        await page.locator("#native-language").selectOption(native);
        assert.match(await page.locator("#pack-note").innerText(),/100/);
      }
    }
    await page.locator("#target-language").selectOption("fr");
    await page.locator("#native-language").selectOption("ru");
    await page.locator("#dictionary-query").fill("E\u0301COLE");
    assert.match(await page.locator("#dictionary-results").innerText(),/école/);
    await page.locator("#dictionary-query").fill("<script>alert('xss')</script>");
    assert.equal(await page.locator("#empty-results").isVisible(),true);
    assert.equal(external.length,0,"Search must not send text to an external service");
    assert.equal(new URL(await page.locator("#translate-link").getAttribute("href")).hostname,"translate.yandex.com");
    await page.locator("#dictionary-query").fill("école");
    await page.screenshot({path:path.join(output,"mobile.png"),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    const downloadPromise=page.waitForEvent("download");
    await page.locator("#download-dictionary").click();
    const download=await downloadPromise;
    const downloaded=path.join(output,"lexi-dictionary.html");await download.saveAs(downloaded);
    await page.locator("#save-offline").click();
    await page.waitForFunction(()=>document.getElementById("offline-status").textContent.includes("Словарь сохранён"));
    // Same-tab uninstall/reinstall must not depend on serviceWorker.ready's old promise.
    await page.locator("#remove-offline").click();
    await page.waitForFunction(()=>document.getElementById("remove-offline").hidden);
    await page.locator("#save-offline").click();
    await page.waitForFunction(()=>document.getElementById("offline-status").textContent.includes("Словарь сохранён"));
    const cacheUrls=await page.evaluate(async()=>{const results=[];for(const key of await caches.keys()){const c=await caches.open(key);results.push(...(await c.keys()).map(request=>new URL(request.url).pathname));}return results;});
    assert(cacheUrls.every(url=>["/dictionary/","/static/dictionary.css","/static/dictionary.js","/dictionary/manifest.webmanifest"].includes(url)));
    await context.setOffline(true);
    assert.equal(await page.locator("#translate-link").isVisible(),false);
    await page.close();
    const offline=await context.newPage();offline.on("pageerror",error=>errors.push(error.message));
    await offline.goto(`${base}/dictionary/`);
    await offline.locator(".word-row").first().waitFor();
    // Chromium's new-tab navigator.onLine hint can remain true despite blocked
    // network. The existing-tab offline event is checked above; this checks
    // actual cold loading/search with network unavailable.
    await offline.locator("#target-language").selectOption("de");
    await offline.locator("#native-language").selectOption("ru");
    await offline.locator("#dictionary-query").fill("Schule");
    assert.match(await offline.locator("#dictionary-results").innerText(),/школа/);
    assert.equal(await offline.locator("#saved-count").innerText(),"1");
    // Download is independently usable even without HTTP or a service worker.
    const file=await context.newPage();file.on("pageerror",error=>errors.push(error.message));
    await file.goto(`file://${downloaded}`);
    await file.locator(".word-row").first().waitFor();
    assert.equal(await file.locator("#target-language").inputValue(),"fr");
    assert.equal(await file.locator("#native-language").inputValue(),"ru");
    assert.equal(await file.locator("#interface-language").inputValue(),"ru");
    await file.locator("#dictionary-query").fill("école");
    assert.match(await file.locator("#dictionary-results").innerText(),/школа/);
    await file.locator(".brand").click();
    assert(file.url().startsWith(`file://${downloaded}`));
    await context.setOffline(false);
    const desktop=await context.newPage();await desktop.setViewportSize({width:1280,height:900});await desktop.emulateMedia({colorScheme:"light"});
    await desktop.goto(`${base}/dictionary/?target=en&native=ru&ui=ru`);
    await desktop.locator(".word-row").first().waitFor();
    await desktop.screenshot({path:path.join(output,"desktop.png"),fullPage:true});
    await desktop.evaluate(()=>localStorage.setItem("lexi:dictionary:v1",JSON.stringify({preferences:{ui:42,target:[],native:{}},saved:{}})));
    await desktop.reload();await desktop.locator(".word-row").first().waitFor();
    assert.deepEqual(errors,[]);
    console.log(JSON.stringify({ok:true,checks:["42 language pairs","Unicode/reverse lookup","saved persistence","written feedback","no external query traffic","mobile overflow","offline save/remove/resave","cold offline tab","standalone download","malformed storage"],output}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
