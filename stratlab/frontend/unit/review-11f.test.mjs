// Review 11f: drawings sync, replay keys, chart gestures, "Test an idea" lookups and the import size limit.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { choose } = await import("../src/charts/price/drawChoose.ts");
const { splitKey } = await import("../src/charts/price/drawGeo.ts");
const { attachGestures } = await import("../src/charts/price/interaction.ts");
const { directId, findPrefill } = await import("../src/lib/prefill.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const d = { id: "a", kind: "trend", points: [] };
const empty = { drawings: [], layout: null, at: 0 };

test("a copy the account already held loses to an emptied account", () => {
  assert.equal(choose({ drawings: [d], layout: null, at: 1000, dirty: false, synced: true }, empty).send, false);
  assert.deepEqual(choose({ drawings: [d], layout: null, at: 1000, dirty: false, synced: true }, empty).use, empty);
});

test("a copy that was never sent still goes up to an empty account", () => {
  const c = choose({ drawings: [d], layout: null, at: 0, dirty: false, synced: false }, empty);
  assert.equal(c.send, true);
});

test("replay ids that differ only in case stay two saved rows", () => {
  const a = splitKey("REPLAY-abc"), b = splitKey("REPLAY-ABC");
  assert.equal(a.region, "REPLAY");
  assert.notEqual(a.symbol, b.symbol);
  assert.equal(a.symbol, "ABC");
});

function fakeEl() {
  const L = {};
  return { L, addEventListener: (n, f) => { L[n] = f; }, removeEventListener() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }), setPointerCapture() {} };
}
const ev = (type, id, x, y) => ({ type, pointerId: id, pointerType: "touch", button: 0, clientX: x, clientY: y });

test("a pointercancel is not a tap", () => {
  const el = fakeEl(), calls = [];
  attachGestures(el, { hover() {}, zoom() {}, pan() {}, leave() {}, tap: () => calls.push("tap"), panEnd: () => calls.push("panEnd") });
  el.L.pointerdown(ev("pointerdown", 1, 10, 10));
  el.L.pointercancel(ev("pointercancel", 1, 10, 10));
  assert.deepEqual(calls, ["panEnd"]);
});

test("a pinch that starts during a drag drops the drag", () => {
  const el = fakeEl(), calls = [];
  attachGestures(el, { hover() {}, zoom() {}, pan() {}, leave() {}, down: () => true, drag: () => calls.push("drag"), drop: () => calls.push("drop") });
  el.L.pointerdown(ev("pointerdown", 1, 10, 10));
  el.L.pointerdown(ev("pointerdown", 2, 50, 50));
  assert.deepEqual(calls, ["drop"]);
});

test("a one-letter US ticker is looked up by id, and a chosen contract by its own id", async () => {
  assert.equal(directId({ market: "US", symbol: "f" }), "US:F");
  assert.equal(directId({ market: "IN", symbol: "RELIANCE" }), null);
  assert.equal(directId({ market: "IN", symbol: "NIFTY", instrumentId: "IN:123" }), "IN:123");
  const paths = [];
  const get = async (p) => { paths.push(p); return { id: "US:F", symbol: "F" }; };
  assert.equal((await findPrefill({ market: "US", symbol: "F" }, get)).symbol, "F");
  assert.deepEqual(paths, ["/instruments/US%3AF"]);
});

test("a chosen contract that can't be found is reported, not swapped for the stock", async () => {
  const paths = [];
  const get = async (p) => { paths.push(p); throw new Error("404"); };
  assert.equal(await findPrefill({ market: "IN", symbol: "NIFTY", instrumentId: "IN:999" }, get), null);
  assert.equal(paths.length, 1);
  assert.equal(await findPrefill({ market: "US", symbol: "ZZZZ" }, async (p) => { if (p.includes("search")) return []; throw new Error("404"); }), null);
});

test("the palette passes the instrument id, the import has one limit and the save message is shown", () => {
  assert.match(read("src/components/SearchPalette.tsx"), /testIdea\("", mk, i\.symbol, i\.id\)/);
  const imp = read("src/components/ImportStrategy.tsx");
  assert.doesNotMatch(imp, /\.slice\(0, 20000\)/);
  assert.match(imp, /too long to import/);
  assert.match(read("src/charts/price/PriceChart.tsx"), /setSaveNote/);
});
