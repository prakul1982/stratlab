// Review 4d (data layer and research UI): the watchlist button, fractional quantities' minus, the missing-data line for an
// unknown source, and the company page's two requests merged by source. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

// research.ts reads React, the router and the API client; here each is a stand-in (this file runs in its own process), so the
// watchlist hook can be driven as the company page's Watch button drives it, against a saved list held in memory
const mod = (src) => "data:text/javascript," + encodeURIComponent(src);
const REACT = mod(`export const useState = (v) => [typeof v === "function" ? v() : v, () => {}];
export const useEffect = (fn) => { fn(); }; export const useCallback = (fn) => fn; export const useRef = (v) => ({ current: v });
export const useMemo = (fn) => fn();`);
const ROUTER = mod(`export const useSearchParams = () => [new URLSearchParams(), () => {}];`);
const API = mod(`export class ApiError extends Error {}
export async function api(path, opts = {}) {
  const w = globalThis.__watch, method = opts.method ?? "GET";
  w.calls.push([method, path, opts.body]);
  if (method === "GET") { if (w.failGets > 0) { w.failGets--; throw new Error("503"); } return { items: w.saved }; }
  w.saved = opts.body.items; return {};
}`);
register(mod(`export async function resolve(s, c, next) {
  if (s === "react") return { url: ${JSON.stringify(REACT)}, shortCircuit: true };
  if (s === "react-router-dom") return { url: ${JSON.stringify(ROUTER)}, shortCircuit: true };
  if (s === "./api" && String(c.parentURL).endsWith("/src/lib/research.ts")) return { url: ${JSON.stringify(API)}, shortCircuit: true };
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.__watch = { failGets: 1, calls: [], saved: [{ region: "IN", symbol: "TCS", name: "TCS" }, { region: "IN", symbol: "INFY", name: "Infosys" }] };
const R = await import("../src/lib/research.ts");
const { qty } = await import("../src/lib/format.ts");
const { missingLine, missingWhat } = await import("../src/lib/researchFormat.ts");

test("Watch pressed while the saved list was still unread never removes a company already on it", async () => {
  const w = R.useWatchlist();                         // the first read of the saved list fails (a 503)
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(w.has("IN", "TCS"), false);            // so the company page's button says "Watch"
  const changed = await w.toggle({ region: "IN", symbol: "TCS", name: "TCS" }, true);
  assert.equal(changed, false);
  assert.deepEqual(globalThis.__watch.saved.map((i) => i.symbol), ["TCS", "INFY"]);
  assert.deepEqual(globalThis.__watch.calls.filter((c) => c[0] === "PUT"), []);          // nothing saved
  assert.equal(R.watchNote("TCS", true, changed), "TCS is already on your watchlist.");
  // the other directions do what was asked, and say what happened
  assert.equal(await w.toggle({ region: "IN", symbol: "WIPRO", name: null }, true), true);
  assert.equal(await w.toggle({ region: "IN", symbol: "INFY", name: null }, false), true);
  assert.equal(await w.toggle({ region: "IN", symbol: "HCLTECH", name: null }, false), false);
  assert.deepEqual(globalThis.__watch.saved.map((i) => i.symbol), ["TCS", "WIPRO"]);
  assert.equal(R.watchNote("WIPRO", true, true), "WIPRO added to your watchlist.");
  assert.equal(R.watchNote("INFY", false, true), "INFY removed from your watchlist.");
  assert.equal(R.watchNote("HCLTECH", false, false), "HCLTECH isn't on your watchlist.");
});

test("watchChange adds only what is missing and removes only what is there", () => {
  const cur = [{ region: "IN", symbol: "TCS", name: "TCS" }];
  assert.deepEqual(R.watchChange(cur, { region: "IN", symbol: "TCS", name: null }, true), { list: cur, changed: false });
  assert.equal(R.watchChange(cur, { region: "IN", symbol: "TCS", name: null }, true).list, cur);
  assert.deepEqual(R.watchChange(cur, { region: "US", symbol: "TCS", name: null }, true).list.map((i) => i.region), ["IN", "US"]);
  assert.deepEqual(R.watchChange(cur, { region: "IN", symbol: "TCS", name: null }, false), { list: [], changed: true });
  assert.deepEqual(R.watchChange(cur, { region: "IN", symbol: "INFY", name: null }, false), { list: cur, changed: false });
});

test("a fractional quantity has the same true minus as a whole one, and never reads -0", () => {
  assert.equal(qty(-50), "−50");
  assert.equal(qty(-0.5), "−0.5");
  assert.equal(qty(-1234.5), "−1,234.5");
  assert.equal(qty(-1234.5, undefined, "US"), "−1,234.5");
  assert.equal(qty(-1e-9), "0");
  assert.equal(qty(-0.05, 1e-8), "−0.05000000");
  assert.equal(qty(-1e-10, 1e-8), "0");
  assert.equal(qty(0.5), "0.5");
  assert.doesNotMatch(qty(-0.25) + qty(-0.25, 0.01), /-/);
});

test("the missing-data line makes sense for a source it has no name for", () => {
  assert.equal(missingLine([{ source: "Data", ok: false }]), "Some data is missing.");
  assert.equal(missingLine([{ source: "Data", ok: false }, { source: "News", ok: false }]), "Some data is missing: news and other data.");
  assert.equal(missingLine([{ source: "Data", ok: false }, { source: "News", ok: false }, { source: "Live prices", ok: false }]),
    "Some data is missing: news, prices and other data.");
  assert.equal(missingLine([{ source: "News", ok: false }]), "Some data is missing: news.");
  assert.deepEqual(missingWhat([{ source: "Data", ok: false }]), ["other data"]);
  assert.doesNotMatch(missingLine([{ source: "Data", ok: false }]), /some data\./);
});

test("a source that failed in the company page's second request still shows as missing", () => {
  const c = { symbol: "TCS", news: [], peers: [], about: { wiki: null, profile: null }, lazy: ["news"],
    sources: [{ source: "News", ok: true, error: null }, { source: "Fundamentals", ok: true, error: null }] };
  const m = { news: [], wiki: null, peers: [], sources: [{ source: "News", ok: false, error: "slow", what: ["news"] }, { source: "Encyclopedia", ok: true, error: null }] };
  const out = R.withMore(c, m);
  assert.deepEqual(out.sources.map((s) => [s.source, s.ok]), [["News", false], ["Fundamentals", true], ["Encyclopedia", true]]);
  assert.equal(missingLine(out.sources), "Some data is missing: news.");
  // ...and one that failed in the first and worked in the second stays missing (what the page showed was read then)
  const first = { ...c, sources: [{ source: "Fundamentals", ok: false, error: "x", what: ["financials"] }] };
  const again = R.withMore(first, { ...m, sources: [{ source: "Fundamentals", ok: true, error: null }] });
  assert.deepEqual(again.sources.map((s) => [s.source, s.ok]), [["Fundamentals", false]]);
  assert.equal(c.sources[0].ok, true);                // the first answer isn't changed in place
});
