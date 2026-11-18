// fix15 (LIVE12A, 18 Nov 2026): the scored live review of Release 69 — markets, calendars, IPOs, movers, landing. Each test reads the
// source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };

test("LIVE12A-003: a sector chart served while it is brought to the latest close says so and is read again until the new one is in", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.match(s, /updating\?: boolean;/);
  assert.match(s, /export const ROTATION_RECHECK_MS = 8000;/);
  assert.match(s, /if \(!out\?\.updating \|\| rechecks >= ROTATION_RECHECKS\) return;/);
  assert.match(s, /out\.updating && !out\.kept \? " · being brought to the latest close" : ""/);
});
