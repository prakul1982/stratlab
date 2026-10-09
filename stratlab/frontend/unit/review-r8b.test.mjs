// Round 8B review of the live site at India's close (9 Oct 2026): the app's side, each on the reviewer's example.
// Every clock here is a fixed instant. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R8B-002: the paper overview gives the deepest fall in money and its day, not a percentage alone", () => {
  const src = read("src/components/RiskOverview.tsx");
  assert.match(src, /deepest_fall\?: \{ pnl: number; pct: number; date: string \} \| null/);
  assert.match(src, /money\(c\.deepest_fall\.pnl, c\.currency\)\} from the high point, \$\{day\(c\.deepest_fall\.date\)\}/);
});

test("R8B-005: the PCR table says how many strikes were read, never an 'All strikes read' column that repeats the PCR", async () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /header: "All strikes read"/);
  assert.match(page, /header: "Strikes read"/);
  const { strikesRead, ratio } = await import("../src/lib/positioning.ts");
  assert.equal(strikesRead(31, 15, 1.09, ratio), "31 strikes read");                       // the live read: the near window only
  assert.equal(strikesRead(81, 15, 0.6, ratio), "all strikes read 0.60 (81 strikes)");      // a wider read: its own PCR
  assert.equal(strikesRead(undefined, 15, 1.09, ratio), "");
});

test("R8B-007: a brief's web page shows the AI's words under the facts line", () => {
  const page = read("src/pages/NewsPage.tsx");
  assert.ok(page.indexOf("{issue.summary && <p className=\"k-lede\">") < page.indexOf("{issue.ai_summary && <p data-testid=\"news-ai-summary\">"));
  assert.match(read("src/lib/news.ts"), /ai_summary\?: string \| null/);
});

test("R8B-008: yesterday's numbers on the evening of today say when today's are due", async () => {
  const { latestDue } = await import("../src/lib/format.ts");
  const pending = { day: "2026-10-09", due: "18:30 IST" };
  assert.equal(latestDue("2026-10-08", pending), "Latest: 8 Oct · 9 Oct due about 18:30 IST");
  assert.equal(latestDue("2026-10-09", pending), null);
  assert.equal(latestDue("2026-10-08", null), null);
  assert.equal(latestDue("2026-10-08", { day: "2026-10-09", due: null }), "Latest: 8 Oct · 9 Oct due this evening");
  const { cardFigures } = await import("../src/lib/breadth.ts");
  const today = { day: "2026-10-08", adv: { value: 300 }, dec: { value: 200 }, pct50: { value: 41.5 }, highs: { value: 3 }, lows: { value: 9 } };
  assert.equal(cardFigures({ today, live: null, pending }).when, "Latest: 8 Oct · 9 Oct due about 18:30 IST");
  assert.equal(cardFigures({ today, live: null }).when, "Last close, 8 Oct");
  const breadth = read("src/pages/BreadthPage.tsx");
  assert.match(breadth, /title=\{latestDue\(t\.day, pending\) \?\? \(lastClose/);
  assert.match(read("src/pages/Screens.tsx"), /data-testid="screens-pending"/);
});

test("R8B-010: the closing auction's final price and gap come right after the stock", () => {
  const all = read("src/pages/trade/ClosingAuctionPage.tsx");
  const src = all.slice(all.indexOf("const cols: Column<CasStock>[] = ["));
  const at = (k) => src.indexOf(`{ key: "${k}", header:`);
  assert.ok(at("stock") < at("price") && at("price") < at("gap") && at("gap") < at("ref"), "stock, final price, gap, then the reference");
});

test("R8B-011: every 'Opening' state has the Reload after a wait, and the offline page has a Reload that needs no script", async () => {
  // the app's start, a page's code downloading, and a visitor's start all use the timed Opening
  const main = read("src/main.tsx");
  assert.match(main, /<Suspense fallback=\{<><h1 className="sr-only">Opening the page<\/h1><Opening \/><\/>\}>/);
  assert.match(main, /<Opening label="Opening StratLab" \/>/);
  assert.match(read("src/visitor/VisitorApp.tsx"), /<Opening label="Opening StratLab" \/>/);
  // the service worker's offline page, for a dropped connection and for a 5xx with no copy of the app kept
  const vm = await import("node:vm");
  const src = read("public/sw.js");
  const handlers = {};
  const caches = { open: async () => ({ put: async () => undefined, add: async () => undefined }), match: async () => undefined, keys: async () => [], delete: async () => true };
  class Response { constructor(body, init) { this.body = body; this.status = init.status; } static error() { return "error"; } }
  const self = { addEventListener: (t, f) => { handlers[t] = f; }, location: { origin: "https://stratlab.studio" }, skipWaiting() {}, clients: { claim() {} } };
  let net = () => Promise.resolve({ ok: false, status: 503, headers: { get: () => "text/html" } });
  vm.runInNewContext(src, { self, caches, fetch: () => net(), URL, Response, Promise, String });
  const ask = async (url) => { let a; handlers.fetch({ request: { method: "GET", url, mode: "navigate" }, respondWith: (p) => { a = p; } }); return a; };
  const res = await ask("https://stratlab.studio/research/screens?x=1");
  assert.equal(res.status, 503);
  assert.match(res.body, /StratLab can't be reached/);
  assert.match(res.body, /<form method="get" action="\/research\/screens\?x=1"><button type="submit" data-testid="offline-reload"[^>]*>Reload<\/button><\/form>/);
  assert.match(res.body, /<meta http-equiv="refresh" content="30">/);
  net = () => Promise.reject(new Error("dropped"));
  assert.match((await ask("https://stratlab.studio/invest")).body, /action="\/invest"><button type="submit"/);
  assert.match((await ask('https://stratlab.studio/a"<b>')).body, /action="\/a%22%3Cb%3E"/);     // the address is never markup
});
