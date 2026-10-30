// 25 Oct 2026, the deep audit of the Money data and maths (DG-001 .. DG-060, with DP2-001 .. DP2-040 on the same pages):
// holdings at their last close while live prices are off, a gain of some lines said to be of those lines, one gold price
// across pages, a net worth change that leaves out the money just added, the loan's next reset, and the plain words.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const H = await import("../src/lib/holdingsEdit.ts");
const NW = await import("../src/lib/networth.ts");
const { goldLine } = await import("../src/lib/gold.ts");
const { importLine } = await import("../src/lib/mfImport.ts");
const { numberProblem } = await import("../src/lib/validate.ts");
const { timeTicks } = await import("../src/lib/chartFormat.ts");
const day = (iso) => (iso === "2026-10-23" ? "Fri 23 Oct" : iso);

test("DP2-001, DG-002: holdings at the last close say so, and what is still at cost", () => {
  const rows = [{ value: 100, market: "IN" }, { value: null, market: "IN" }];
  assert.equal(H.priceNote(false, { day: "2026-10-23", close: 7, file: 0 }, rows, day),
    "Live prices are off right now, so these are at their last close: the exchange's close of Fri 23 Oct. 1 stock has no price, so it is shown at cost.");
  assert.equal(H.priceNote(false, { day: "2026-10-23", close: 4, file: 2 }, [{ value: 1 }], day),
    "Live prices are off right now, so these are at their last close: the exchange's close of Fri 23 Oct, and the close in your holdings file for 2.");
  assert.equal(H.priceNote(true, null, [{ value: 1 }], day), null);
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /priceNote\(view\.prices, view\.closes, rows/);
  assert.doesNotMatch(page, /Live prices are offline right now, so values are shown at cost/);
});

test("DG-001, DG-050: a gain of one line of nine is labelled as such, on Holdings and Money home", () => {
  assert.equal(H.pnlLabel("Unrealised P&L", { priced: 1, lines: 9 }), "Unrealised P&L · 1 of 9 lines");
  assert.equal(H.pnlLabel("Gain or loss", null), "Gain or loss");
  assert.match(read("src/pages/HoldingsPage.tsx"), /pnlLabel\("Unrealised P&L", t\.pnl_partial\)/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /pnlLabel\("Gain or loss", h\.totals\.pnl_partial\)/);
});

test("DG-005: Friday's move on a Sunday is the last session's, and the US line reads plainly", async () => {
  assert.equal(H.dayLabel("2026-10-23", "2026-10-25", day), "Last session (Fri 23 Oct)");
  assert.equal(H.dayLabel("2026-10-26", "2026-10-26", day), "Today");
  assert.match(read("src/lib/marketHours.ts"), /return `Today includes your US stocks \$\{live \? "live, moving until the US close" : "at their last close"\}/);
});

test("DG-060, DP2-040: one gold price in India, with the duty that is most of the gap to the world price", () => {
  const inr = (v) => `₹${Math.round(v).toLocaleString("en-IN")}`;
  const india = { per_10g: 142150, as_of: "2026-10-23T23:30+05:30", duty_pct: 15, duty_note: "India's import duty on gold is 15% (10% customs duty and 5% AIDC) since 13 May 2026, with 3% GST on top" };
  assert.equal(goldLine(india, 122336, inr), "₹1,42,150 per 10 g in India, the price Net worth uses. The world price at the dollar rate is ₹1,22,336; India's import duty on gold is 15% (10% customs duty and 5% AIDC) since 13 May 2026, with 3% GST on top.");
  assert.equal(goldLine(null, 122336, inr), "₹1,22,336 per 10 g at the world price and dollar rate, before India's import duty and GST");
  assert.match(read("src/pages/MineHome.tsx"), /api<IndiaGold>\("\/money\/gold"\)/);
});

test("DP2-006: a new FD isn't a gain; daily snapshots get a day axis; the snapshots list sits under the chart", () => {
  const hist = [{ d: "2026-10-23", net: 1000000 }, { d: "2026-10-25", net: 1107000, added: 107000 }];
  assert.deepEqual(NW.netWorthDelta(1107000, null, hist, "2026-10-25"), { change: 0, since: "2026-10-23", added: 107000 });
  assert.equal(NW.sinceNote({ since: "2026-10-23", added: 107000 }, day, (v) => `₹${v / 100000} lakh`), "since Fri 23 Oct, leaving out ₹1.07 lakh added in new or changed entries");
  const two = timeTicks(Date.UTC(2026, 9, 23), Date.UTC(2026, 9, 25), 10, "Asia/Kolkata", true);
  assert.ok(two.length > 0 && two.every((t) => !/^\d\d:\d\d$/.test(t.label)), JSON.stringify(two));
  const page = read("src/pages/money/NetWorthPage.tsx");
  assert.match(page, /\{snapsList\("nw-snaps"\)\}/);
  assert.match(page, /<DataTable label="Assets" columns=\{assetCols\} rows=\{view\.assets\} rowKey=\{\(r\) => r\.id\} stack \/>/);    // DP2-007
});

test("DP2-005, DG-014: 1e5 is typed in digits, a zero amount is refused, dates in the wrong order are said under the box", () => {
  assert.equal(numberProblem("1e5", { min: 0 }), "Type the number in digits, like 100000.");
  assert.equal(numberProblem("0", { min: 0, above: true, unit: "₹" }), "Enter more than ₹0.");
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /out\.maturity = "The maturity date has to be after the start date\."/);
});

test("DG-011 .. DG-013: the loan's rate now, points not percent, and what the next reset brings", () => {
  assert.equal(NW.nextResetNote({ benchmark: "repo", repo_now: 5.5, repo_at_reset: 5.25, next_expected: 7.5 }),
    " The repo rate is 5.50% now (5.25% at the last reset), so if it stays there the reset takes the expected rate to 7.50%.");
  assert.equal(NW.nextResetNote({ benchmark: "repo", repo_now: 5.5, repo_at_reset: 5.5, next_expected: 7.75 }), "");
  const card = read("src/pages/money/LoanCheck.tsx");
  assert.match(card, /\{Math\.abs\(c\.gap\.pts\) === 1 \? "point" : "points"\}/);
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /% a year now \(\$\{sanctioned\}% at the start\)/);
});

test("DP2-017, DG-026: the import says the stamp duty lines and the schemes kept apart", () => {
  assert.equal(importLine({ added: 133, duplicates: 0, schemes: 7, kept: 5, charges: 63 }), "70 transactions and 63 stamp duty or tax lines added, from 5 of the file's 7 schemes.");
  assert.equal(importLine({ added: 4, duplicates: 1, schemes: 2, kept: 2, charges: 0 }), "4 transactions added, 1 already saved (skipped), from 2 schemes.");
  const mf = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(mf, /data-testid="mf-short"/);                  // DG-021
  assert.match(mf, /data-testid="mf-elss-early"/);             // DG-024
  assert.match(mf, /equity: "Equity", debt: "Debt"/);          // DG-026: the narrow box
});

test("DG-030 .. DG-034, DP2-002: the SIP test's words, its start date and a result of other picks said", () => {
  const sip = read("src/pages/money/SipTestPage.tsx");
  assert.match(sip, /"Pick a stock or ETF first\."/);
  assert.match(sip, /Mutual fund SIPs, priced at each day's NAV, aren't tested here yet\./);
  assert.match(sip, /\{ key: "med", label: "Median XIRR"/);          // TABLE-SWEEP: a row of the spread table
  assert.match(sip, /<DateField label="Start" optional/);
  assert.match(sip, /data-testid="sip-stale"/);
  assert.match(read("src/components/InstrumentSearch.tsx"), /r\.etf \|\| r\.type === "ETF" \? "ETF"/);
});

test("DG-040 .. DG-042, DP2-015: rates are dated, compounding compared, every slab chip in view", () => {
  const rates = read("src/pages/money/RatesPage.tsx");
  assert.match(rates, /sub\(`as on \$\{dateOnly\(r\.as_of\)\}`\)/);
  assert.match(rates, /a year compounded/);
  assert.match(rates, /data-testid="tbill-note"/);
  assert.match(rates, /onChange=\{\(v\) => setPick\(v === "mine" \? "mine" : Number\(v\)\)\} wrap \/>/);
  assert.match(rates, /That is the highest slab, used until you pick yours above\./);
});

test("DP2-007: a stacked table's action cell is the card's width, so Edit and remove stay on a phone's card", () => {
  assert.match(read("src/styles.css"), /\.k-tbl-wrap\.stack \.k-table td\.k-act \{ text-align: right; width: auto; \}/);
});
