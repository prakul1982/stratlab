// Re-score of 26 Oct 2026, Money data and Tax (RC2B): the frontend's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC2B-001: My space's net worth tile follows the page's rule: no change from a snapshot valued another way, and it says why", async () => {
  const home = read("src/pages/MineHome.tsx");
  assert.match(home, /netWorthDelta\(v\.totals\.net, v\.totals\.partial, hist, undefined, v\.valuation\)/);
  assert.match(home, /restatedNote\(hist, v\.valuation,/);
  assert.match(home, /m\?: number/);
  const { netWorthDelta, restatedNote } = await import("../src/lib/networth.ts");
  const hist = [{ d: "2026-10-23", net: 4_300_000 }, { d: "2026-10-25", net: 2_200_000, m: 1 }];
  // the snapshots are of the old way; the live total is valued the new way (2): no change, and the note says so
  assert.equal(netWorthDelta(410_000, null, hist.map((h) => ({ ...h, m: 1 })), "2026-10-26", 2), null);
  assert.match(restatedNote(hist.map((h) => ({ ...h, m: 1 })), 2, (d) => d, "2026-10-26"), /valued a different way/);
});

test("RC2B-020, RC2B-021: the net worth chart waits for a third snapshot, and the add modal's way back is 'Back'", () => {
  const page = read("src/pages/money/NetWorthPage.tsx");
  assert.match(page, /view\.history_allowed && whole\.length >= 3 && \(/);
  assert.match(page, /whole\.length < 3 && snapsList/);
  assert.match(page, />← Back<\/button>/);
  assert.doesNotMatch(page, /← Something else/);
  const home = read("src/pages/MineHome.tsx");
  assert.match(home, /so far; the chart starts at the third/);
});

test("RC2B-002: no Money page opens on a year another page remembered", async () => {
  const fy = read("src/lib/fy.ts");
  assert.doesNotMatch(fy, /localStorage|savedFy|rememberFy/);
  assert.doesNotMatch(read("src/lib/useFy.ts"), /rememberFy|useEffect/);
  for (const f of ["src/pages/TaxReportPage.tsx", "src/pages/money/TaxToolsPage.tsx", "src/pages/money/ItrExportPage.tsx", "src/pages/money/UsTaxPage.tsx",
    "src/pages/money/MutualFundsPage.tsx", "src/pages/SpaceHomes.tsx"]) assert.doesNotMatch(read(f), /rememberFy|savedFy/, f);
  const { pickFy, openFy } = await import("../src/lib/fy.ts");
  const years = [2026, 2025, 2024];
  // 26 Oct 2026: the tax is in FY 2025-26 (the year being filed); FY 2024-25 was picked elsewhere and is not carried here
  assert.deepEqual(openFy(years, 2026, (y) => y === 2025), { fy: 2025, from: null });
  assert.deepEqual(openFy(years, 2026, (y) => y === 2024), { fy: 2024, from: 2025 });          // the filing year is empty: the latest with data
  assert.equal(pickFy(years, 2026, () => true), 2025);
  assert.deepEqual(openFy(years, 2026, () => true, null, 2024), { fy: 2024, from: null });     // a link's year still wins
});

test("RC2B-003, RC2B-004: no late fee for a year with no return; one headline figure; the rounded line only when it differs", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /payable\.return_needed === false/);
  assert.match(src, /No return is needed for \{y\.label\}: total income/);
  assert.match(src, /plus 234A, 234B and 234C\{payable\.fee_234f \? " and the 234F late fee" : ""\}/);
  assert.match(src, /const rounds = t\.rounded != null && t\.rounded\.tax !== Math\.round\(t\.total\);/);
  assert.doesNotMatch(src, /value=\{<a className="link" href="#tax-total">\{inr\(t\.total\)\}<\/a>\}/);
  const tools = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(tools, /data-testid="payable-no-return"/);
  assert.match(tools, /Not counted in the <Link/);
});

test("RC2B-006, RC2B-007, RC2B-035: the SIP result says a live price and a demerger", () => {
  const src = read("src/pages/money/SipTestPage.tsx");
  assert.match(src, /res\?\.last_live \? "Last price" : "Last close"/);
  assert.match(src, /data-testid="sip-note"/);
  assert.match(src, /last_live\?: boolean; notes\?: string\[\]/);
});

test("RC2B-009: a Kite file is 'your Zerodha Kite file', the login is the login", async () => {
  const { sourceWords } = await import("../src/lib/format.ts");
  assert.equal(sourceWords("Zerodha Kite"), "your Zerodha login");
  assert.equal(sourceWords("Zerodha Kite file"), "your Zerodha Kite file");
  assert.equal(sourceWords("Groww"), "your Groww file");
});

test("RC2B-013, RC2B-015: the US page adds no month-first line to ISO dates, and a refused file stays on the page", () => {
  const src = read("src/pages/money/UsTaxPage.tsx");
  assert.doesNotMatch(src, /read month first, the US way/);
  assert.match(src, /data-testid="us-upload-error"/);
  assert.match(src, /setUploadError\(\(e as \{ message\?: string \}\)\?\.message/);
});

test("RC2B-017, RC2B-048: the ITR page says the lock once and the year is not a third 'Financial year'", () => {
  const src = read("src/pages/money/ItrExportPage.tsx");
  assert.doesNotMatch(src, /The downloads are on the \{v\.plan\} plan\./);
  assert.match(src, /s\.label !== "Financial year"/);
  assert.match(src, /const words = /);
});

test("RC2B-018: a saved amount is written 20,00,000 in its box", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /toLocaleString\("en-IN", \{ maximumFractionDigits: 2 \}\)/);
  assert.match(src, /useState\(v\.saved && v\.other \? grouped\(v\.other\) : ""\)/);
  assert.match(src, /onBlur=\{\(\) => setOther\(regroup\)\}/);
});

test("RC2B-022: the funds page counts transactions apart from the stamp duty and tax lines", () => {
  const src = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(src, /view\.txns - \(view\.charge_lines \?\? 0\)/);
  assert.match(src, /stamp duty or tax lines/);
});

test("RC2B-023: Holdings and the tax report no longer contradict each other about US stocks", async () => {
  const hold = read("src/pages/HoldingsPage.tsx");
  assert.doesNotMatch(hold, /aren't part of the tax report/);
  assert.match(hold, /Sales of US stocks come from the trades on the <Link/);
  const { usSharesNote } = await import("../src/lib/usGains.ts");
  assert.match(usSharesNote(1, 2, (v) => `₹${v}`), /^US shares, kept apart from these totals/);
  assert.match(read("src/pages/TaxReportPage.tsx"), /Their tax is added in the year's total tax estimate/);
});

test("RC2B-024: the floating rate bond is a row of the small savings table", () => {
  const src = read("src/pages/money/RatesPage.tsx");
  assert.match(src, /\[\.\.\.d\.small_savings\.rows, \.\.\.d\.bonds\]/);
  assert.doesNotMatch(src, /label="Bonds"/);
});

test("RC2B-040, RC2B-041, RC2B-043, RC2B-044: the cards of Money home and the calendar end together, and the add forms use the row", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /className="grid2 space-panels even">\s*<HoldingsSummary \/>/);
  const css = read("src/styles.css");
  assert.match(css, /\.mc-grid \{ align-items: stretch; \}/);
  assert.match(css, /\.us-add > \.k-form \{ grid-template-columns: repeat\(6, minmax\(0, 1fr\)\); \}/);
  assert.match(css, /\.hold-add > \.k-form \{ grid-template-columns: minmax\(0, 2fr\) repeat\(2, minmax\(0, 1fr\)\); \}/);
  assert.match(read("src/pages/money/UsTaxPage.tsx"), /aria-label="Add a trade" className="us-add"/);
  assert.match(read("src/pages/HoldingsPage.tsx"), /<div className="hold-add"><FormGrid/);
});

test("RC2B-045, RC2B-046: Holdings dividends don't repeat the tile's label as a heading", () => {
  const src = read("src/components/HoldingsActions.tsx");
  assert.match(src, /Paid in the last 12 months, by company/);
  assert.equal((src.match(/Last 12 months \(estimated\)/g) ?? []).length, 1);
});
