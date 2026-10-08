import { expect, test } from "@playwright/test";
import { blankStrategy, defaultExit, INDICATORS, INDICATOR_GROUPS, parseStrategyText, withDefaultExit } from "../src/lib/rules";

// Round 5, the owner's review (R5O-…). The first tests need no browser.
const pure = (info: { project: { name: string } }) => test.skip(info.project.name !== "desktop", "no browser needed: once is enough");
const ema = (p: number) => ({ t: "ema" as const, p });

test("no target the person didn't ask for (R5O-010)", ({}, info) => {
  pure(info);
  expect(blankStrategy().risk.tgt).toBe(0);
  const p = parseStrategyText("Buy when 20 EMA crosses above 50 EMA. Stop loss 2%");
  const s = { ...blankStrategy(), entry: p.entry, exit: p.exit, risk: { ...blankStrategy().risk, ...p.risk } };
  expect(s.risk.sl).toBe(2);
  expect(s.risk.tgt).toBe(0);
});

test("the sell rule shown as the default is the one the notebook runs (R5O-010)", ({}, info) => {
  pure(info);
  const s = { ...blankStrategy(), entry: [{ l: ema(20), op: "xa" as const, r: ema(50) }] };
  expect(defaultExit(s)).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(withDefaultExit(s, ["sl"]).exit).toEqual([{ l: ema(20), op: "xb", r: ema(50) }]);
  expect(withDefaultExit(s, ["exit"]).exit).toEqual([]);                       // the idea said how to sell: left alone
  const rsi = { ...blankStrategy(), entry: [{ l: { t: "rsi" as const, p: 14 }, op: "xb" as const, r: { t: "num" as const, v: 30 } }] };
  expect(withDefaultExit(rsi, []).exit).toEqual([{ l: { t: "rsi", p: 14 }, op: "xa", r: { t: "num", v: 55 } }]);
  const level = { ...blankStrategy(), entry: [{ l: { t: "price" as const }, op: "gt" as const, r: { t: "num" as const, v: 100 } }] };
  expect(withDefaultExit(level, []).exit).toEqual([]);                          // nothing follows: the page says no sell rule is set
});

test("the rule picker is grouped, in plain words (R5O-040)", ({}, info) => {
  pure(info);
  const stage = INDICATORS.find((i) => i.t === "stage")!;
  expect(stage.name).toBe("Stage (1–4)");
  expect(stage.friendly).toMatch(/1 basing, 2 rising, 3 topping, 4 falling/);
  expect(INDICATORS.map((i) => i.name).join(" ")).not.toMatch(/Weinstein|Donchian/);
  for (const i of INDICATORS) expect(INDICATOR_GROUPS.map(([g]) => g)).toContain(i.group);
  for (const [g] of INDICATOR_GROUPS) expect(INDICATORS.filter((i) => i.group === g).length).toBeLessThanOrEqual(8);
});
