import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

// site83 (Release 83): unit checks of the fixes the browser specs (e2e/site83.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

/** sw.js run with a fake cache and network; `install(addRoutes)` dispatches its install event, with or without the routes API. */
function worker() {
  const handlers = {};
  const caches = { open: async () => ({ put: async () => undefined, add: async () => undefined }), match: async () => undefined, keys: async () => [], delete: async () => true };
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: { claim() {} } };
  vm.runInNewContext(read("public/sw.js"), { self, caches, fetch: async () => { throw new Error("offline"); }, URL, Response, Promise, String, setTimeout });
  const install = async (addRoutes) => {
    const waits = [];
    const e = { waitUntil: (p) => waits.push(p) };
    if (addRoutes) e.addRoutes = addRoutes;
    handlers.install(e);
    await Promise.all(waits);
  };
  return { install, handlers };
}

test("LIVE20B-001: while the worker isn't running, every request goes to the network; while it runs, only its own files and page loads pass it", async () => {
  let routes;
  await worker().install((r) => { routes = r; return Promise.resolve(); });
  assert.deepEqual(JSON.parse(JSON.stringify(routes)), [
    { condition: { runningStatus: "not-running" }, source: "network" },
    { condition: { or: [{ requestMode: "navigate" }, { urlPattern: "/config.js" }, { urlPattern: "/theme.js" }, { urlPattern: "/boot.js" }, { urlPattern: "/favicon.svg" }] }, source: "fetch-event" },
    { condition: { requestMethod: "GET" }, source: "network" },
  ]);
  // never a race against the worker on a cold start: that started it beside the page and slowed the page's own start-up files
  assert.doesNotMatch(read("public/sw.js"), /source: "race-network-and-fetch-handler"/);
});

test("LIVE20B-001: a browser without the routes API, or one that refuses them, still installs the worker and keeps its fetch handler", async () => {
  const a = worker();
  await a.install(undefined);
  assert.equal(typeof a.handlers.fetch, "function");
  const b = worker();
  await b.install(() => { throw new TypeError("unknown condition"); });          // a browser that knows addRoutes but not one of the conditions
  const c = worker();
  await c.install(() => Promise.reject(new TypeError("bad route")));
  // the offline page still answers a failed page load where the handler runs (Safari, Firefox, or a running worker)
  let answer;
  c.handlers.fetch({ request: { method: "GET", url: "https://stratlab.studio/mine", mode: "navigate" }, respondWith: (p) => { answer = p; } });
  const res = await answer;
  assert.equal(res.status, 503);
  assert.match(await res.text(), /StratLab can't be reached/);
});
