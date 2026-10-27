// RC3-T: a harsh correctness review of the Trade side (see backend/tests/test_review_rc3t.py). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const R = await import("../src/lib/replay.ts");
const { changes, sizing, BOLD_NOTE } = await import("../src/lib/compare.ts");

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// ---------- RC3T-002: the page's replay figure counts the depository charge like the server ----------
const bar = (t, c) => ({ t, o: c, h: c + 1, l: c - 1, c });
const days = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"].map((d, i) => bar(`${d}T00:00:00+05:30`, 100 + i));
const rates = { in_eq: { buy: 0, sell: 0, flat: 0, dp: 15.34 }, in_etf: { buy: 0, sell: 0, flat: 0, dp: 15.34 }, in_fut: { buy: 0, sell: 0, flat: 0 } };

test("a delivery sale pays the depository charge once for each day it sold, a short sale and futures none (RC3T-002)", () => {
  const orders = [{ i: 1, action: "long", qty: 100 }, { i: 2, action: "short", qty: 50 }, { i: 3, action: "flat" }];
  const got = R.simulate(days, orders, 1, 4, "in_eq", rates, 1, true);
  assert.equal(got.trades.length, 1);
  assert.ok(Math.abs(got.trades[0].charges - 2 * 15.34) < 1e-9, `two days of sales: ${got.trades[0].charges}`);
  const etf = R.simulate(days, orders, 1, 4, "in_etf", rates, 1, true);
  assert.ok(Math.abs(etf.trades[0].charges - 2 * 15.34) < 1e-9);
  const short = R.simulate(days, [{ i: 1, action: "short", qty: 100 }, { i: 3, action: "flat" }], 1, 4, "in_eq", rates, 1, true);
  assert.equal(short.trades[0].charges, 0);
  const fut = R.simulate(days, orders, 1, 4, "in_fut", rates, 1, true);
  assert.equal(fut.trades[0].charges, 0);
  const intra = [bar("2026-03-02T09:15:00+05:30", 100), bar("2026-03-02T09:20:00+05:30", 101), bar("2026-03-02T09:25:00+05:30", 102)];
  const one = R.simulate(intra, [{ i: 1, action: "long", qty: 10 }, { i: 2, action: "flat" }], 1, 2, "in_eq", { ...rates, in_eq: { buy: 0, sell: 0, flat: 0, dp: 15.34 } }, 1, true);
  assert.equal(one.trades[0].charges, 0, "bought and sold on one day is intraday: none");
});

// ---------- RC3T-004: a change in leverage is said, whatever the sizing ----------
const run = (risk, symbol = "NIFTY") => ({ strategy: { name: "x", tf: "1d", entry: [], exit: [], risk: { capital: 500000, riskPct: 1, maxAlloc: 100, sl: 2, tgt: 0, brokerage: 20, slippage: 0.05, ...risk } }, instrument: { symbol, currency: "INR" }, days: 365 });

test("leverage is part of how a run sizes its trades, by risk or by capital (RC3T-004)", () => {
  assert.equal(sizing({ sizing: "risk", leverage: 1 }, "INR"), "by risk");
  assert.equal(sizing({ sizing: "risk", leverage: 3 }, "INR"), "by risk × 3 leverage");
  assert.match(sizing({ sizing: "capital", leverage: 3, perTrade: 50000 }, "INR"), /fixed .* a trade × 3 leverage/);
  const out = changes(run({ leverage: 1 }), run({ leverage: 3 }));
  assert.deepEqual(out, ["Position size: by risk → by risk × 3 leverage"]);
  assert.deepEqual(changes(run({ leverage: 2 }), run({ leverage: 2 })), []);
});

// ---------- RC3T-005: the table's bold is said as it is drawn ----------
test("the numbers table does not say bold is always the larger figure (RC3T-005)", () => {
  assert.doesNotMatch(BOLD_NOTE, /the larger/);
  assert.match(BOLD_NOTE, /lower one/);
  assert.match(src("pages/CompareExperiments.tsx"), /info=\{BOLD_NOTE\}/);
});

// ---------- RC3T-007: the entry window ends at the last entry's minute, as the session's own clock has it ----------
test("at the last entry's minute the window is shut, as the server judges it (RC3T-007)", async () => {
  const { startWhenText } = await import("../src/lib/options.ts");
  const t = { entry: "09:30", lastEntry: "14:45" };
  const wed = (hm) => new Date(`2026-10-28T${hm}:30+05:30`);
  assert.match(startWhenText(t, null, wed("14:44")), /^now if prices are live/);
  assert.equal(startWhenText(t, null, wed("14:45")), "at 09:30 on market days");          // the server enters from 09:30 up to, not at, 14:45
  assert.match(startWhenText(t, null, wed("09:30")), /^now if prices are live/);
  const s = read("src/lib/options.ts");
  assert.match(s, /hm >= s\.timing\.lastEntry\) return `\$\{none\} Next entry/);
});

// ---------- RC3T-008: the stand-in hours of futures and options are the derivatives segment's, to 15:40 ----------
test("the stand-in hours for NSE and BSE options end at 15:40, where the segment closes (RC3T-008)", async () => {
  const { FALLBACK_HOURS, timingIssues } = await import("../src/lib/options.ts");
  assert.equal(FALLBACK_HOURS.NFO.close, "15:40");
  assert.equal(FALLBACK_HOURS.BFO.close, "15:40");
  assert.deepEqual(timingIssues({ entry: "09:30", lastEntry: "14:45", squareoff: "15:35" }, FALLBACK_HOURS.NFO.open, FALLBACK_HOURS.NFO.close), []);
});

// ---------- RC3T-009: a stock with no gap is not "unchanged" ----------
test("the closing auction's above, unchanged and below add up over the stocks that have a gap (RC3T-009)", async () => {
  const { aboveBelow } = await import("../src/lib/closingAuction.ts");
  assert.equal(aboveBelow({ stocks: 213, compared: 213, up: 181, down: 28 }), "181 above · 4 unchanged · 28 below");
  assert.equal(aboveBelow({ stocks: 213, compared: 210, up: 181, down: 28 }), "181 above · 1 unchanged · 28 below · 3 without a gap");
  assert.equal(aboveBelow({ stocks: 10, up: 6, down: 3 }), "6 above · 1 unchanged · 3 below");           // an older answer has no `compared`
});

// ---------- RC3T-010: the help for the checks and the figures says what they are, not what to conclude ----------
test("the unseen-data help states the rule it applies; Sharpe's help is true of a losing run; the cost help names the DP charge (RC3T-010)", async () => {
  const { HELP } = await import("../src/lib/help.ts");
  assert.doesNotMatch(HELP.unseen, /A real edge/);
  assert.match(HELP.unseen, /at least 5 trades closed in it/);
  assert.doesNotMatch(HELP.sharpe, /the gains came with a lot of swings/);
  assert.match(HELP.sharpe, /near 0 or below/);
  assert.match(HELP.keep, /depository \(DP\) charge on Indian shares sold from delivery/);
  assert.doesNotMatch(HELP.winRate, /is fine/);
  assert.doesNotMatch(HELP.walkforward, /really have earned/);
  assert.doesNotMatch(HELP.basket, /more likely a real pattern|probably that chart/);
  assert.match(HELP.basket, /most making money means the result isn't limited to your pick/);
});

test("the walk-forward card states what happened, not why (RC3T-010)", () => {
  const s = read("src/pages/ExperimentPage.tsx");
  assert.doesNotMatch(s, /flattered it|fitting noise/);
  assert.match(s, /under 50% means most of it did not carry over/);
  assert.match(s, /The best settings changed from one step to the next\./);
});
