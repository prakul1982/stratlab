// Round 9 review of the broker, reliability and the US session (9 Oct 2026): the app's side, each on the reviewer's example.
// Every clock here is a fixed instant. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

test("R9R-003: the funds page shows the NAV date only when funds are held, and never the time the file was read", () => {
  const page = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(page, /asOf=\{t\?\.held \? \(t\.nav_dates\?\.\[1\] \?\? view\?\.nav_date\) : undefined\} asOfLabel="NAVs up to"/);
  assert.doesNotMatch(page, /nav_read_at/);
});

test("R9R-004: a count of days is written in the singular for one", async () => {
  const { periodName } = await import("../src/lib/format.ts");
  assert.equal(periodName(1), "1 day");
  assert.equal(periodName(10), "10 days");
  assert.equal(periodName(45), "1 month");
});

test("R9R-007: during a session with no live count the stored day is the latest close and the count's time is said", async () => {
  const { latestDue } = await import("../src/lib/format.ts");
  const during = { day: "2026-10-09", due: "5:45 PM ET", during: true };
  assert.equal(latestDue("2026-10-08", during), "Latest close 8 Oct · today's count comes after 5:45 PM ET");
  assert.equal(latestDue("2026-10-09", during), null);
  assert.equal(latestDue("2026-10-08", { day: "2026-10-09", due: null, during: true }), "Latest close 8 Oct · today's count comes after the close");
  // after the close it is the evening wording, as before
  assert.equal(latestDue("2026-10-08", { day: "2026-10-09", due: "5:45 PM ET" }), "Latest: 8 Oct · 9 Oct due about 5:45 PM ET");
  // the Invest home's card says the same
  const { cardFigures } = await import("../src/lib/breadth.ts");
  const figure = { value: 1, prev: null, change: null };
  const today = { day: "2026-10-08", prev_day: null, adv: figure, dec: figure, pct50: figure, highs: figure, lows: figure };
  assert.equal(cardFigures({ today, live: null, pending: during }).when, "Latest close 8 Oct · today's count comes after 5:45 PM ET");
});

test("R9R-008: the Invest home's US tab drives every panel and says why a card has nothing for the US", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /<WatchPanel region=\{region\} \/>/);
  assert.match(src, /<ResultsToday region=\{region\} \/>/);
  assert.match(src, /<BreadthCard region=\{region\} \/>/);
  assert.match(src, /<RedFlags region=\{region\} \/>/);
  assert.match(src, /data-testid="invest-us-redflags"/);
  assert.match(src, /Red-flag filings are read from India's exchange, so there are none to show for US companies/);
  const card = read("src/components/BreadthCard.tsx");
  assert.match(card, /BreadthCard\(\{ region: picked \}/);
  assert.match(card, /const region = picked \?\? homeRegion\(\)/);
});

test("R9R-008: the US market's own breadth group is the S&P 500", async () => {
  const { MARKET_GROUP, savedPick } = await import("../src/lib/breadthPick.ts");
  assert.equal(MARKET_GROUP.US, "sp500");
  assert.equal(savedPick("US").group, "sp500");
});

test("R9R-010: the lower cards of My space read their data after the first paint", async () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.match(mine, /const later = useAfterPaint\(\);/);
  assert.match(mine, /const coming = useComingUp\(6, later\);/);
  assert.match(mine, /<MarketsCard later=\{later\} \/>/);
  const lib = read("src/lib/mine.ts");
  assert.match(lib, /export function useComingUp\(limit = 6, enabled = true\)/);
  assert.match(lib, /export function useMarketStrip\(enabled = true\)/);
  // the helper waits for a frame, then a pause, and can be cancelled
  const { afterPaint, DEFER_MS } = await import("../src/lib/defer.ts");
  assert.ok(DEFER_MS >= 500 && DEFER_MS <= 3000);
  const ran = [];
  const frames = [];
  globalThis.requestAnimationFrame = (fn) => { frames.push(fn); return frames.length; };
  globalThis.cancelAnimationFrame = (id) => { frames[id - 1] = null; };
  const cancel = afterPaint(() => ran.push("a"), 5);
  assert.deepEqual(ran, []);                                              // not before the frame
  frames[0]();
  await new Promise((r) => setTimeout(r, 40));
  assert.deepEqual(ran, ["a"]);
  const cancelled = afterPaint(() => ran.push("b"), 5);
  cancelled();
  frames[1]?.();
  await new Promise((r) => setTimeout(r, 40));
  assert.deepEqual(ran, ["a"]);                                           // cancelled before it ran
  cancel();
  delete globalThis.requestAnimationFrame;
  delete globalThis.cancelAnimationFrame;
});

test("R9R-011: the net worth page says the same thing in its lede and its empty state about stocks", () => {
  const page = read("src/pages/money/NetWorthPage.tsx");
  assert.match(page, /lede="What you own minus what you owe: your stocks from My Holdings and mutual funds from your statement \(both added on their own\)/);
  assert.match(page, /are added to the total on their own once you have some there/);
  assert.doesNotMatch(page, /counted on their own/);
});
