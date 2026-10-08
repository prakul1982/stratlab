// Round 6, the owner's review on the live site (8 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Admin's AI tile counts paused and out-of-quota providers honestly (R6O-003)", async () => {
  const { aiTile } = await import("../src/pages/admin/attention.ts");
  const row = (label, extra) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: true, ...extra });
  const ai = [row("Groq"), row("Hugging Face", { paused_models: 1 }), row("Cerebras", { answering: false, quota_used: true, state_text: "Free quota used up" }),
    { label: "Unset", configured: false, in_use: false, model: null, last_error: null }];
  const t = aiTile(ai);
  assert.equal(t.detail, "2 of 3 answering · 1 out of free quota · 1 with a model paused");
  assert.equal(t.state, "warn");
  assert.equal(aiTile([row("Groq"), row("Mistral")]).state, "ok");
  assert.equal(aiTile([row("Groq", { paused_models: 2 })]).state, "warn");          // a paused model is never "OK, all answering"
});

test("A results day whose quarter is already in the table reads as filed (R6O-016)", async () => {
  const { resultsFiled } = await import("../src/lib/researchFormat.ts");
  assert.equal(resultsFiled("2026-10-08", "Sep 2026", "2026-10-08"), true);         // TCS at 23:47 IST, Sep 2026 in the table
  assert.equal(resultsFiled("2026-10-08", "Jun 2026", "2026-10-08"), false);        // still to come: the table ends in June
  assert.equal(resultsFiled("2026-10-29", "Jun 2026", "2026-10-08"), false);        // a day ahead
  assert.equal(resultsFiled(null, "Sep 2026", "2026-10-08"), false);
  assert.match(read("src/lib/mine.ts"), /results_out/);                           // filed results aren't "coming up"
});

test("Service worker: an offline page load with no kept copy gets an offline page, never nothing; the shell is cached file by file (R6O-006)", async () => {
  const vm = await import("node:vm");
  const src = read("public/sw.js");
  const handlers = {}, added = [];
  const caches = {
    open: async () => ({ put: async () => undefined, add: async (f) => { if (f === "/icon-192.png") throw new Error("502"); added.push(f); } }),
    match: async () => undefined, keys: async () => [], delete: async () => true,
  };
  class Response { constructor(body, init) { this.body = body; this.status = init.status; } static error() { return "error"; } }
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: { claim() {} } };
  vm.runInNewContext(src, { self, caches, fetch: () => Promise.reject(new Error("TLS handshake")), URL, Response, Promise });
  let waited;
  handlers.install({ waitUntil: (p) => { waited = p; } });
  await waited;
  assert.ok(added.includes("/") && added.includes("/config.js"), "one failed file doesn't stop the others");
  let answer;
  handlers.fetch({ request: { method: "GET", url: "https://stratlab.studio/mine", mode: "navigate" }, respondWith: (p) => { answer = p; } });
  const res = await answer;
  assert.ok(res && res.status === 503 && /can't be reached/.test(res.body));
});

test("Breadth opens on the reader's market: an India reader gets an Indian group, never the S&P 500 picked elsewhere (R6O-007)", async () => {
  const mem = new Map();
  globalThis.localStorage = { getItem: (k) => (mem.has(k) ? mem.get(k) : null), setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
  const { savedPick, savePick } = await import("../src/lib/breadthPick.ts");
  assert.deepEqual(savedPick("IN"), { group: "nifty500", range: "1y", picked: false });
  mem.set("stratlab.breadth", JSON.stringify({ group: "sp500", range: "6m" }));       // the S&P 500, picked once while on the US
  assert.deepEqual(savedPick("IN"), { group: "nifty500", range: "6m", picked: false });
  assert.equal(savedPick("US").group, "sp500");
  savePick("midcap150", "1y");
  assert.deepEqual(savedPick("IN"), { group: "midcap150", range: "1y", picked: true });
  assert.equal(savedPick("US").group, "sp500");                                        // each market keeps its own pick
  assert.match(read("src/components/BreadthCard.tsx"), /BROAD_GROUP\[region\]/);         // no counts yet: the broad group
  delete globalThis.localStorage;
});

test("Notebook: the question keeps the person's casing, the rule line never says 'or a no target', the chart opens on the test window (R6O-010)", async () => {
  const { questionFrom } = await import("../src/lib/rules.ts");
  const q = questionFrom("R test: Buy RELIANCE when the 20-day EMA crosses above the 50-day EMA, sell when it crosses back below, stop loss 3%", "RELIANCE");
  assert.ok(q.startsWith('Does "R test: Buy RELIANCE'), q);
  const rules = read("src/components/Rules.tsx");
  assert.doesNotMatch(rules, /\{" "\}or a\{" "\}/);
  assert.match(rules, /r\.tgt > 0 \? \(r\.sl > 0 \? " or a " : " and at a "\) : \(r\.sl > 0 \? ", with " : " and "\)/);
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /openFrom=\{e\.series\.t\[0\] \?\? null\}/);
  assert.match(page, /<UnadjustedNote e=\{e\} \/>/);
});

test("View as chips fit the menu, paper-trade messages say Basic, and locks and limits read as Plans does (R6O-011, 012, 013)", async () => {
  const css = read("src/styles.css");
  assert.match(css, /\.acct-viewas \{ display: flex; flex-wrap: wrap;/);
  assert.match(css, /\.acct-pop \[role="menuitemradio"\] \{ flex: 1 1 0; min-width: 0;/);
  assert.match(read("src/components/AlertSettings.tsx"), /every paper trade\{!canAlert && <span className="k-inline-badge"><Badge tone="warn">Basic<\/Badge>/);
  const plans = read("src/lib/plans.ts");
  assert.match(plans, /every trend scan \(the Stage 2 scan/);
  assert.match(plans, /every Market Brief on News/);
  assert.match(plans, /daily Market Brief and My Stocks by email/);
  assert.match(read("src/pages/money/ItrExportPage.tsx"), /Part of this page is on \{v\.plan\}\. \{featureName\("itr_export"\)\}: on the \{v\.plan\} plan\. You're on \{yours\}/);
  assert.match(read("src/pages/AccountPage.tsx"), /me\.view_as && <p[^>]*>Your own use this month, against the \{me\.plan_info\.name\} plan's limits/);
});

test("Money: the tax card shows the F&O income the tax is on; Today names its US part, live or at the close (R6O-014, R6O-015)", async () => {
  const homes = read("src/pages/SpaceHomes.tsx");
  assert.match(homes, /label="F&O and other business income"/);
  const { usTodayNote } = await import("../src/lib/marketHours.ts");
  const us = { id: "US", name: "US", venues: "", currency: "USD", symbol: "", tz: "America/New_York", hours: { open: "09:30", close: "16:00", days: "Mon-Fri" },
    what: "", costs: "", brokerage: 0, status: "live", max_days: null };
  const live = new Date("2026-10-08T18:00:00Z");          // 14:00 in New York, 23:30 in India
  assert.equal(usTodayNote([us], { day: 5.28, in_total: true }, 96.77, live), "Today includes US stocks, US, live: it moves until the US close: +$5.28 (₹511 at ₹96.77 a dollar).");
  assert.match(usTodayNote([us], { day: -2, in_total: true }, 96.77, new Date("2026-10-09T03:00:00Z")), /US, at their last close: −\$2\.00/);
  assert.equal(usTodayNote([us], { day: 5.28, in_total: false }, 96.77, live), null);       // not in the rupee Today: nothing to name
  assert.match(read("src/pages/HoldingsPage.tsx"), /usTodayNote\(markets, view\.us, view\.usd_inr\)/);
});
