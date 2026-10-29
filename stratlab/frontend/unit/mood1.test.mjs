// MOOD-1 (owner, 29 Oct): the Market pulse's mood as tables. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MOOD-1: figures are written one way: a true minus, grouped the Indian way, crore with a sign", async () => {
  const m = await import("../src/lib/pulseMood.ts");
  assert.equal(m.whole(1234567), "12,34,567");
  assert.equal(m.signedWhole(-105), "−105");
  assert.equal(m.signedWhole(0), "0");
  assert.equal(m.signedPts(1.4), "+1.4 pts");
  assert.equal(m.signedPts(-0.6), "−0.6 pts");
  assert.equal(m.signedPts(0.04), "0.0 pts");
  assert.equal(m.crore(-2800), "−₹2,800 cr");
  assert.equal(m.crore(356900), "+₹3,56,900 cr");
  assert.equal(m.signedPoints(55.34), "+55.3");
  assert.equal(m.signedPoints(-32), "−32.0");
  assert.equal(m.riskLevel({ label: "US 10-year yield", tag: "yield", price: 4.05 }), "4.05%");
  assert.equal(m.riskLevel({ label: "USD/INR", tag: "fx", price: 83.1234 }), "₹83.12");
  assert.equal(m.riskLevel({ label: "Gold", tag: "gold", price: 2650 }), "$2,650");
});

test("MOOD-1: two tables sit side by side only when they have as many rows; the movers are one list by points", async () => {
  const m = await import("../src/lib/pulseMood.ts");
  assert.equal(m.pairable(6, 6), true);
  assert.equal(m.pairable(6, 5), false);
  assert.equal(m.pairable(0, 0), false);
  const rows = m.moverRows({ index: "NIFTY 50", of: 50, note: "", adding: [{ symbol: "A", change_pct: 1, points: 40 }, { symbol: "C", change_pct: 1, points: 10 }], taking: [{ symbol: "B", change_pct: -2, points: -30 }] });
  assert.deepEqual(rows.map((r) => r.symbol), ["A", "C", "B"]);
  assert.equal(m.movedBy([{ symbol: "X", name: "ICICI Bank", change_pct: 1.05 }, { symbol: "H", change_pct: -1.19 }], (v) => `${v}%`), "ICICI Bank 1.05%, H -1.19%");
});

test("MOOD-1: the headlines the main story counts are the ones marked, and the sector count is the table's own", async () => {
  const m = await import("../src/lib/pulseMood.ts");
  const story = { label: "crude oil prices", n: 2, of: 3, indices: [0, 2], headlines: ["Crude oil climbs", "TCS profit up", "Oil prices surge"] };
  assert.equal(m.storyOf(story, "Crude oil climbs"), "crude oil prices");
  assert.equal(m.storyOf(story, "TCS profit up"), null);
  assert.equal(m.storyOf(null, "x"), null);
  assert.equal(m.sectorCount({ rows: [], up: 15, down: 1, unchanged: 0, of: 16, leader: "", laggard: "" }), "15 of 16 sector indices rose, 1 fell");
});

test("MOOD-1: every block of the pulse that shows figures is a table; prose stays prose", () => {
  const t = read("src/pages/PulseMood.tsx"), p = read("src/pages/Research.tsx");
  for (const label of ["Breadth of ", "Sector indices, best first", "Companies that moved the ", "FII and DII net buying, last five days", "Volatility, currencies and rates",
    "Other markets", "Results, IPOs and events this week", "Companies named in today's headlines", "Money and markets in the headlines", "Themes in play", "Today's headlines", "Index levels"]) {
    assert.ok(t.includes(`label="${label}`) || t.includes(`label={\`${label}`) || t.includes(label), label);
  }
  assert.doesNotMatch(p, /className="inv-themes"|className="inv-rows"/);          // the tiles and rows lists of the old page
  assert.match(t, /export function Pair[\s\S]*pairable\(nl, nr\)/);
  assert.doesNotMatch(t, /and \d+ more|\.\.\. and/);                              // no "and N more" truncation
});

test("MOOD-1: breadth's figures are one table: the day, the day before, the change and the average of the last 20 days", async () => {
  const { avg20, measureRows, figure, change, liveRows } = await import("../src/lib/breadthTable.ts");
  assert.equal(avg20([1, 2, 3]), null);                                             // under 5 days: no average
  assert.equal(avg20([1, 2, 3, 4, 5, null]), 3);
  assert.equal(avg20(Array.from({ length: 30 }, (_, i) => i + 1)), 20.5);           // the last 20 of 30: 11..30
  const f = (value, prev) => ({ value, prev, change: value != null && prev != null ? +(value - prev).toFixed(3) : null });
  const t = { day: "2026-10-28", prev_day: "2026-10-27", adv: f(254, 359), dec: f(244, 141), unch: f(2, 0), ad_ratio: f(1.04, 2.55), pct20: f(26.6, 25), pct50: f(19.2, 17.8), pct200: f(33.2, 33.8),
    highs: f(7, 6), lows: f(24, 24), up4: f(22, 59), down4: f(12, 7), stage2: f(23.3, 23.1), mcclellan: f(1.3, -7.3), summation: f(2688.6, 2687.3), thrust: f(1, 1), trin: f(0.93, 0.8), stocks: f(500, 500) };
  const rows = measureRows(t, null);
  assert.deepEqual(rows.map((r) => r.key), ["ad", "ratio", "p20", "p50", "p200", "hl", "mv", "s2", "mc", "su", "tr"]);
  assert.ok(rows.every((r) => r.means.length > 10), "each measure says what it means");
  assert.deepEqual(rows[0].parts.map((p) => [p.now, p.before, p.change]), [[254, 359, -105], [244, 141, 103]]);
  assert.equal(rows[0].parts.every((p) => p.avg === null), true);                   // no history (the Free plan): no average column
  const h = { adv: Array(25).fill(200), dec: Array(25).fill(100), ad_ratio: Array(25).fill(2), pct20: [], pct50: Array(25).fill(30), pct200: [], highs: [], lows: [], up4: [], down4: [], stage2: [], mcclellan: [], summation: [], trin: [] };
  assert.equal(measureRows(t, h)[0].parts[0].avg, 200);
  assert.equal(measureRows(t, h)[3].parts[0].avg, 30);
  assert.equal(figure(2688.6, "num"), "2,688.6");
  assert.equal(figure(0.93, "ratio"), "0.93");
  assert.equal(figure(19.2, "pct"), "19.2%");
  assert.equal(change(-105, "count"), "−105");
  assert.equal(change(1.4, "pct"), "+1.4 pts");
  assert.equal(change(-0.6, "pct"), "−0.6 pts");
  assert.equal(change(0.13, "ratio"), "+0.13");
  assert.equal(change(0.04, "pct"), "no change");
  const live = liveRows({ adv: 300, dec: 180, pct20: 40, pct50: 30.5, pct200: 35, idx: 22100.5 }, t, "NIFTY 500", 22000);
  assert.deepEqual(live.map((r) => r.key), ["ad", "p20", "p50", "p200", "idx"]);
  assert.equal(live[2].parts[0].change, 30.5 - 19.2);
  assert.equal(live[4].parts[0].change, 100.5);
});

test("MOOD-1: the alert is a bell on the 50-day row, not a card; it says the level when one is set", () => {
  const page = read("src/pages/BreadthPage.tsx"), a = read("src/components/BreadthAlert.tsx");
  assert.doesNotMatch(page, /function AlertBox|<AlertBox|Alert on the share above the 50-day average" \/>/);
  assert.match(page, /r\.key === "p50" && !locked \? <BreadthAlertButton group=\{group\} \/>/);
  assert.match(a, /here\.length \? `Alert at \$\{here\.map\(\(a\) => `\$\{a\.level\}%`\)\.join\(", "\)\}` : "Alert me"/);
  assert.match(a, /breadthApi\.addAlert\(group\.id, n\)/);                           // the same alert as before: the same API
  assert.match(a, /<Dialog title="Alert on the share above the 50-day average"/);
});

test("MOOD-1: a remembered custom range can be cleared, and the owner's set of ranges is in the one range control", () => {
  const chip = read("src/components/kit/ChipBar.tsx");
  assert.match(chip, /aria-label=\{`Remove \$\{o\.label\}`\}/);
  assert.match(chip, /if \(v === value && options\.length\) onChange\(options\[options\.length - 1\]\.value\)/);
  assert.match(read("src/lib/period.ts"), /"1w": 7, "1m": 30, "3m": 91, "6m": 182, "1y": 365, "2y": 730, "3y": 1095, "5y": 1826/);
});

test("MOOD-1: the rotation's four run-on sentences are a table of every one, with the counts in its filter and no truncation", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(s, /and \$\{xs\.length - n\} more|rot-read|const few = /);
  assert.match(s, /<ChipBar label="Show quadrant" value=\{quad\}/);
  assert.match(s, /\.\.\.QUADRANTS\.map\(\(x\) => \(\{ value: x\.id, label: `\$\{x\.name\} \$\{counts\[x\.id\]\}` \}\)\)/);
  assert.match(s, /Entered Leading/);
  assert.doesNotMatch(s, /<Badge[^>]*>New</);                                       // no "New" tag anywhere (owner's rule): the mark says what it is
  assert.match(s, /header: "1W"[\s\S]*"1M"[\s\S]*"3M"|\{ w1: "1W", m1: "1M", m3: "3M" \}/);
  assert.match(s, /sort=\{\{ key: sort\?\.key \?\? "", desc: sort\?\.desc \?\? false, onSort \}\}/);
  // the table comes before the chart
  assert.ok(s.indexOf('testId="rot-table"') < s.indexOf("<ChartFrame title={`${out.name} vs ${out.benchmark}`}"));
});
