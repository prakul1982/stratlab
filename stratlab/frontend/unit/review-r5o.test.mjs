// Round 5, the owner's review on the live site (8 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { quoteAt } from "../src/lib/format.ts";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const IST = "Asia/Kolkata";

test("each watchlist price carries the time it was traded, in the market's zone (R5O-003)", () => {
  const now = new Date("2026-10-08T09:31:00Z");                      // 15:01 IST
  assert.equal(quoteAt("2026-10-08T15:01:12+05:30", IST, now), "15:01 IST");
  assert.equal(quoteAt("2026-10-07T15:29:59+05:30", IST, now), "7 Oct, 15:29 IST");   // a stale quote reads as stale
  assert.equal(quoteAt("2026-10-08", IST, now), "8 Oct");              // a daily candle: its day only
  assert.equal(quoteAt(null, IST, now), "");
  // both tabs show it, from the same quotes
  assert.match(read("src/pages/Research.tsx"), /quoteAt\(q\.at, marketTz\(region\)\)/);
  assert.match(read("src/pages/InvestorHome.tsx"), /quoteAt\(r\.price_at, marketTz\(region\)\)/);
});

test("an ETF badge never sets today's price against yesterday's NAV (R5O-005)", async () => {
  const { gapAtPrice } = await import("../src/lib/etfGapMath.ts");
  // 8 Oct 14:25 IST, Nifty -1.7%: NIFTYBEES at 254.15 against the 7 Oct NAV of 257.80 read "1.4% below"
  const row = { symbol: "NIFTYBEES", name: "Nippon India ETF Nifty 50 BeES", underlying: null, fund: "equity", fund_label: "Equity ETF",
    price: 254.15, price_at: "2026-10-08T14:25+05:30", inav: null, inav_gap: null, nav: 257.8026, nav_date: "2026-10-07",
    nav_gap: -0.08, nav_price: 257.60, nav_price_day: "2026-10-07", gap: -0.08, basis: "NAV", text: "NIFTYBEES closed 0.08% below its NAV on 7 Oct" };
  const today = gapAtPrice(row, 254.15, "2026-10-08");
  assert.equal(today.gap, -0.08);                      // the 7 Oct close's gap stands, not -1.42
  assert.equal(gapAtPrice(row, 254.15).gap, -0.08);    // a price of unknown day is never set against the NAV either
  assert.equal(gapAtPrice(row, 257.0, "2026-10-07").gap, -0.31);   // a 7 Oct price is
  const badge = read("src/components/EtfGap.tsx");
  assert.match(badge, /close` : ""\)/);
  assert.match(read("src/pages/EtfGapsPage.tsx"), /header: "Close vs NAV"/);
});

test("AAPL's page: no unsourced segment split, an insider net that matches its rows, US grouping (R5O-007)", async () => {
  const { signed, grouped } = await import("../src/lib/format.ts");
  assert.equal(signed(208772, 0, "US"), "+208,772");
  assert.equal(signed(-139005, 0, "US"), "−139,005");
  assert.equal(signed(-139005), "−1,39,005");                 // India keeps its grouping
  assert.equal(grouped(4753636, 0, "US"), "4,753,636");
  assert.equal(grouped(4753636), "47,53,636");
  const research = read("src/pages/Research.tsx");
  assert.match(research, /signed\(Math\.round\(v\), 0, region\)/);
  assert.match(research, /shares over the \{c\.insider\.rows\.length\} filing/);
  assert.doesNotMatch(research + read("src/components/Research.tsx"), /Revenue by segment|<Donut/);
});

test("TCS's key numbers: no scraped strengths and concerns, and a figure's note shows (R5O-011)", () => {
  const research = read("src/pages/Research.tsx");
  assert.doesNotMatch(research, /Strengths and concerns|c\.pros|c\.cons/);
  assert.match(read("src/components/Research.tsx"), /\{m\.label\}\{m\.note && <span className="k-sub-line">\{m\.note\}<\/span>\}/);
});

test("the screener starts with the largest companies (R5O-012)", () => {
  const screens = read("src/pages/Screens.tsx");
  assert.match(screens, /useState\("market_cap"\)/);
  assert.match(screens, /const \[desc, setDesc\] = useState\(true\)/);
  assert.doesNotMatch(screens, /the list is alphabetical/);
});

test("whole-number growth rates stay whole, and the compare page names each section (R5O-021)", async () => {
  const { metricText } = await import("../src/lib/researchFormat.ts");
  assert.equal(metricText({ label: "5Y", value: -12, unit: "%±", dp: 0 }, "INR"), "−12%");
  assert.equal(metricText({ label: "10Y", value: 6, unit: "%±", dp: 0 }, "INR"), "+6%");
  assert.equal(metricText({ label: "1Y", value: -31.42, unit: "%±" }, "INR"), "−31.4%");
  const research = read("src/pages/Research.tsx");
  assert.match(research, /label=\{`\$\{sec\.title\} for both companies`\}/);
  assert.match(research, /<span className="k-eyebrow">\{sec\.title\}<\/span>/);
});

test("the Money card's tax is the tax report's total, with the audit fact (R5O-022)", () => {
  const card = read("src/pages/SpaceHomes.tsx");
  assert.match(card, /year\?\.total\?\.available \? year\.total\.total/);
  assert.match(card, /Total tax estimate, \$\{year\?\.label/);
  assert.match(card, /\{year\?\.audit && <p className="small">\{year\.audit\}<\/p>\}/);
  assert.doesNotMatch(card, /Capital gains tax, \$\{year/);
});

test("dates: quarter ends, the app's date format for an expiry, ticks on trading days (R5O-026)", async () => {
  const { isQuarterEnd } = await import("../src/components/NamedHolders.tsx").catch(() => ({}));
  const named = read("src/components/NamedHolders.tsx");
  assert.match(named, /\["03-31", "06-30", "09-30", "12-31"\]\.includes\(iso\.slice\(5, 10\)\)/);
  assert.match(named, /isQuarterEnd\(v\.quarter\) \? "Quarter to" : "As of"/);
  if (isQuarterEnd) { assert.equal(isQuarterEnd("2026-09-30"), true); assert.equal(isQuarterEnd("2026-10-05"), false); }
  assert.match(read("src/pages/OptionsSession.tsx"), /expiry \$\{fmtDate\(snap\.expiry, \{ weekday: true \}\)\}/);
  const { tickOnPoint } = await import("../src/lib/chartFormat.ts");
  const ms = (d) => Date.parse(`${d}T00:00:00+05:30`);
  const IST = "Asia/Kolkata";
  // 2 Oct 2026 (Gandhi Jayanti) and 3 Oct (Saturday) have no point: their ticks land on Monday 5 Oct's and say so
  assert.equal(tickOnPoint({ t: ms("2026-10-02"), label: "2 Oct" }, ms("2026-10-05"), false, IST), "5 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-03"), label: "3 Oct" }, ms("2026-10-05"), false, IST), "5 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-07"), label: "7 Oct" }, ms("2026-10-07"), false, IST), "7 Oct");
  assert.equal(tickOnPoint({ t: ms("2026-10-01"), label: "Oct" }, ms("2026-10-01"), false, IST), "Oct");
});

test("holdings name what is left out of the totals and of Today (R5O-004)", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /Not in these totals: \{t\.no_cost\.symbols\.join/);
  assert.match(page, /last change is left out of Today/);
  assert.match(page, /r\.session !== t\.session/);
  assert.match(page, /view\.us && view\.us\.count > 0/);
});
