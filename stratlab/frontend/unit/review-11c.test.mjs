// rev11c: the no-stop risk line, real-bar readouts under Heikin-Ashi, "it" on the right of a sell rule, the "is" operator.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const R = await import("../src/lib/rules.ts");
const T = await import("../src/charts/price/transforms.ts");

const rules = (cs) => cs.map((c) => `${R.refName(c.l)} ${c.op} ${R.refName(c.r)}`);
const parse = (t) => R.parseStrategyText(t);

// 1. risk sizing with no stop
test("risk sizing with no stop loss and no trail is flagged, with a stop it is not", () => {
  assert.equal(R.sizedWithoutStop({ sizing: "risk", sl: 0, trail: 0 }), true);
  assert.equal(R.sizedWithoutStop({ sizing: undefined, sl: 0, trail: undefined }), true);
  assert.equal(R.sizedWithoutStop({ sizing: "risk", sl: 2, trail: 0 }), false);
  assert.equal(R.sizedWithoutStop({ sizing: "risk", sl: 0, trail: 3 }), false);
  assert.equal(R.sizedWithoutStop({ sizing: "capital", sl: 0, trail: 0 }), false);
  assert.match(R.NO_STOP_SIZE_NOTE, /Most in one trade/);
  assert.doesNotMatch(R.NO_STOP_SIZE_NOTE, /if the stop loss is hit/);
});

// 2. Heikin-Ashi readouts come from the real bars
const bars = [{ t: 1, w: 1, o: 100, h: 110, l: 95, c: 108, v: 1 }, { t: 2, w: 2, o: 108, h: 120, l: 105, c: 106, v: 1 }];
test("readout and last-price tag use the real bars, not the Heikin-Ashi ones", () => {
  const ha = T.heikinAshi(bars);
  assert.notEqual(ha[1].c, 106);
  const r = T.readoutAt(bars, 1);
  assert.equal(r.bar.c, 106); assert.equal(r.bar.o, 108); assert.equal(r.prev.c, 108);
  assert.equal(T.readoutAt(bars, 0).prev, null);
  assert.equal(T.readoutAt(bars, 5), null);
  assert.deepEqual(T.lastTag(bars), { close: 106, up: false });
  assert.deepEqual(T.lastTag([bars[0]]), { close: 108, up: true });
  assert.equal(T.lastTag([]), null);
});

// 3. "it" on the right
const SMA = "Price xa SMA 50";
for (const [text, exit] of [
  ["Buy when price crosses above 50 SMA, sell when it crosses below it.", ["Price xb SMA 50"]],
  ["Buy when price crosses above 50 SMA, sell when price crosses below it.", ["Price xb SMA 50"]],
  ["Buy when price crosses above 50 SMA, sell when it crosses back below.", ["Price xb SMA 50"]],
  ["Buy when price closes above the 20 EMA. Sell when it closes below it.", ["Price lt EMA 20"]],
  ["Buy when price is above the 50 SMA. Sell when it falls below it.", ["Price lt SMA 50"]],
]) {
  test(`sell rule kept: ${text}`, () => {
    const p = parse(text);
    assert.deepEqual(rules(p.exit), exit);
    assert.deepEqual(p.dropped, []);
  });
}
test("the entry of the cross sentence is unchanged", () => {
  assert.deepEqual(rules(parse("Buy when price crosses above 50 SMA, sell when it crosses below it.").entry), [SMA]);
});
test("a rule the parser drops is listed in dropped", () => {
  const p = parse("Sell when it crosses below it.");
  assert.deepEqual(p.exit, []);
  assert.equal(p.dropped.length, 1);
});

// 4. "is"
test("'X is Y' gives eq", () => {
  assert.deepEqual(rules(parse("Buy when RSI 14 is 30.").entry), ["RSI 14 eq 30"]);
  const st = parse("Buy when stage is 2.").entry;
  assert.equal(st.length, 1); assert.equal(st[0].op, "eq"); assert.equal(st[0].l.t, "stage"); assert.equal(st[0].r.v, 2);
  assert.equal(parse("Buy when 20 EMA is 50 EMA.").entry[0].op, "eq");
});
test("'is above' and 'is below' stay gt and lt", () => {
  assert.deepEqual(rules(parse("Buy when RSI 14 is below 35 and price is above 200 SMA.").entry), ["RSI 14 lt 35", "Price gt SMA 200"]);
});
