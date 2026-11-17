// fix13 (LIVE11A, 18 Nov 2026): the scored live review of Release 66. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE11A-001: a closed session's final read is not 'Reading the market again' hours later", async () => {
  const { moodStale, MOOD_STALE_SHUT } = await import("../src/lib/moodCache.ts");
  const now = Date.parse("2026-11-17T23:05:00Z");
  const old = new Date(now - (MOOD_STALE_SHUT + 12 * 3600) * 1000).toISOString();
  const m = { region: "IN", is_open: false, read_at: old, headline: "x", lines: [] };
  assert.equal(moodStale(m, now), true);                                   // not final: a fresh read is asked for
  assert.equal(moodStale({ ...m, final: true }, now), false);              // the session's final read: shown as it is
  assert.equal(moodStale({ ...m, final: true, refreshing: true }, now), true);
});
