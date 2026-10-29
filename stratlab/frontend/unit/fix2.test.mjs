// FIX-2 (29 Oct 2026): the one range control, and what the reviewed pages now read.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const weekdays = (from, n) => { const out = []; const d = new Date(`${from}T00:00:00Z`); while (out.length < n) { if (d.getUTCDay() % 6) out.push(d.toISOString().slice(0, 10)); d.setUTCDate(d.getUTCDate() + 1); } return out; };

test("O4: only the chips the data reaches, never two that show the same stretch", async () => {
  const { offeredRanges } = await import("../src/lib/range.ts");
  const v = (days) => offeredRanges(days).map((o) => o.value);
  assert.deepEqual(v(weekdays("2026-10-01", 2)), []);                                      // two points: nothing to cut
  assert.deepEqual(v(weekdays("2026-09-01", 22)), ["1w", "all"]);                         // a month: 1W, then everything (no 1M look-alike of All)
  const year = weekdays("2025-10-28", 262);                                                   // a year of days to 28 Oct 2026
  assert.deepEqual(v(year), ["1w", "1m", "3m", "6m", "ytd", "all"]);                       // 1Y starts at the first point: it is All
  const five = weekdays("2021-11-01", 1300);                                                  // about five years
  const got = v(five);
  assert.deepEqual(got.filter((x) => x !== "ytd"), ["1w", "1m", "3m", "6m", "1y", "3y", "all"]);   // 5Y reaches the first point: All
  assert.ok(got.indexOf("ytd") > got.indexOf("6m") && got.indexOf("ytd") < got.indexOf("1y"));
  assert.equal(new Set(got).size, got.length);
  const long = weekdays("2018-01-01", 2200);
  assert.ok(v(long).includes("5y") && v(long).includes("3y"));
});

test("O4: a range starts where it says, counted back from the last point, the lengths being lib/period.ts's", async () => {
  const { rangeFrom, rangeStart, toMs } = await import("../src/lib/range.ts");
  const days = ["2026-01-29", "2026-01-30", "2026-02-27", "2026-03-31", "2026-04-30", "2026-05-29", "2026-06-30", "2026-09-30", "2026-10-28"];
  assert.equal(days[rangeFrom(days, "1w")], "2026-10-28");                                // nothing in the week before but the last point's own
  assert.equal(days[rangeFrom(days, "1m")], "2026-09-30");                                // 28 Sep onwards
  assert.equal(days[rangeFrom(days, "3m")], "2026-09-30");                                // 28 Jul onwards (nothing between 30 Jun and 30 Sep)
  assert.equal(days[rangeFrom(days, "ytd")], "2026-01-29");                               // from 1 Jan
  assert.equal(days[rangeFrom(days, "6m")], "2026-04-30");                                // from 28 Apr
  assert.equal(rangeFrom(days, "all"), 0);
  assert.equal(new Date(rangeStart("1m", toMs("2026-03-31"))).toISOString().slice(0, 10), "2026-03-01");     // 1m is 30 days (lib/period.ts): 31 Mar back is 1 Mar
  assert.equal(new Date(rangeStart("18 months", toMs("2026-10-28"))).toISOString().slice(0, 10), "2025-04-28");
  assert.equal(new Date(rangeStart("45 days", toMs("2026-10-28"))).toISOString().slice(0, 10), "2026-09-13");
  assert.equal(rangeStart("junk", toMs("2026-10-28")), null);
});

test("O4: a custom range is kept only while it cuts something, and a saved choice is remembered per chart", async () => {
  const store = new Map();
  globalThis.localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  const { offeredRanges, saveRange, savedRange, startRange, isRange, rangeLabel, spanWords } = await import("../src/lib/range.ts");
  const days = weekdays("2023-11-01", 800);
  const opts = offeredRanges(days);
  assert.equal(startRange("a", days, opts), "all");                                         // nothing saved: all
  assert.equal(startRange("a", days, opts, "1y"), "1y");                                    // a page's own first view
  saveRange("a", "6m"); saveRange("b", "3y");
  assert.equal(startRange("a", days, opts), "6m");
  assert.equal(startRange("b", days, opts), "3y");
  assert.equal(startRange("c", days, opts), "all");                                         // another chart is its own
  saveRange("a", "18 months");
  assert.equal(startRange("a", days, opts), "18 months");                                   // custom, and the data is longer than it
  saveRange("a", "20 years");
  assert.equal(startRange("a", days, opts), "all");                                         // custom, longer than the data: All
  saveRange("a", "5y");
  assert.equal(startRange("a", days, opts), "all");                                         // a chip this chart no longer offers
  assert.ok(isRange("45 days") && isRange("3m") && !isRange("45 fortnights") && !isRange(""));
  assert.equal(rangeLabel("1 years"), "1 year"); assert.equal(rangeLabel("18 months"), "18 months"); assert.equal(rangeLabel("ytd"), "YTD");
  assert.equal(spanWords(1500), "4.1 years"); assert.equal(spanWords(120), "4 months"); assert.equal(spanWords(40), "40 days");
  assert.equal(savedRange("zzz"), null);
  delete globalThis.localStorage;
});

test("O4: positioning cuts each series from its own last day", async () => {
  const { cutPoints } = await import("../src/lib/range.ts");
  const pts = weekdays("2026-01-05", 200).map((day) => ({ day, v: 1 }));
  assert.equal(cutPoints(pts, "all").length, 200);
  const three = cutPoints(pts, "3m");
  assert.ok(three.length > 55 && three.length < 70 && three[three.length - 1].day === pts[199].day);
});

test("O4: every history chart goes through the one component (no page keeps a range list of its own)", () => {
  for (const f of ["src/components/chart/XYChart.tsx", "src/components/kit/ChartFrame.tsx", "src/pages/MarginFundingPage.tsx", "src/pages/money/NetWorthPage.tsx",
    "src/pages/PositioningPage.tsx", "src/pages/trade/StockFuturesPage.tsx", "src/pages/StockLendingPage.tsx", "src/components/EtfGap.tsx"]) {
    assert.match(read(f), /RangeChips|useRange|offeredRanges/, f);
  }
  assert.doesNotMatch(read("src/pages/MarginFundingPage.tsx"), /rangesFor|RANGE_DAYS/);
  assert.doesNotMatch(read("src/pages/money/NetWorthPage.tsx"), /RANGE_DAYS/);
  assert.doesNotMatch(read("src/components/chart/XYChart.tsx"), /RANGE_PRESETS/);
});

test("O1: the ETF gap's summary line is of the days shown, and the long explanation is folded", async () => {
  const { gapSummary } = await import("../src/lib/etfGapMath.ts");
  const days = [{ day: "2026-10-01", gap: 1 }, { day: "2026-10-02", gap: null }, { day: "2026-10-05", gap: 3 }];
  assert.deepEqual(gapSummary(days), { days: 2, shown: 3, low: 1, high: 3, avg: 2, from: "2026-10-01", to: "2026-10-05" });
  assert.equal(gapSummary([{ day: "x", gap: null }]), null);
  const src = read("src/components/EtfGap.tsx");
  assert.match(src, /<Disclosure summary="How this is worked out">/);
  assert.doesNotMatch(src, /footer=\{<p className="k-note">\{d\.note\}/);
});

test("O7: the issue page's figures are worked out in the open (year ends, change, the objects' share, price to earnings)", async () => {
  const t = await import("../src/lib/ipoText.ts");
  assert.equal(t.yearKey("Mar 2026"), "2026-03");
  assert.equal(t.yearKey("March 31, 2026"), "2026-03");
  assert.equal(t.yearKey("Three months ended June 30, 2026"), null);
  assert.equal(Math.round(t.growthPct(803.63, 697.86) * 100) / 100, 15.16);
  assert.equal(t.growthPct(10, -5), null);                                             // a change from a loss is not a percentage
  assert.equal(t.growthPct(null, 5), null);
  assert.equal(t.freshCrore({ fresh_cr: 400 }), 400);
  assert.equal(t.freshCrore({ fresh: 17_000_000, high: 150 }), 255);
  assert.equal(t.freshCrore({ fresh: 17_000_000, price: 140, high: 150 }), 238);        // the issue price once there is one
  assert.equal(t.freshCrore({}), null);
  const rows = t.objectRows([{ label: "Repay borrowings", amount: 42.23 }, { label: "Working capital", amount: 74.92 }, { label: "General corporate purposes", amount: null }], 200);
  assert.deepEqual(rows.map((r) => r.n), [1, 2, 3]);
  assert.equal(Math.round(rows[0].share * 100) / 100, 21.12);
  assert.equal(rows[2].share, null);
  assert.equal(t.objectRows([{ label: "x", amount: 5 }], null)[0].share, null);          // no fresh issue size: no share
  assert.equal(t.priceToEarnings(150, 16.52), 9.08);
  assert.equal(t.priceToEarnings(150, -2), null);                                      // no price to earnings on a loss
  assert.equal(t.priceToEarnings(null, 5), null);
  const [head, rest] = t.firstAndRest([1, 2, 3, 4, 5, 6, 7], 5);
  assert.deepEqual([head.length, rest.length], [5, 2]);
  assert.equal(t.kpiText(21.55, "pct"), "21.55%");
  assert.equal(t.kpiText(0.05, "times"), "0.05×");
  assert.equal(t.kpiText(1570.07, "crore"), "1,570.07");
  assert.equal(t.kpiText(null, "crore"), "–");
  assert.equal(t.periodText("the three months ending June 30, 2026"), "3 months to June 30, 2026");
  assert.equal(t.periodText("Fiscal 2026"), "Fiscal 2026");
});

test("O7: every block of the issue page is a table, the risks have one fold, and the summary has one fold for the document's words", () => {
  const page = read("src/pages/IpoPage.tsx");
  assert.doesNotMatch(page, /<ul|<ol|<dl|<dt/);                                         // no lists of facts
  for (const id of ["ipo-terms", "ipo-bids", "ipo-listing", "ipo-objects", "ipo-promoters", "ipo-holding", "ipo-financials", "ipo-kpis", "ipo-peer-kpis", "ipo-peers", "ipo-risks", "ipo-summary", "ipo-docs"])
    assert.match(page, new RegExp(`testId="${id}"`), id);
  assert.equal((page.match(/<Disclosure summary="Show the document's words"/g) ?? []).length, 1);
  assert.equal((page.match(/<Disclosure summary=\{`Show the other/g) ?? []).length, 1);
  assert.match(page, /firstAndRest\(risks, 5\)/);
  assert.doesNotMatch(page, /Statements|ipo-sum-promoters|ipo-sum-risks/);              // the AI no longer writes the risks, the promoters or the objects
});

test("LIVE2-013: Free is priced in the money the paid cards are charged in", () => {
  const plans = read("src/pages/PlansPage.tsx"), land = read("src/pages/Login.tsx");
  assert.match(plans, /currency !== "INR" && chargedInRupees\(row, currency, per === "year" \? row\.yearly_charged_in : row\.charged_in\) \? "₹0" : money\(row, 0, currency\)/);
  assert.match(land, /p === "free" \? \(inRupees\("basic", year\) \? rupees\(p, year\)/);
});

test("LIVE2-014, 027, 033: no flat equity line for a session with no trades, the whole-market audit above the form, the dividends list asks again by itself", () => {
  assert.match(read("src/pages/PaperPage.tsx"), /curve\.length > 1 && span > 0 \?/);
  assert.match(read("src/pages/PaperPage.tsx"), /No trades yet: the account is still at the starting/);
  const q = read("src/pages/admin/QualitySection.tsx");
  assert.ok(q.indexOf("<MarketAuditPanel") < q.indexOf("<AuditPanel"), "the whole-market result first");
  assert.doesNotMatch(read("src/pages/admin/AuditPanel.tsx"), /Running · up to date/);
  const h = read("src/components/HoldingsActions.tsx");
  assert.match(h, /setTimeout\(\(\) => setAgain\(\(n\) => n \+ 1\), 30_000\)/);
  assert.doesNotMatch(h, /reload in a minute/);
});
