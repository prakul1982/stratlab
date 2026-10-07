// The chart's drawing maths: picking distances, rays, channels, Fibonacci levels, long and short position numbers
// (risk and reward, quantity from a risk amount), measures, magnet snapping, handle moves, undo and saved data.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import * as G from "../src/charts/price/drawGeo.ts";

const near = (a, b, eps = 1e-9) => assert.ok(Math.abs(a - b) <= eps, `${a} vs ${b}`);

test("distance to a segment, inside and past its ends", () => {
  near(G.distToSegment(5, 3, 0, 0, 10, 0), 3);
  near(G.distToSegment(-3, 4, 0, 0, 10, 0), 5);
  near(G.distToSegment(1, 1, 2, 2, 2, 2), Math.SQRT2);
});

test("a ray leaves the plot on the side it points to", () => {
  assert.deepEqual(G.rayEnd({ x: 10, y: 10 }, { x: 20, y: 20 }, 100), { x: 100, y: 100 });
  assert.deepEqual(G.rayEnd({ x: 50, y: 10 }, { x: 40, y: 20 }, 100), { x: 0, y: 60 });
  assert.deepEqual(G.rayEnd({ x: 10, y: 10 }, { x: 10, y: 30 }, 100), { x: 10, y: 30 });
});

test("a channel's second line is parallel through the third point", () => {
  near(G.channelShift({ x: 0, y: 100 }, { x: 100, y: 50 }, { x: 50, y: 90 }), 15);
  near(G.channelShift({ x: 0, y: 0 }, { x: 0, y: 50 }, { x: 5, y: 9 }), 0);
});

test("Fibonacci prices run from the second point (0) to the first (1)", () => {
  near(G.fibPrice(200, 100, 0), 100);
  near(G.fibPrice(200, 100, 1), 200);
  near(G.fibPrice(200, 100, 0.618), 161.8);
  near(G.fibPrice(100, 200, 0.5), 150);
  assert.deepEqual(G.FIB_LEVELS, [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1]);
  assert.equal(G.levelText(0.236), "0.236");
  assert.equal(G.levelText(1), "1");
});

test("a long position: risk, reward, ratio, percentages and the quantity for a risk amount", () => {
  const s = G.positionStats("long", 100, 95, 110, 1000);
  near(s.riskPerUnit, 5); near(s.rewardPerUnit, 10); near(s.ratio, 2);
  near(s.stopMove, -5); near(s.targetMove, 10); near(s.stopPct, -5); near(s.targetPct, 10);
  assert.equal(s.qty, 200); near(s.riskTotal, 1000); near(s.rewardTotal, 2000);
  assert.ok(s.stopSideOk && s.targetSideOk);
});

test("the quantity is whole units and never more than the risk amount allows", () => {
  const s = G.positionStats("long", 1849.3, 1830.1, 1900, 10000);       // 19.2 per unit -> 520.83 -> 520
  assert.equal(s.qty, 520);
  assert.ok(s.riskTotal <= 10000);
  assert.equal(G.positionStats("long", 100, 99.9, 101, 1).qty, 10);       // float error does not round an exact division down
  assert.equal(G.positionStats("long", 100, 95, 110, 4).qty, 0);          // smaller than one unit
  assert.equal(G.positionStats("long", 100, 95, 110, null).qty, null);
  assert.equal(G.positionStats("long", 100, 95, 110, 0).qty, null);
});

test("a short position mirrors it", () => {
  const s = G.positionStats("short", 100, 104, 90, 800);
  near(s.riskPerUnit, 4); near(s.rewardPerUnit, 10); near(s.ratio, 2.5);
  near(s.stopMove, 4); near(s.targetMove, -10); near(s.targetPct, -10);
  assert.equal(s.qty, 200);
});

test("a stop or target on the wrong side is flagged, and no ratio is made up", () => {
  const s = G.positionStats("long", 100, 105, 110, 1000);
  assert.equal(s.stopSideOk, false); assert.equal(s.ratio, null); assert.equal(s.qty, null);
  assert.equal(G.positionStats("long", 100, 95, 90, 1000).targetSideOk, false);
});

test("a new position's stop starts half the target's distance on the other side", () => {
  const p = G.buildPosition({ t: 1, p: 100 }, { t: 5, p: 110 });
  assert.deepEqual(p, [{ t: 1, p: 100 }, { t: 5, p: 110 }, { t: 5, p: 95 }]);
  const d = { id: "a", kind: "long", points: p, risk: 500 };
  assert.equal(G.statsOf(d).qty, 100);
  assert.equal(G.statsOf({ id: "b", kind: "trend", points: [{ t: 1, p: 1 }, { t: 2, p: 2 }] }), null);
});

test("measure: price change, percent, bars and time", () => {
  const s = G.measureStats({ t: 0, p: 200 }, { t: 3 * 86_400_000 + 4 * 3_600_000, p: 150 }, 3);
  near(s.move, -50); near(s.pct, -25); assert.equal(s.bars, 3);
  assert.equal(G.durationText(s.ms), "3d 4h");
  assert.equal(G.durationText(5.5 * 3_600_000), "5h 30m");
  assert.equal(G.durationText(12 * 60_000), "12m");
  assert.equal(G.durationText(-86_400_000), "−1d");
});

test("candles between two times, inside the data and beyond it", () => {
  const times = [0, 10, 20, 30, 40];
  assert.equal(G.barsBetween(times, 10, 30), 2);
  assert.equal(G.barsBetween(times, 15, 25), 1);
  assert.equal(G.barsBetween(times, 30, 10), -2);
  assert.equal(G.barsBetween(times, 40, 60), 2);                           // spaced like the last candles
  assert.equal(G.barsBetween(times, -10, 0), 1);
  near(G.fracIndex(times, 25), 2.5);
});

test("the magnet picks the nearest of open, high, low, close within reach", () => {
  const bar = { o: 100, h: 110, l: 95, c: 105 };
  const y = (p) => 200 - p;                                               // 1 px per price unit
  assert.equal(G.snapOhlc(bar, y(109), y, 10), 110);
  assert.equal(G.snapOhlc(bar, y(96), y, 10), 95);
  assert.equal(G.snapOhlc(bar, y(101), y, 10), 100);
  assert.equal(G.snapOhlc(bar, y(102.6), y, 10), 105);
  assert.equal(G.snapOhlc(bar, y(125), y, 10), null);                       // too far: left where it is
});

test("moving a handle: a position's entry, target and stop each move their own part", () => {
  const d = { id: "p", kind: "long", points: G.buildPosition({ t: 1, p: 100 }, { t: 5, p: 110 }) };
  assert.deepEqual(G.moveHandle(d, 2, { t: 99, p: 90 }).points[2], { t: 5, p: 90 });      // stop: price only
  const t = G.moveHandle(d, 1, { t: 8, p: 120 }).points;
  assert.deepEqual([t[1], t[2]], [{ t: 8, p: 120 }, { t: 8, p: 95 }]);                    // target: time and price, stop follows its time
  assert.deepEqual(G.moveHandle(d, 0, { t: 0, p: 101 }).points[0], { t: 0, p: 101 });
  assert.deepEqual(d.points[0], { t: 1, p: 100 });                                          // the original is untouched
  const line = { id: "l", kind: "trend", points: [{ t: 1, p: 1 }, { t: 2, p: 2 }] };
  assert.deepEqual(G.moveHandle(line, 1, { t: 9, p: 9 }).points, [{ t: 1, p: 1 }, { t: 9, p: 9 }]);
});

test("shifting a drawing moves every point", () => {
  const d = G.shiftDrawing({ id: "l", kind: "trend", points: [{ t: 1, p: 10 }, { t: 2, p: 20 }] }, 5, (p) => p + 1);
  assert.deepEqual(d.points, [{ t: 6, p: 11 }, { t: 7, p: 21 }]);
});

test("a brush stroke is thinned and keeps both ends", () => {
  const pts = Array.from({ length: 1000 }, (_, i) => ({ t: i, p: i }));
  const out = G.thinStroke(pts, 200);
  assert.equal(out.length, 200); assert.deepEqual(out[0], pts[0]); assert.deepEqual(out[199], pts[999]);
  assert.equal(G.thinStroke(pts.slice(0, 5), 200).length, 5);
});

test("undo and redo walk through states, and a new edit forgets the redo", () => {
  const h = new G.History(3);
  assert.equal(h.undo("a"), null);
  h.push("a"); h.push("b");                                               // a -> b -> c (current)
  assert.equal(h.undo("c"), "b"); assert.ok(h.canRedo);
  assert.equal(h.undo("b"), "a");
  assert.equal(h.redo("a"), "b");
  h.push("b");                                                            // a new edit
  assert.equal(h.canRedo, false);
  h.clear();
  h.push("x"); h.push("y"); h.push("z"); h.push("w");                     // the oldest drop past the limit of 3
  let n = 0; let cur = "v"; for (let r = h.undo(cur); r !== null; r = h.undo(cur)) { cur = r; n++; }
  assert.equal(n, 3);
});

test("saved drawings: unreadable ones are left out, good ones kept with their style", () => {
  const good = { id: "a1", kind: "long", points: [{ t: 1, p: 1 }, { t: 2, p: 2 }, { t: 2, p: 0.5 }], color: "green", dash: "dashed", locked: true, risk: 500, born: 5 };
  const out = G.cleanDrawings([good,
    { id: "b", kind: "trend", points: [{ t: 1, p: 1 }] },                    // a trend line needs two points
    { id: "c d", kind: "hline", points: [{ t: 1, p: 1 }] },                  // odd id
    { id: "e", kind: "nope", points: [{ t: 1, p: 1 }] },
    { id: "f", kind: "hline", points: [{ t: NaN, p: 1 }] },
    { id: "g", kind: "brush", points: [{ t: 1, p: 1 }, { t: 2, p: 2 }, { t: 3, p: 1 }], color: "#f00" },
    "x", null]);
  assert.deepEqual(out.map((d) => d.id), ["a1", "g"]);
  assert.deepEqual(out[0], good);
  assert.equal(out[1].color, undefined);                                    // only palette colours
  assert.deepEqual(G.cleanDrawings("nope"), []);
});

test("the market code and symbol a chart's saved drawings go under", () => {
  assert.deepEqual(G.splitKey("IN:RELIANCE"), { region: "IN", symbol: "RELIANCE" });
  assert.deepEqual(G.splitKey("CRYPTO:BTC-USD"), { region: "CRYPTO", symbol: "BTC-USD" });
  assert.deepEqual(G.splitKey("REPLAY-ab12"), { region: "REPLAY", symbol: "AB12" });
  assert.deepEqual(G.splitKey("us:aapl"), { region: "US", symbol: "AAPL" });
  assert.equal(G.splitKey("weird key!").region, "OTHER");
});
