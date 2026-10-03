import { expect, test } from "@playwright/test";
import { parseStrategyText, STARTERS } from "../src/lib/rules";

// The simple converter, used when the AI builder can't run: plain sentences people really type.
test.beforeEach(({}, info) => test.skip(info.project.name !== "desktop", "no browser needed: once is enough"));

const ema = (p: number) => ({ t: "ema", p });

test("\"sell when it crosses back below\" reverses the entry's crossing, and \"5% stop loss\" is the stop", () => {
  const r = parseStrategyText("Buy RELIANCE when the 20 day EMA crosses above the 50 day EMA, sell when it crosses back below, 5% stop loss");
  expect(r.entry).toEqual([{ l: ema(20), op: "xa", r: ema(50) }]);
  expect(r.exit).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(r.risk.sl).toBe(5);
});

test("a target written number-first is the target, not a price rule", () => {
  const r = parseStrategyText("Buy when price crosses above 50 SMA with a 3% stop loss and a 9% target");
  expect(r.entry).toEqual([{ l: { t: "price" }, op: "xa", r: { t: "sma", p: 50 } }]);
  expect(r.exit).toEqual([]);
  expect(r.risk).toMatchObject({ sl: 3, tgt: 9 });
});

test("the starter ideas still read the same", () => {
  const [trend, cross, dip] = STARTERS.map((s) => parseStrategyText(s.text));
  expect(trend.exit).toEqual([{ l: { t: "price" }, op: "xb", r: { t: "sma", p: 50 } }]);
  expect(trend.risk).toMatchObject({ sl: 4, tgt: 10, riskPct: 1 });
  expect(cross.entry).toEqual([{ l: ema(20), op: "xa", r: ema(50) }]);
  expect(cross.exit).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(dip.entry).toHaveLength(2);
  expect(dip.exit).toEqual([{ l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 60 } }]);
});
