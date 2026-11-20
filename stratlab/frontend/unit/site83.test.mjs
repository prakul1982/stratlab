import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/site82.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

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

test("LIVE20A-006: a filed row with an older quarter kept says previous quarter; the meeting's own quarter decides when it names one", async () => {
  const { quarterLabel, reportedQuarter, movesEmpty } = await import("../src/lib/resultsRows.ts");
  // BJ's, filed Fri 20 Nov for the quarter ended Oct 2026, figures to Aug 2026
  assert.deepEqual(quarterLabel("Aug 2026 vs Aug 2025", "2026-11-20", { filedAt: "2026-11-20T07:00:00" }), { text: "previous quarter, to Aug 2026", prior: true });
  assert.deepEqual(quarterLabel("Aug 2026 vs Aug 2025", "2026-11-20", { reported: reportedQuarter("Quarterly results (quarter ended Oct 2026)") }), { text: "previous quarter, to Aug 2026", prior: true });
  // IES, filed for the quarter ended Sep 2026, figures to Jun 2026
  assert.equal(quarterLabel("Jun 2026 vs Jun 2025", "2026-11-20", { filedAt: "2026-11-20" }).prior, true);
  // once the filed quarter is read, it is its own
  assert.deepEqual(quarterLabel("Oct 2026 vs Oct 2025", "2026-11-20", { filedAt: "2026-11-20", reported: "Oct 2026" }), { text: "quarter to Oct 2026", prior: false });
  assert.deepEqual(quarterLabel("Sep 2026 vs Sep 2025", "2026-11-14", { filedAt: "2026-11-14" }), { text: "quarter to Sep 2026", prior: false });
  assert.equal(reportedQuarter("Quarterly results (fiscal Q3 2027)"), null);
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /r\.q\?\.unreported && r\.out \? <span className="k-muted" data-testid="res-q-unread"[^>]*>Not read yet<\/span> :/);
  // the US column with no company that has an earlier results day kept: decided from the first frame, no "–" column and loading bars
  const rows = Array.from({ length: 30 }, (_, i) => ({ symbol: `S${i}`, mv_days: i < 2 ? 3 : 0 }));
  assert.equal(movesEmpty(rows, {}), true);
  assert.equal(movesEmpty(rows.map((r, i) => ({ ...r, mv_days: i < 5 ? 3 : 0 })), {}), false);           // five could still bring one
});

test("LIVE20A-007: the IPO banner says when the list is read next; an older close is the stock's last trade", async () => {
  const { problemNote } = await import("../src/lib/ipoText.ts");
  const t = problemNote(["SEC filings for Zeno42 Inc.: The SEC is having trouble (500)."], "19 Nov, 22:00 ET", "20 Nov, 11:00 ET");
  assert.match(t, /It is read again at 20 Nov, 11:00 ET\.$/);
  assert.doesNotMatch(t, /within the hour/);
  assert.match(problemNote(["12 Sep calendar: timeout"], null, null), /It is read again at the list's next read\.$/);
  const page = read("src/pages/IposPage.tsx");
  assert.match(page, /\(older \? `Last traded \$\{fmtDate\(p\.latest_date, \{ year: false \}\)\} · ` : `Close /);
  assert.match(page, /d\.next_read \? asOf\(d\.next_read, \{ tz: marketTz\(market\), year: false \}\) : null/);
});

test("LIVE20B-005 / 007 / 009 / 008: one 'too few', one 'over', 'the trade journal', the expiry notes' room, bare pages' notes at once, the RD so far", async () => {
  const { heroSummary } = await import("../src/lib/tradeUi.ts");
  assert.deepEqual(heroSummary("Only 9 closed trades here. That's too few to tell a real edge from a lucky streak, whatever the P&L says.", "Only 9 trades: too few to judge."),
    ["That's too few to tell a real edge from a lucky streak, whatever the P&L says."]);
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /heroSummary\(v\.summary, `\$\{v\.headline\}`\)/);
  assert.match(j, /c\.id === "sample" && c\.status === "fail" \? "Under 15 trades, luck can decide the result; 30 or more make a fair sample\."/);
  const { lockWords } = await import("../src/lib/lockText.ts");
  assert.equal(lockWords("Trade journal: every trade, the honesty checks, breakdowns and paper vs real", "Basic", "Free", false),
    "Basic adds the trade journal: every trade, the honesty checks, breakdowns and paper vs real. Everything else here is on your Free plan.");
  assert.match(read("src/lib/closingAuction.ts"), /closed: "Final prices are the official closes\.",/);
  const css = read("src/styles.css");
  assert.match(css, /@media \(min-width: 641px\) \{\n  \.k-expiry \{ display: grid; grid-template-columns: max-content minmax\(0, 1fr\);[^}]*min-height: 66px; \}/);
  const { BARE_PAGES } = await import("../src/lib/gates.ts");
  assert.ok(BARE_PAGES.has("/trade/positioning"));
  assert.ok(!BARE_PAGES.has("/money/net-worth"));          // a page with notes of its own still waits (LIVE6-020)
  assert.match(read("src/components/PageLock.tsx"), /const partial = !gate\?\.whole && !BARE_PAGES\.has\(/);
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /`paid so far \$\{inr\(f\.paid_in\)\} of \$\{inr\(f\.total_in\)\}`/);
});

test("LIVE20B-012 / 006: the no-JS plans words say a dollar figure, not today's rate; the watchlist says Close once the market has shut", () => {
  const seo = read("src/content/seo.ts");
  assert.match(seo, /"Prices are in Indian rupees, with a dollar figure beside each, and the payment is charged in rupees\./);
  assert.doesNotMatch(seo, /beside each at today's rate/);
  assert.match(read("src/pages/Research.tsx"), /const at = shut \? "Close" : quoteAt\(q\.at, marketTz\(region\)\);/);
});
