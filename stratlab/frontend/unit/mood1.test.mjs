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
