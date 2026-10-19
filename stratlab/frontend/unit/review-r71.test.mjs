// Round 71 (19 Oct 2026): the owner on Safari through the US open — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R71-003: a market's index trading now says 'today, live' beside India's 'on 19 Oct'", async () => {
  const { tileWhen } = await import("../src/lib/mine.ts");
  const day = (d) => d.slice(8) + " Oct";
  assert.equal(tileWhen("2026-10-19", "2026-10-19", day, false, true), "today, live");
  assert.equal(tileWhen("2026-10-19", "2026-10-19", day, true, true), "on 19 Oct");     // closed: its day
  assert.equal(tileWhen("2026-10-16", "2026-10-19", day, false, true), "on 16 Oct");    // before the open: Friday's
  assert.equal(tileWhen("2026-10-19", "2026-10-19", day, false, false), null);          // a pair trading round the clock
  assert.match(read("src/pages/MineHome.tsx"), /closed\(tileMarket\(t\)\), !!tileMarket\(t\),/);
});

test("R71-006: a live price shows the close its move is from", () => {
  assert.match(read("src/components/Research.tsx"), /data-testid="price-prev">Previous close \{price\(q\.price - q\.change, currency\)\}/);
});

test("R71-004: the Invest home's US tab lists the US's own coming events", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /\(region !== "US" \|\| e\.kind === "us"\)/);
  assert.match(src, /<NextEvents region=\{region\} \/>/);
});

test("R71-009: Market events shows the newest index change open and folds the earlier ones", () => {
  const src = read("src/pages/trade/EventsPage.tsx");
  assert.match(src, /shown\.slice\(0, 1\)\.map\(\(c\) => card\(c, 0\)\)/);
  assert.match(src, /<Disclosure summary=\{`Earlier index changes \(\$\{Math\.min\(4, shown\.length\) - 1\}\)`\} testId="ev-index-earlier">/);
});
