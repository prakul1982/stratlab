// Review DC (24 Oct 2026): the Trade market-data pages — positioning and the option chain, stock futures, the closing
// auction, market events, F&O changes and Trade home. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("DC-003: the chain says whether its open interest is the exchange's end-of-day figure or an intraday recording", async () => {
  const { oiBasis, historyBasis, chainWords, chainWithTime } = await import("../src/lib/positioning.ts");
  assert.match(oiBasis({ source: "recorded", final: true, as_of: "2026-10-23T18:00:00+05:30" }), /exchange's end-of-day figures/);
  assert.match(oiBasis({ source: "recorded", final: false, as_of: "2026-10-23T15:41:00+05:30" }), /^An intraday recording .*can differ from them/);
  assert.equal(oiBasis({ source: "live", final: false }), "");
  assert.equal(chainWords({ source: "recorded", final: true }), "the exchange's end-of-day chain");
  assert.match(chainWithTime({ source: "recorded", final: true, as_of: "2026-10-23T18:00:00+05:30" }, "23 Oct, 18:00 IST"), /^the exchange's end-of-day chain, 23 Oct/);
  assert.doesNotMatch(chainWithTime({ source: "recorded", final: true, as_of: "2026-10-23T18:00:00+05:30" }, "23 Oct, 18:00 IST"), /18:00/);
  assert.equal(historyBasis([{ final: true }, { final: true }]), "Every day uses the exchange's end-of-day open interest.");
  assert.match(historyBasis([{ final: true }, { final: false }, { final: false }]), /^1 of 3 days .* the other 2 use StratLab's intraday recording/);
  const page = read("src/pages/PositioningPage.tsx");
  assert.match(page, /data-testid="chain-basis"/);
  assert.match(page, /historyBasis\(chain\)/);
});

test("DB-012: max pain is labelled near the money; DC-008: the IV tile counts down the days it needs", async () => {
  const { chainCounts, ivWait } = await import("../src/lib/positioning.ts");
  assert.match(chainCounts({ rows: [], near_strikes: 15, window_strikes: 31 }).maxPain, /^near-the-money max pain: over the 31 strikes/);
  assert.match(read("src/pages/PositioningPage.tsx"), /label="Max pain, near the money"/);
  assert.equal(ivWait(17, 20), "Needs 3 more recorded days");
  assert.equal(ivWait(19, 20), "Needs 1 more recorded day");
  assert.doesNotMatch(read("src/pages/PositioningPage.tsx"), /needed so far/);
});

test("DC-005: a change in a long or short count is shown in the text colour, not green or red; DC-006: Prop desks", async () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.match(page, /function Chg\(\{ v \}: \{ v: number \| null \}\) \{\n {2}return v == null \? null : <span className="k-sub-line k-muted num" data-testid="pos-chg">\{signed\(v\)\}<\/span>;/);
  const { PARTICIPANTS } = await import("../src/lib/positioning.ts");
  assert.deepEqual(PARTICIPANTS.find(([id]) => id === "pro"), ["pro", "Prop desks"]);
});

test("DC-007: the FII long-share chart is drawn once, under History; the cash axis is in ₹ crore", () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.doesNotMatch(page, /<FiiTrend/);
  assert.match(page, /axisFormat=\{\(v\) => crore\(v\)\}/);
});

test("DC-004, DB-011: the chain is in contracts once the lot is known", async () => {
  const { unitLine } = await import("../src/lib/positioning.ts");
  assert.match(unitLine({ unit: "lots", lot: 65 }), /lots of 65 shares/);
});

test("DC-009: stock futures page through 50 rows at a time, open interest in lots, the days to expiry said once", () => {
  const src = read("src/pages/trade/StockFuturesPage.tsx");
  assert.match(src, /export const SF_PAGE = 50;/);
  assert.match(src, /const shown = rows\.slice\(0, limit\);/);
  assert.match(src, /data-testid="sf-more"/);
  assert.match(src, /export const oiLots = \(r: Pick<FutRow, "oi" \| "lot">\) => \(r\.oi != null && r\.lot \? Math\.round\(r\.oi \/ r\.lot\) : null\);/);
  assert.match(src, /f !== "roll" \|\| \(count\(f\) > 0 && count\(f\) < \(t\?\.rows\.length \?\? 0\)\)/);   // a chip that filters nothing is left out
  assert.match(src, /r\.td != null && !same \? `\$\{r\.td\}d to expiry`/);
  assert.match(src, /data-testid="sf-expiry"/);
});

test("DC-010, DC-011, DC-012: the closing auction's numbers in one form, empty columns left out, the three counts add up", async () => {
  const { qtyExact, aboveBelow, anyValue } = await import("../src/lib/closingAuction.ts");
  assert.equal(qtyExact(190000), "1,90,000");
  assert.equal(qtyExact(14105), "14,105");
  assert.equal(qtyExact(null), "–");
  assert.equal(aboveBelow({ stocks: 213, up: 181, down: 28 }), "181 above · 4 unchanged · 28 below");
  assert.equal(anyValue([{ x: 0 }, { x: 0 }], (r) => r.x, false), false);
  assert.equal(anyValue([{ x: null }, { x: 3 }], (r) => r.x), true);
  const page = read("src/pages/trade/ClosingAuctionPage.tsx");
  assert.match(page, /title=\{v\.trading_day \? "Today's timetable" : "The auction's timetable, each trading day"\}/);
  assert.match(page, /\{LIVE_PHASES\.includes\(v\.phase\) && <Timeline v=\{v\} \/>\}\n {10}<Stocks v=\{v\} \/>/);
  assert.doesNotMatch(page, /More F&O stocks in the closing auction/);           // one table, not two of different widths
  assert.match(page, /Kept from \{asOf\(h\.days\[h\.days\.length - 1\]\.day\)\}/);
});

test("DC-013: a failed source is said on the events page, and a notice not read into stocks is still listed", async () => {
  // the module reads the page's address when loaded, so its source is checked here
  const lib = read("src/lib/marketEvents.ts");
  assert.match(lib, /const bad = sources\.filter\(\(s\) => s\.failed\);\n {2}if \(!bad\.length\) return null;/);
  assert.match(lib, /couldn't be read at the last check, so its newest dates and figures may be missing here\./);
  const page = read("src/pages/trade/EventsPage.tsx");
  assert.match(page, /data-testid="ev-failed"/);
  assert.match(page, /testId="ev-index-unread"/);
});

test("DC-015: the events page promises figures only where it reads them", () => {
  assert.doesNotMatch(read("src/pages/trade/EventsPage.tsx"), /with the published figure once it is out\./);
  assert.doesNotMatch(read("src/lib/navGroups.ts"), /published figure once it is out/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /the US reports as dates with a link/);
});

test("DC-016: the list opens at today, a day's kind is in words, and a kind with no event says so", () => {
  const cal = read("src/components/kit/Calendar.tsx");
  assert.match(cal, /data-testid="cal-today"/);
  assert.match(cal, /mark\.current\?\.scrollIntoView\?\.\(\{ block: "start" \}\)/);
  assert.match(cal, /className="k-cal-tag"/);
  assert.match(read("src/pages/trade/EventsPage.tsx"), /none\(k\) \? `\$\{v\.kinds\[k\]\} \(none yet\)`/);
});

test("DC-017 to DC-021: F&O changes have a name-change kind, the old symbol and a warning when a source failed", async () => {
  const page = read("src/pages/trade/FoChangesPage.tsx");
  assert.match(page, /\["rename", "Name changes"\]/);
  assert.match(page, /rename: "Name change"/);
  assert.match(page, /\{e\.was_symbol && <span className="k-note">was \{e\.was_symbol\}<\/span>\}/);
  assert.match(page, /data-testid="fo-failed"/);
  assert.match(read("src/lib/foChanges.ts"), /export type FoKind = "exit" \| "entry" \| "lot" \| "rename" \| "expiry" \| "circular";/);
});

test("DC-001: Trade home shows VIX, the FIIs' cash net, the next expiry and the F&O ban count, each linking to its page", () => {
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /<MarketStrip \/>/);
  for (const id of ["vix", "fii", "expiry", "ban"]) assert.match(home, new RegExp(`id: "${id}", to: "/trade/`));
  assert.match(home, /aria-label="Market today" data-testid="trade-market"/);
});
