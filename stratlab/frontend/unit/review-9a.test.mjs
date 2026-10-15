// rev9a: a push click opens only paths on this site; sign-out clears what the browser kept; outside links go through safeHref.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a push click opens a same-site path, and anything else opens the home page", async () => {
  const vm = await import("node:vm");
  const handlers = {};
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: {} };
  vm.runInNewContext(read("public/sw.js"), { self, caches: {}, fetch: () => {}, URL, Response: class {}, Promise, String });
  const click = async (data) => {
    const opened = [];
    self.clients.matchAll = async () => [];
    self.clients.openWindow = async (u) => { opened.push(u); };
    let p; handlers.notificationclick({ notification: { close() {}, data }, waitUntil: (x) => { p = x; } });
    await p;
    return opened[0];
  };
  assert.equal(await click({ url: "/paper?x=1" }), "/paper?x=1");
  assert.equal(await click({}), "/paper");
  for (const bad of ["https://evil.example/", "//evil.example/", "/\\evil.example", "javascript:alert(1)", "paper", 5, "/\n/evil.example"])
    assert.equal(await click({ url: bad }), "/", String(bad));
});

test("sign-out clears uploaded CSVs, pins and the imported strategy", async () => {
  const store = (init) => { const m = new Map(Object.entries(init));
    return { m, getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: (k) => m.delete(k) }; };
  const local = store({ "stratlab-upload-n1": "{}", "stratlab-upload-n2": "{}", "stratlab.pins": '["/paper"]', "stratlab.theme": "dark" });
  const session = store({ "stratlab.options.import": "{}", other: "1" });
  // Object.keys(localStorage) must list the keys: a Proxy over the map
  globalThis.localStorage = new Proxy(local, { ownKeys: () => [...local.m.keys()], getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true }) });
  globalThis.sessionStorage = session;
  const { clearLocalData } = await import("../src/lib/localData.ts");
  clearLocalData();
  assert.deepEqual([...local.m.keys()], ["stratlab.theme"]);                // other settings stay
  assert.deepEqual([...session.m.keys()], ["other"]);
});

test("sign-out paths call clearLocalData", () => {
  assert.match(read("src/lib/app.tsx"), /SIGNED_OUT"\) \{ writeViewAs\(null\); clearLocalData\(\); \}/);
  assert.match(read("src/lib/signout.ts"), /clearLocalData\(\);\s*writeViewAs\(null\)/);
});

test("outside links go through safeHref", () => {
  for (const f of ["src/pages/trade/EventsPage.tsx", "src/pages/trade/ClosingAuctionPage.tsx", "src/pages/admin/RulesPanel.tsx",
                   "src/pages/admin/AIPanel.tsx", "src/pages/admin/OverviewSection.tsx"])
    assert.doesNotMatch(read(f), /href=\{(?!safeHref|`|")[a-z.]*(url|consultation|dash)/i, f);
});
