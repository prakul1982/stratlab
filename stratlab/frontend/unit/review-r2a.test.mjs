import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

// Round 2A: one minus glyph, the AI builder's blame, signed-out titles, the closing auction before the open.

test("one minus: a hyphen used as a minus becomes the real minus, ranges and dates are left alone (R2A-019)", async () => {
  const { minus, minusNode, num } = await import("../src/lib/format.ts");
  assert.equal(minus("-0.21"), "−0.21");
  assert.equal(minus("Sharpe -0.21"), "Sharpe −0.21");
  assert.equal(minus("(-3.5%)"), "(−3.5%)");
  assert.equal(minus("-₹473"), "−₹473");
  assert.equal(minus("FY 2024-25"), "FY 2024-25");
  assert.equal(minus("2026-10-07"), "2026-10-07");
  assert.equal(minus("20-day average"), "20-day average");
  assert.equal(minusNode(-4), "−4");
  assert.equal(minusNode("-1,801"), "−1,801");
  assert.equal(num(-0.21, 2), "−0.21");
  assert.equal(num(1234.5, 2), "1,234.50");
  assert.equal(num(-0.001, 2), "0.00");           // a figure that rounds to nothing has no sign
  assert.equal(num(null), "–");
});

test("a build that finds no rule blames our side when the sentence plainly holds one (R2A-008)", async () => {
  const { looksLikeRule, noRuleNote } = await import("../src/lib/rules.ts");
  const first = "Buy NIFTY 50 when the 20 EMA crosses above the 50 EMA, stop loss 2%";     // the New page's own first example
  assert.equal(looksLikeRule(first), true);
  const ours = noRuleNote(first);
  assert.equal(ours.system, true);
  assert.match(ours.note, /on our side/);
  assert.match(ours.note, /Try again/);
  assert.doesNotMatch(ours.note, /couldn't find an entry rule/);
  const vague = noRuleNote("something about the market and my feelings");
  assert.equal(vague.system, false);
  assert.match(vague.note, /Say when to buy/);
});

test("signed-out tab titles say what they wait for (R2A-025)", async () => {
  const { signedOutTitle } = await import("../src/lib/title.ts");
  assert.equal(signedOutTitle("/options"), "Sign in · Options builder · StratLab");
  assert.equal(signedOutTitle("/holdings").startsWith("Sign in · "), true);
  assert.equal(signedOutTitle("/pricing"), "Plans · StratLab");
  assert.equal(signedOutTitle("/plans"), "Plans · StratLab");
  assert.equal(signedOutTitle("/"), "StratLab: test it, research it, track it");
});

test("the closing auction says closed before the open, not continuous trading (R2A-006)", async () => {
  const { PHASE_TEXT } = await import("../src/lib/closingAuction.ts");
  assert.match(PHASE_TEXT.preopen, /closed/i);
  assert.doesNotMatch(PHASE_TEXT.preopen, /Continuous trading\./);
  assert.match(PHASE_TEXT.holiday, /closed/i);
});

test("every Money page opens on the year being filed, even one with nothing in it (R2A-003)", async () => {
  const { pickFy } = await import("../src/lib/fy.ts");
  // tax report (sales in 2024 only), tax tools (dividends in 2025), ITR: all list the filing year, so all open on it
  for (const years of [[2026, 2025, 2024], [2026, 2025]]) assert.equal(pickFy(years, 2026, (y) => y === 2024, null), 2025);
});
