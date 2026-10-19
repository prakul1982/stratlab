// Round 61 (19 Oct 2026): iPhone (Trade), iPad and the dark phone (Invest) — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R61-007: a card's checks line is left out when its headline already gives the count", async () => {
  const { underHeadline, checksLine, LOST_CHECKS } = await import("../src/lib/tradeUi.ts");
  const line = checksLine(3, 3);
  assert.equal(underHeadline(line, "108.5 points behind buy and hold after costs; 3 of 4 checks run · all 3 passed."), "");
  assert.equal(underHeadline(LOST_CHECKS, "5.3 points behind buy and hold; lost money after costs."), "");
  assert.equal(underHeadline(line, "Passed all four checks."), line);
  assert.equal(underHeadline(line, null), line);
  assert.match(read("src/pages/Login.tsx"), /\{cardChecks\(e\) && <span className="small muted">\{cardChecks\(e\)\}<\/span>\}/);
});

test("R61-011: a hidden replay's chart names no day or month", () => {
  const eng = read("src/charts/price/engine.ts");
  assert.match(eng, /if \(this\.hideDates \|\| x < 16 \|\| x > pw - 16\) continue;/);
  assert.match(eng, /this\.hideDates \? `Candle \$\{this\.hoverIndex \+ 1\}`/);
  assert.match(read("src/charts/price/PriceChart.tsx"), /setHideDates\(!!props\.hideDates\)/);
  assert.match(read("src/pages/trade/ReplayPage.tsx"), /replay hideDates=\{s\.hidden\}/);
});

test("R61-003: legs of your own rename a made-up strategy name", () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /set=\{\(legs\) => patch\(\{ legs, structure: "custom", \.\.\.named\(`\$\{s\.underlying\} options`\) \}\)\}/);
  assert.match(src, /if \(id === "custom"\) \{ patch\(\{ structure: "custom", \.\.\.named\(`\$\{s\.underlying\} options`\) \}\); return; \}/);
});

test("R61-004/005/019: the journal verdict says what it covers; the countdown stays one line; the invite rule has its cap", async () => {
  assert.match(read("src/pages/trade/JournalPage.tsx"), /aren't trade by trade, so they aren't part of this verdict/);
  assert.match(read("src/styles.css"), /\.k-notice\.promo-countdown > span:first-child \{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; \}/);
  const { youGet } = await import("../src/lib/invite.ts");
  assert.match(youGet({}, "free"), /adds 8 days, up to 8 times in a year\./);
  assert.match(youGet({ extra_cap: 5, extra_days: 10 }, "pro"), /adds 10 days, up to 5 times in a year\./);
});
