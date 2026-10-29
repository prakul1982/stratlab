// The re-check of the live site (RC1-001 to RC1-013 and what the deep audit left): the frontend's side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("RC1-002: a list longer than a box allows is said in words, not 'Check this value'", async () => {
  const { invalidText } = await import("../src/lib/validate.ts");
  assert.equal(invalidText({ type: "too_long", ctx: { max_length: 12 } }), "Use at most 12 items.");
  assert.equal(invalidText({ type: "too_short", ctx: { min_length: 1 } }), "Pick at least 1.");
});

test("RC1-003: the watchlist's box doesn't promise that an exact symbol works", () => {
  const picker = read("src/components/kit/StockPicker.tsx");
  assert.match(picker, /listedOnly\?: boolean/);
  assert.match(picker, /No listed company matches\. Pick one from the list\./);
  assert.match(picker, /else if \(!listedOnly\) exact\(\)/);
  assert.match(read("src/pages/Research.tsx"), /<StockPicker id=\{id\} market=\{region\} clearOnPick listedOnly onPick=\{add\}/);
});

test("RC1-004: a symbol the prices never heard of is told apart from prices that can't be read", () => {
  const src = read("src/charts/price/PriceChart.tsx");
  assert.match(src, /status && status >= 500 \? "Prices couldn't be read just now\. Try again in a moment\." : `No prices found for \$\{want\}\./);
});

test("RC1-006: the corporate actions page says why nothing is coming up", () => {
  const page = read("src/pages/CorpActionsPage.tsx");
  assert.match(page, /ahead_note\?: string \| null/);
  assert.match(page, /data-testid="ahead-note">\{n \? "Nothing ahead meets the filters\." : data\.ahead_note \?\? "Nothing announced with an ex-date ahead\."\}/);
  assert.doesNotMatch(page, /\(data\.ahead_known \|\| data\.ahead\.length > 0\) && \(/);
  assert.doesNotMatch(read("src/components/CorpActions.tsx"), /aren't available for US companies yet/);
});

test("RC1-008: the paper session's caption says a forming candle is forming whenever the chart draws one", () => {
  assert.match(read("src/pages/PaperPage.tsx"), /const chartNote = snap\.forming \? `/);
});

test("RC1-010 and DB-002: an import's notes stay until read; DB-004: the hours warning names the close", async () => {
  const src = read("src/pages/OptionsPage.tsx");
  assert.match(src, /const DRAFT = OPTIONS_DRAFT, NOTES = OPTIONS_NOTES;/);
  assert.match(read("src/lib/options.ts"), /export const OPTIONS_NOTES = "stratlab\.options\.importnotes\.v1"/);
  assert.match(src, /useState<string\[\]>\(loadNotes\)/);
  assert.match(src, /optionsMarket\(markets, s\.exchange\)\?\.hours \?\? FALLBACK_HOURS\[s\.exchange\]/);
  const { timingIssues, FALLBACK_HOURS } = await import("../src/lib/options.ts");
  const bad = timingIssues({ entry: "16:00", lastEntry: "16:10", squareoff: "16:20" }, "09:15", "15:30");
  assert.equal(bad.length, 3);
  assert.match(bad[0], /^The entry time, 16:00, is after the market closes at 15:30/);
  assert.deepEqual(timingIssues({ entry: "08:00", lastEntry: "14:00", squareoff: "15:00" }, "09:15", "15:30").length, 1);
  assert.ok(FALLBACK_HOURS.NFO.close && FALLBACK_HOURS.MCX.open);
});

test("RC1-011: /pricing repeats the plans page, so its canonical address is /plans", async () => {
  const { seoFor } = await import("../src/lib/seo.ts");
  assert.equal(seoFor("/pricing").canonical, "https://stratlab.studio/plans");
  assert.equal(seoFor("/plans").canonical, "https://stratlab.studio/plans");
});

test("RC1-012: two headlines of one date have one age", async () => {
  const { newsWhen } = await import("../src/lib/researchFormat.ts");
  const now = new Date(2026, 9, 25, 10, 0, 0);
  const morning = newsWhen(new Date(2026, 9, 23, 20, 30).toISOString(), now);
  const evening = newsWhen(new Date(2026, 9, 23, 2, 15).toISOString(), now);
  assert.equal(morning, "23 Oct · 2 days old");
  assert.equal(evening, "23 Oct · 2 days old");
});

test("RC1-013: a snapshot valued another way isn't the start of the headline change", async () => {
  const { netWorthDelta, restatedNote } = await import("../src/lib/networth.ts");
  const hist = [{ d: "2026-10-23", net: 1000, partial: undefined }, { d: "2026-10-24", net: 800, m: 2 }];
  assert.deepEqual(netWorthDelta(790, null, hist, "2026-10-25", 2), { change: -10, since: "2026-10-24" });
  assert.equal(netWorthDelta(790, null, hist.slice(0, 1), "2026-10-25", 2), null);            // the old method's total is no start
  assert.deepEqual(netWorthDelta(790, null, hist.slice(0, 1), "2026-10-25"), { change: -210, since: "2026-10-23" });
  assert.match(restatedNote(hist.slice(0, 1), 2, (d) => d, "2026-10-25"), /valued a different way/);
  assert.equal(restatedNote(hist.slice(1), 2, (d) => d), null);
});
