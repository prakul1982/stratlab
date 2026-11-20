import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a .ts file's extensionless imports, as the build resolves them (as unit/site81.test.mjs)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// site82 (Release 82): unit checks of the fixes the browser specs (e2e/site82.spec.ts) prove on the pages.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("LIVE19A-006: the points card says its basis from the payload (free float, or market value)", () => {
  assert.match(read("src/pages/PulseMood.tsx"), /\$\{m\.note \|\|/);
});

test("LIVE19B-002: /plans on a phone: both switches one width, each choice an equal half, a long label wrapping inside it", () => {
  assert.match(css, /\.lp-period > \*, \.lp-period \.cur-switch \{ flex-basis: 100%; \}/);
  assert.match(css, /\.lp-period \.k-seg, \.k-plan-opts \.k-seg \{ display: grid; grid-auto-flow: column; grid-auto-columns: minmax\(0, 1fr\); width: 100%; \}/);
  assert.match(css, /\.lp-period \.k-seg button, \.k-plan-opts \.k-seg button \{ min-width: 0; white-space: normal;/);
  assert.match(read("src/pages/PlansPage.tsx"), /<div className="k-plan-opts"><FormGrid label="Price options">/);
});

test("LIVE19B-008: the journal's as-of row from the first frame, and its upload card's controls the card's width on a phone", () => {
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /asOfPending=\{!j\} infoRow/);
  assert.match(j, /<Card label="Bring in your trades" className="j-bring">/);
  const head = read("src/components/kit/PageHeader.tsx");
  assert.match(head, /const inLede = inline && !infoRow;/);
  assert.match(css, /\.j-bring > \.k-card-head > \.k-card-actions > \.k-seg, \.j-bring > \.k-card-head > \.k-card-actions > \.btn, \.j-bring \.k-row > \.k-upload,/);
});

test("LIVE19B-006: the options builder draws its underlyings list from the first frame and keeps the expiry choices on one row", () => {
  const o = read("src/pages/OptionsPage.tsx");
  assert.doesNotMatch(o, /\{!!unds\?\.length && \(\s*<Select small label="Other underlyings"/);
  assert.match(o, /<Select small label="Other underlyings" value=\{onPopular \? "" : `\$\{s\.exchange\}:\$\{s\.underlying\}`\} disabled=\{!unds\?\.length\}/);
  assert.match(o, /\{!und && <span className="k-note" aria-hidden="true">&nbsp;<\/span>\}/);
  assert.match(css, /\.k-expiry \{ display: flex; flex-direction: column; align-items: stretch; gap: 6px; min-height: 174px; \}/);
  assert.match(css, /\.k-expiry > \.k-seg \{ display: flex; flex-direction: column; width: 100%; \}/);
});

test("LIVE19B-007: holdings' import card waits for the sectors and positions, so nothing under the second loading card moves", () => {
  assert.match(read("src/pages/HoldingsPage.tsx"), /\{view && rows\.length > 0 && actionsReady && importPart\}/);
});

test("LIVE19B-009: a whole page's plan note waits for the page's title, so the scan page draws one lock message once", () => {
  const lock = read("src/components/PageLock.tsx");
  assert.match(lock, /if \(!\(slot && slot\.isConnected\)\) return null;/);
  assert.doesNotMatch(lock, /: note;/);
});

test("LIVE19B-011: three watched stocks stack the Invest home's cards across the page", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /\.length <= 3;/);
});

test("LIVE19A-011: every results row names its quarter, and the day tables share one column set at fixed widths", async () => {
  const { quarterLabel } = await import("../src/lib/resultsRows.ts");
  assert.deepEqual(quarterLabel("Oct 2026 vs Oct 2025", "2026-11-19"), { text: "quarter to Oct 2026", prior: false });
  assert.deepEqual(quarterLabel("Jul 2026 vs Jul 2025", "2026-11-19"), { text: "previous quarter, to Jul 2026", prior: true });
  // updated on purpose (site83, LIVE20A-006): a filed row is no longer taken to be of its own quarter (IES, filed 20 Nov for Sep 2026,
  // said "quarter to Jun 2026"), so quarterLabel no longer takes "filed"; unit/site83 has the filed cases
  assert.equal(quarterLabel(null, "2026-11-19"), null);
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /data-testid="res-q-of">\{l\.text\}/);
  // updated on purpose (Release 82 CI): "Implied" stays a day's own column (R15 #11, e2e/r15-pages); it is the last column, so the first five
  // keep their fixed widths and still line up
  assert.match(page, /columns=\{pageColumns\.filter\(\(c\) => c\.key !== "im" \|\| on\.some\(\(r\) => r\.fo\)\)\} stack compact phonePage=\{10\}/);
  assert.doesNotMatch(page, /movesEmpty\(on, moves, on\.length\)/);
  assert.match(page, /<div key=\{d\} className="inv-day res-days" data-testid="results-day">/);
  const inv = read("src/styles-invest.css");
  assert.match(inv, /\.res-days \.k-table \{ table-layout: fixed; width: 100%; \}/);
  // the sort by a column the page doesn't show is not offered
  assert.match(page, /sorts=\{mvEmpty && filters\.sort !== "move" \?/);
});

test("LIVE19B-003: early.js asks nothing once the app's code is running (it arrived late on a cold launch and asked every read twice)", () => {
  const src = read("public/early.js");
  const run = (appRunning) => {
    const calls = [];
    const store = new Map([["sb-demo-auth-token", JSON.stringify({ access_token: "tok", expires_at: Math.floor(Date.now() / 1000) + 3600 })]]);
    const win = { STRATLAB_CONFIG: { API_BASE: "https://api.example", SUPABASE_URL: "https://demo.supabase.co" }, ...(appRunning ? { __stratlabApp: Date.now() } : {}) };
    const doc = { head: { appendChild: () => undefined }, createElement: () => ({}) };
    new Function("window", "document", "localStorage", "fetch", "location", src)(win, doc, { getItem: (k) => store.get(k) ?? null },
      (url) => { calls.push(url.replace("https://api.example", "")); return Promise.resolve({}); }, { pathname: "/trade" });
    return calls;
  };
  assert.equal(run(false).length, 5);
  assert.deepEqual(run(true), []);
  assert.match(read("src/main.tsx"), /\(window as unknown as \{ __stratlabApp\?: number \}\)\.__stratlabApp = Date\.now\(\);/);
  assert.match(read("public/boot.js"), /e\.fetchPriority = "high"; e\.src = "\/early\.js";/);
});

test("LIVE19A-012: a page load's request goes out while the service worker starts (navigation preload)", () => {
  const sw = read("public/sw.js");
  assert.match(sw, /self\.registration\.navigationPreload\.enable\(\)/);
  assert.match(sw, /const page = Promise\.resolve\(e\.preloadResponse\)\.catch\(\(\) => undefined\)\.then\(\(pre\) => pre \|\| fetch\(req\)\);/);
});

test("LIVE19B-004 / LIVE19B-010: Pro's AI builds say the cap alone; a usage row with no limit has no reset date", async () => {
  const { unlimitedLabel } = await import("../src/lib/plans.ts");
  assert.equal(unlimitedLabel("pro", "ai_builds_per_month"), "Up to 200 a day");
  const { resetsWord } = await import("../src/lib/usageText.ts");
  assert.equal(resetsWord({ resets: "month", limit: null }), "–");
  assert.equal(resetsWord({ resets: null, limit: null }), "–");
  assert.equal(resetsWord({ resets: "month", limit: 10 }, new Date("2026-11-20T10:00:00Z")), "1 Dec");
  assert.equal(resetsWord({ resets: "day", limit: 30 }), "Midnight India time");
});

test("LIVE19B accessibility: a checkbox is a 24px target on a desktop too", () => {
  assert.match(css, /\.k-check input \{ width: 24px; height: 24px; accent-color: var\(--blue\); \}/);
});

test("LIVE19B: the closing auction's rows say final or indicative only where it differs from the column's head", () => {
  assert.match(read("src/pages/trade/ClosingAuctionPage.tsx"), /\{!!r\.final_out !== final && <span className="k-sub-line">\{r\.final_out \? "final" : "indicative"\}<\/span>\}/);
});

test("LIVE19A-011: the calendars' search is drawn above the filters, which come with the figures (it moved 265px down when they came)", () => {
  const f = read("src/components/CalendarFilters.tsx");
  assert.ok(f.indexOf("{search}") < f.indexOf('<div className="res-filter-grid">'));
  assert.equal((f.match(/\{search\}/g) ?? []).length, 1);
});
