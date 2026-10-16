// Round 29B (owner pass): My stocks currency, a lazy page that never arrives, the legacy emptied-account run, the report card's
// words, the glance's repeated Stage, plural, the last-price line, the cold start.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const { itemCurrency } = await import("../src/lib/newsPrice.ts");
const { importWithRetry } = await import("../src/lib/lazyRetry.ts");
const { isLegacyEmptied, emptiedDay } = await import("../src/lib/legacyRun.ts");
const { unsettledNote, saidOn } = await import("../src/lib/reportCard.ts");
const { trendBadge } = await import("../src/lib/glance.ts");
const { waitingLine } = await import("../src/lib/bizUpdates.ts");
const { lineSpans, labelClear } = await import("../src/charts/price/lastPrice.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("R29B-002: an item's price is in its market's currency, never a guessed rupee", () => {
  assert.equal(itemCurrency("IN"), "INR");
  assert.equal(itemCurrency("US"), "USD");
  assert.equal(itemCurrency(null), null);
  assert.equal(itemCurrency("XX"), null);
  assert.equal(itemCurrency(undefined, "USD"), "USD");          // the item's own currency wins
  assert.equal(itemCurrency("IN", "USD"), "USD");
  assert.doesNotMatch(read("src/pages/NewsPage.tsx"), /issue\.region \?\? "IN"/);
});

test("R29B-003: a chunk that never answers fails after its time, and a slow one that comes is used", async () => {
  await assert.rejects(importWithRetry(() => new Promise(() => {}), [], 20), /timed out/);
  let n = 0;
  const got = await importWithRetry(async () => { if (++n < 3) throw new Error("Failed to fetch dynamically imported module"); return { ok: 1 }; }, [1, 1], 50);
  assert.deepEqual(got, { ok: 1 });
  await assert.rejects(importWithRetry(async () => { throw new Error("Failed to fetch dynamically imported module"); }, [1], 50), /dynamically imported/);
});

test("R29B-003: 'Checking access' and the admin sections end on the reload card, not a spinner for ever", () => {
  assert.match(read("src/components/AccountWait.tsx"), /stuck[\s\S]*<LoadFailed what="this page" \/>/);
  assert.match(read("src/pages/AdminPage.tsx"), /<Suspense fallback=\{<Card label="Loading"><Opening /);
});

test("R29B-009: a run that says the account emptied and then lists later trades is a legacy run", () => {
  const trade = (entry_t, exit_t, why = "Stop") => ({ entry_t, exit_t, why });
  const legacy = { stats: { emptied_on: "2022-05-09" }, trades: [trade("2022-05-02", "2022-05-09", "Account emptied"), trade("2022-06-01", "2022-06-03")] };
  assert.equal(isLegacyEmptied(legacy), true);
  assert.equal(isLegacyEmptied({ stats: { emptied_on: "2022-05-09" }, trades: [trade("2022-05-02", "2022-05-09", "Account emptied")] }), false);
  assert.equal(isLegacyEmptied({ stats: {}, trades: [trade("2022-06-01", "2022-06-03")] }), false);
  assert.equal(emptiedDay({ stats: {}, trades: [trade("2022-05-02", "2022-05-09", "Account emptied")] }), "2022-05-09");
  assert.match(read("src/pages/ExperimentPage.tsx"), /\{legacyNote\(e\)\}/);     // changed on purpose (round 39): the note is the plain-words legacyNote, which still says it was saved by an older version
});

test("R29B-014: the report card never says a past period hasn't ended; outlook shows when it was said", () => {
  assert.doesNotMatch(unsettledNote({ pending: 0, unchecked: 3 }), /hasn't ended/);
  assert.match(unsettledNote({ pending: 0, unchecked: 3 }), /no reported number or later statement/);
  assert.match(unsettledNote({ pending: 2, unchecked: 0 }), /not out yet/);
  assert.equal(saidOn("2023-05-10", (d) => `on ${d}`), "said on 2023-05-10");
  assert.equal(saidOn(null, String), "date not given");
  assert.doesNotMatch(read("src/pages/DeepDive.tsx"), /period hasn't ended/);
});

test("R29B-018: the glance doesn't repeat Stage", () => {
  assert.equal(trendBadge(2, "stage2"), null);
  assert.equal(trendBadge(2, "st_s2"), null);
  assert.equal(trendBadge(2, "fresh"), "Fresh Stage 2 + Supertrend");
  assert.equal(trendBadge(3, null), null);
});

test("R29B-023: one stock is waiting, several are", () => {
  assert.match(waitingLine(1), /^1 of your stocks is waiting to be read/);
  assert.match(waitingLine(3), /^3 of your stocks are waiting to be read/);
});

test("R29B-017: the last price's line leaves the legend clear and no axis label sits under the tag", () => {
  assert.deepEqual(lineSpans(100, 300, { w: 120, h: 30 }), [[0, 300]]);
  assert.deepEqual(lineSpans(12, 300, { w: 120, h: 30 }), [[134, 300]]);
  assert.deepEqual(lineSpans(12, 100, { w: 120, h: 30 }), []);
  assert.deepEqual(lineSpans(12, 300, null), [[0, 300]]);
  assert.equal(labelClear(100, [104]), false);
  assert.equal(labelClear(100, [120]), true);
  assert.match(read("src/charts/price/engine.ts"), /labelClear\(y, tagYs\)/);
});

test("R29B-019: a saved sign-in never sees the marketing words while the app starts", () => {
  assert.match(read("public/boot.js"), /sb-\.\+-auth-token[\s\S]*data-saved/);
  assert.match(read("index.html"), /html\[data-saved\] \[data-boot\] > \* \{ display: none; \}/);
  assert.match(read("src/entry.tsx"), /if \(!account\) holdStartup\(root\)/);
});

test("R29B-008: the trailing stop and time limit read as a label and a value", () => {
  const rules = read("src/components/Rules.tsx");
  assert.doesNotMatch(rules, /nothing \(off\)|no time limit|Trail the stop by/);
  assert.match(rules, /Trailing stop:[\s\S]*missing="off"[\s\S]*Time limit:[\s\S]*missing="none"/);
});
