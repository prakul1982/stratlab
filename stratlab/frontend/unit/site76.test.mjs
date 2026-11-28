// Lane site76: the LIVE14A / LIVE14B site findings (live review after Release 75, Wed 18 Nov 2026). Run: npm run test:unit
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
const dayText = (iso) => `${Number(iso.slice(8, 10))} Nov`;

test("LIVE14A-001: a level the source stopped updating mid-session says its time, never 'Live' or 'today'", async () => {
  const { indexWhen, pulseClosedDay, pulseDelayedAt, pulseLede } = await import("../src/lib/research.ts");
  const at = "2026-11-18T15:52:50+00:00";
  const time = () => "10:52 ET";
  const rows = [{ name: "S&P 500", day: "2026-11-18", live: false, delayed: true, at }, { name: "NASDAQ", day: "2026-11-18", live: false, delayed: true, at }];
  assert.equal(indexWhen(rows[0], dayText, time), "as of 10:52 ET");
  assert.notEqual(indexWhen(rows[0], dayText), "today");
  assert.equal(pulseClosedDay(rows), null);                          // a session still trading is not "Last close, 18 Nov"
  assert.equal(pulseDelayedAt(rows), at);
  const lede = pulseLede(null, false, "10:52 ET");
  assert.match(lede, /^Index levels as of 10:52 ET/);
  assert.doesNotMatch(lede, /Live/);
  // a live level reads as before
  assert.equal(indexWhen({ day: "2026-11-18", live: true }, dayText, time), "today");
  assert.equal(pulseDelayedAt([{ live: true, at }]), null);
  assert.match(pulseLede(null), /^Live index levels/);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /useLiveRefresh\(!!data\?\.indices\.some\(\(i\) => i\.live \|\| i\.delayed\)/);     // asked again while delayed
});

test("LIVE14A-001: a results row priced long ago in the session carries its time, and the footer says the prices are not live", async () => {
  const { quoteDelayed } = await import("../src/lib/rowReads.ts");
  const { pricesNote } = await import("../src/lib/rowReads.ts");
  const now = Date.parse("2026-11-18T19:30:00Z");
  const t = () => "10:52 ET";
  assert.equal(quoteDelayed("2026-11-18T15:52:49Z", true, t, now), "as of 10:52 ET");
  assert.equal(quoteDelayed("2026-11-18T19:28:00Z", true, t, now), null);          // two minutes old: live
  assert.equal(quoteDelayed("2026-11-18T15:52:49Z", false, t, now), null);         // market shut: the footer says last close
  const note = pricesNote({ live: false, asOf: "10:52 ET", rows: 30, cap: 1000, closeDay: "2026-11-18", older: 0, olderDay: null, open: true, behind: true }, dayText);
  assert.match(note, /^Prices as of 10:52 ET, the latest the price source has sent: not live/);
  assert.doesNotMatch(note, /not trading now/);
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /data-testid="res-px-at"/);
});

test("LIVE14A-009: Usual move per day's table; the quarter before the one being reported says so", async () => {
  const { movesEmpty, priorQuarter } = await import("../src/lib/resultsRows.ts");
  // a day table of 12 rows, all answered, one with a usual move: no column for that table
  const rows = Array.from({ length: 12 }, (_, i) => ({ symbol: `S${i}` }));
  const back = Object.fromEntries(rows.map((r, i) => [r.symbol, i === 0 ? { moves: { avg: 16.7 } } : null]));
  assert.equal(movesEmpty(rows, back, rows.length), true);
  assert.equal(movesEmpty(rows, { ...back, S1: { moves: { avg: 2 } }, S2: { moves: { avg: 3 } } }, rows.length), false);
  assert.equal(movesEmpty(rows, { S0: { moves: { avg: 1 } } }, rows.length), false);       // still being read: the column stays
  const page = read("src/pages/ResultsPage.tsx");
  // (updated on purpose, LIVE19A-011: one column set for every day of the page (Implied when any row shown has options, Usual move by the page's rows), so the stacked day tables line up: the page's "Usual move" rule is movesEmpty over the rows shown)
  assert.match(page, /const mvEmpty = movesEmpty\(shown, moves\);/);
  assert.match(page, /columns=\{pageColumns\.filter\(\(c\) => c\.key !== "im" \|\| on\.some\(\(r\) => r\.fo\)\)\}/);   // updated on purpose: Release 82, "Implied" a day's own (R15 #11)
  // PANW on 18 Nov: figures to Jul 2026 (110 days before) are the previous quarter's; TJX's to Oct 2026 are the one reported
  assert.equal(priorQuarter("Jul 2026 vs Jul 2025", "2026-11-18"), "Jul 2026");
  assert.equal(priorQuarter("Oct 2026 vs Oct 2025", "2026-11-18"), null);
  assert.equal(priorQuarter("Sep 2026 vs Sep 2025", "2026-11-10"), null);                 // India: 41 days after the quarter
  assert.equal(priorQuarter("Jun 2026 vs Jun 2025", "2026-11-10"), "Jun 2026");
  assert.equal(priorQuarter(null, "2026-11-18"), null);
  assert.match(page, /data-testid="res-q-prior">previous quarter, to \{p\}/);
});

test("LIVE14A-013: an open Indian issue without its lot or bids says why (the issue page found or not, read or not, and when)", () => {
  const page = read("src/pages/IposPage.tsx");
  // (updated on purpose, LIVE16B-006: short in its numbers column, the why in the cell's hover text)
  assert.match(page, /if \(r\?\.page === false\) return "No NSE page yet";/);
  assert.match(page, /export const NO_PAGE_WHY = "NSE has no issue page for it yet; the lot and bids are read there\.";/);
  assert.match(page, /if \(r\?\.page && !r\.page_at\) return "NSE's issue page not read yet";/);
  assert.match(page, /if \(r\?\.page_at\) return `Not on NSE's issue page, read \$\{readAt\(r\.page_at\)\}`;/);
  assert.match(page, /tab === "open" && m === "IN" \? <span className="k-muted" data-testid="ipo-bids-none" title=\{missingWhy\(r\)\}>\{bidsMissing\(r\)\}<\/span>/);
});

test("LIVE14B-007 / LIVE14A-012: the signed-out /plans gives the sample deck its table promises", () => {
  const login = read("src/pages/Login.tsx");
  // (updated on purpose, site78 LIVE15A-003: the same module also gives the shared /info read the Free list uses)
  // (changed on purpose, conv101: the line is on the landing page's plans too, with the sample deck's own page beside the download)
  assert.match(login, /import \{ SampleDeckLink, SampleDeckPageLink, useSampleDeck \} from "\.\.\/components\/SampleDeck";/);
  assert.match(login, /<p className="small muted" data-testid="sample-deck-line">Slide decks are on Basic and Pro\. <SampleDeckLink label="Download a sample deck" \/><SampleDeckPageLink \/><\/p>/);
  assert.match(read("src/components/PlanCompare.tsx"), /0 \(a sample deck to download\)/);
});

test("LIVE14B-008: the tax report holds the year's figure's place and the price pill's while it loads", () => {
  const page = read("src/pages/TaxReportPage.tsx");
  assert.match(page, /asOfPending=\{!rep && !error && hold\.pill\}/);
  assert.match(page, /\{!rep && !error && hold\.head && <Card compact label="The year's tax" className="tax-head-hold">/);
  assert.match(read("src/styles.css"), /\.tax-head-hold \{ min-height: 85px; \}\n@media \(max-width: 640px\) \{ \.tax-head-hold \{ min-height: 145px; \} \}/);
});

test("LIVE14A-008: the theme's 'Every company' table: short header words, the long names on the phone's card, closer columns", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /key: "sales_1y", header: "Growth", cardLabel: "Revenue growth"/);
  assert.match(dive, /key: "r1y", header: "1-yr price", cardLabel: "Price, 1 year"/);
  assert.match(dive, /key: "pb", header: "P\/B", numeric: true, sortable: true, narrow: false/);
  assert.match(dive, /label: c\.cardLabel \?\? \(typeof c\.header === "string" \? c\.header : c\.key\)/);
  assert.match(read("src/styles.css"), /\.leaders-tbl \.k-table th, \.leaders-tbl \.k-table td \{ padding-left: 6px; padding-right: 6px; \}/);
  assert.ok(!read("e2e/ui-lint.allow.json").includes("Revenue growthEBIT"));
});
test("LIVE14B-001: boot.js asks for a saved sign-in's account the moment /config.js says where the server is", () => {
  const src = read("public/boot.js");
  // run boot.js's code against a stand-in window: setting the config fires one /me with the saved token
  const calls = [];
  const store = new Map([["sb-demo-auth-token", JSON.stringify({ access_token: "tok", expires_at: Math.floor(Date.now() / 1000) + 3600 })], ["stratlab.viewas.v1", "basic"]]);
  const win = { addEventListener() {}, location: { pathname: "/mine", search: "" } };
  const doc = { documentElement: { setAttribute() {}, dataset: {} }, addEventListener() {}, getElementById: () => null, readyState: "loading" };
  const fetchStub = (url, o) => { calls.push([url, o.headers]); return Promise.resolve({}); };
  new Function("window", "document", "localStorage", "sessionStorage", "fetch", "location", src)(win, doc,
    { getItem: (k) => store.get(k) ?? null, key: (i) => [...store.keys()][i], get length() { return store.size; }, setItem() {} },
    { getItem: () => null, setItem() {} }, fetchStub, win.location);
  win.STRATLAB_CONFIG = { API_BASE: "https://api.example", SUPABASE_URL: "https://demo.supabase.co" };
  assert.equal(win.STRATLAB_CONFIG.API_BASE, "https://api.example");          // the config still reads back
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], "https://api.example/me");
  assert.equal(calls[0][1].Authorization, "Bearer tok");
  assert.equal(calls[0][1]["X-View-As"], "basic");
  assert.equal(win.__stratlabEarlyMe.token, "tok");
  win.STRATLAB_CONFIG = { API_BASE: "https://api.example", SUPABASE_URL: "https://demo.supabase.co" };        // a second write: asked once
  assert.equal(calls.length, 1);
});

test("LIVE14A-016 (LIVE13A-017): a lock's price after words naming the same plan doesn't name it again", async () => {
  const { priceAfterWords } = await import("../src/lib/offer.ts");
  const price = "Basic is ₹699 a month (US price $8) or ₹6,999 a year (US price $80).";
  assert.equal(priceAfterWords("You've made 1 slide deck this month. The count starts again on 1 Dec. Basic gives 5 a month.", price),
    "It is ₹699 a month (US price $8) or ₹6,999 a year (US price $80).");
  assert.equal(priceAfterWords("Pro has no limit on alerts.", "Pro is ₹1,499 a month."), "It is ₹1,499 a month.");
  assert.equal(priceAfterWords("Market breadth history is on the Basic plan.", price), price);        // the plan not last: as it is
  assert.equal(priceAfterWords("Pro gives 50 a month.", price), price);                              // another plan's price: as it is
  assert.equal(priceAfterWords("x", null), null);
});

test("LIVE14B-009: the scan's special-sessions bracket is one numbered note under the table, its mark on each row", async () => {
  const { scanNotes } = await import("../src/lib/scanNotes.ts");
  const b = " (the averages count the exchange's special sessions of 1 Feb 2026 and 8 Nov 2026, which some price histories leave out)";
  const got = scanNotes([`50-day average 1,259.03 crossed above the 200-day average 1,256.75${b}`, `50-day average 1,896.29 crossed above 1,892.47${b}`, "Closed at 375.05", null]);
  assert.deepEqual(got.details, ["50-day average 1,259.03 crossed above the 200-day average 1,256.75¹", "50-day average 1,896.29 crossed above 1,892.47¹", "Closed at 375.05", null]);
  assert.deepEqual(got.notes, ["The averages count the exchange's special sessions of 1 Feb 2026 and 8 Nov 2026, which some price histories leave out."]);
  assert.match(read("src/pages/ResearchScans.tsx"), /data-testid="scan-sessions-note">\{MARKS\[i\]\} \{n\}<\/p>/);
});

test("LIVE13A-023: /news's heading is its menu name", () => {
  assert.match(read("src/pages/NewsPage.tsx"), /<PageHeader eyebrow="After each market close" title="Today's brief"/);
});

test("LIVE14B-011 / LIVE14B-010: the funds page's count line names no plan; the tax table's head is 'Tax'", () => {
  assert.match(read("src/pages/money/MutualFundsPage.tsx"), /<p className="k-note">\{schemes\.length\} of \{view\.limit\} free schemes used\.<\/p>/);
  assert.match(read("src/pages/TaxReportPage.tsx"), /<FigureTable label="Where the tax comes from" header="Tax" valueHeader="Amount"/);
});

test("LIVE14B-015: the breadth card after the close says its day twice at most (eyebrow and column), no 'Prices as of' foot", () => {
  const card = read("src/components/BreadthCard.tsx");
  assert.doesNotMatch(card, /<AsOf parts=\{\[\["Prices", d\.as_of\]\]\}/);
});
