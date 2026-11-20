// rel1: reliability and honest labels (CX1 problems 3 and 9, LIVE9).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("rel1 item 1: a busy source is asked again on its own, a little later each time, then the error", async () => {
  const { busyRetryIn, busyLine, BUSY_RETRY_MS } = await import("../src/lib/busyRetry.ts");
  const busy = { status: 503 };
  assert.deepEqual([0, 1, 2, 3].map((n) => busyRetryIn(busy, n)), [...BUSY_RETRY_MS, null]);
  assert.equal(busyRetryIn({ status: 404 }, 0), null);
  assert.equal(busyRetryIn({ status: 402 }, 0), null);
  assert.equal(busyRetryIn(new Error("x"), 0), null);
  assert.equal(busyLine("The source is slow. Try again in a minute.", 10000), "The source is slow. Asking again in 10 s.");
  const page = read("src/pages/DeepDive.tsx");
  assert.match(page, /busyRetryIn\(e, auto\.current\)/);
  assert.match(page, /data-testid="deep-busy"/);
  assert.match(page, /v\?\.figures_kept && /);
});

test("rel1 item 2: a sign-in that ends on its own mid-visit says 'You were signed out', not the first-visit wall", async () => {
  const so = await import("../src/lib/signout.ts");
  assert.equal(so.signingOutOnPurpose(), false);
  const app = read("src/lib/app.tsx");
  assert.match(app, /if \(e === "SIGNED_OUT" && !signingOutOnPurpose\(\)\) noteSignInEnded\(\);/);
  // every sign-out a person asks for is marked before the sign-in library hears of it
  assert.match(read("src/lib/signout.ts"), /markSignOutOnPurpose\(\);\s*await leavePush\(\);/);
  assert.match(read("src/pages/AccountPage.tsx"), /markSignOutOnPurpose\(\); await leavePush\(\); const \{ error \} = await supabase\.auth\.signOut\(\{ scope: "global" \}\)/);
  // the sign-in page reads that mark: "You were signed out" before "Sign in to see …"
  assert.match(read("src/pages/Gate.tsx"), /ended \? "You were signed out"/);
  globalThis.sessionStorage ??= { _m: new Map(), getItem(k) { return this._m.get(k) ?? null; }, setItem(k, v) { this._m.set(k, String(v)); }, removeItem(k) { this._m.delete(k); } };
  await so.signOutHere({ signOut: async () => ({ error: null }) }, () => undefined).catch(() => undefined);
  assert.equal(so.signingOutOnPurpose(), true);
});

test("rel1 item 5: a lot the exchange hasn't given is said in words, never a bare dash", () => {
  const page = read("src/pages/IposPage.tsx");
  // (updated on purpose, site76 LIVE14A-013: the words also say whether the issue's page was found and read, and when)
  assert.match(page, /export const lotMissing = \(tab: Stage, r\?: Pick<IpoRow, "page" \| "page_at" \| "exchanges">\): string => \{\n  if \(tab === "upcoming"\) return "Not announced yet";/);
  assert.match(page, /return "Not on the exchange's page yet";/);
  // (updated on purpose, LIVE16B-006: the cell carries the reason as hover text when NSE has no page for the issue)
  assert.match(page, /data-testid="ipo-lot-none" title=\{missingWhy\(r\)\}>\{lotMissing\(tab, r\)\}/);
  assert.doesNotMatch(page, /minText\(r\)\}<\/span><\/> : "–"\)/);
});

test("LIVE9A-014: day chips, market value at the price beside it, and the timing in its own place", async () => {
  const R = await import("../src/lib/resultsRows.ts");
  const days = [{ date: "2026-11-16", count: 40 }, { date: "2026-11-17", count: 12 }, { date: "2026-11-18", count: 30 }, { date: "2026-11-18", count: 30 },
    { date: "2026-11-26", count: 0 }, { date: "2026-11-27", count: 3 }];
  assert.deepEqual(R.laterDays(days, "2026-11-16"), ["2026-11-18", "2026-11-27"]);    // no past day, no tomorrow by date, no empty holiday
  assert.equal(R.nextDay("2026-11-30"), "2026-12-01");
  assert.equal(Math.round(R.capAt(3.92e12, 162.85, 155.58) / 1e10) / 100, 3.75);       // NVDA's value at the live price
  assert.equal(R.capAt(3.92e12, 162.85, null), 3.92e12);
  assert.equal(R.capAt(3.92e12, 162.85, 16.285), 3.92e12);                              // a split-sized jump: the stored value stands
  assert.equal(R.capAt(null, 1, 2), null);
  assert.equal(R.whenShort("after the close"), "After the close");
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /data-testid="res-when">\{whenShort\(r\.when\)\}/);
  assert.match(page, /const cap = capAt\(r\.cap, r\.last, live\);/);
  assert.match(page, /cell: \(r\) => capCell\(r, quotes\[r\.symbol\]\?\.price, \(v\) => screenCap\(v, r\.region\)\) \}/);
  assert.match(page, /laterDays\(\(data\?\.weeks \?\? \[\]\)\.flatMap/);
});

test("LIVE9B-010: the home page's watchlist paints its last rows at once, for this account only, and reserves its height", async () => {
  const M = await import("../src/lib/mineMovers.ts");
  const mem2 = new Map();
  const store = { getItem: (k) => mem2.get(k) ?? null, setItem: (k, v) => mem2.set(k, String(v)), removeItem: (k) => mem2.delete(k) };
  const now = Date.parse("2026-11-17T00:50:00Z");
  M.keepMovers("u1", [{ symbol: "RELIANCE" }], now, store);
  assert.deepEqual(M.readKeptMovers("u1", now + 60_000, store)?.rows, [{ symbol: "RELIANCE" }]);
  assert.equal(M.readKeptMovers("u2", now, store), null);                       // another account's rows are never shown
  assert.equal(M.readKeptMovers("u1", now + 5 * 86400_000, store), null);       // too old to help
  M.forgetKeptMovers(store);
  assert.equal(M.readKeptMovers("u1", now, store), null);
  assert.match(read("src/lib/localData.ts"), /forgetKeptMovers\(\);/);           // gone at sign-out
  const page = read("src/pages/MineHome.tsx");
  assert.match(page, /lines=\{Math\.max\(3, Math\.min\(6, items\?\.length \?\? 3\)\)\}/);
  assert.match(page, /data-testid="mine-movers-earlier">As read \{asOf\(earlier\.at, \{ year: false \}\)\}; today's prices are on their way\./);
});

test("LIVE9B-010: the market tiles paint their last levels, each with its own day, until the fresh read", async () => {
  const M = await import("../src/lib/mine.ts");
  const mem3 = new Map();
  const store = { getItem: (k) => mem3.get(k) ?? null, setItem: (k, v) => mem3.set(k, String(v)) };
  const now = Date.now();
  M.keepStripTile("nifty", { values: [25030, 25291], last: 25291, prev: 25030, changePct: 1.04, day: "2026-11-16", at: now }, store);
  const got = M.keptStrip(now + 1000, store);
  assert.equal(got.nifty.last, 25291);
  assert.equal(got.nifty.day, "2026-11-16");                                  // the tile says the day its level is of
  assert.deepEqual(M.keptStrip(now + 5 * 86400_000, store), {});              // too old: the tile reads afresh
  assert.match(read("src/lib/mine.ts"), /useState<Record<string, Series \| null \| undefined>>\(\(\) => keptStrip\(\)\)/);
});

test("rel1 item 7: the peers card states the size rule", () => {
  assert.match(read("src/components/CompanyPeers.tsx"), /with a market value between 1\/20 of the company's own and 20 times it, nearest first\./);
});
