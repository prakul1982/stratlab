// Lane site78: the LIVE15A / LIVE15B site findings (live review after Release 77, Thu 19 Nov 2026). Run: npm run test:unit
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

test("LIVE15A-002: a session read over 20 minutes old is labelled with its time, never shown as the market now", async () => {
  const { moodOldAt, MOOD_OLD_OPEN } = await import("../src/lib/moodCache.ts");
  const now = Date.parse("2026-11-19T09:06:00Z");                 // 14:36 IST
  const morning = { region: "IN", is_open: true, read_at: "2026-11-19T04:04:00Z", headline: "Mixed", lines: [] };     // 09:34 IST
  assert.equal(moodOldAt(morning, now), morning.read_at);
  assert.equal(moodOldAt({ ...morning, read_at: new Date(now - (MOOD_OLD_OPEN - 60) * 1000).toISOString() }, now), null);
  assert.equal(moodOldAt({ ...morning, is_open: false }, now), null);      // a closed session's read is its own
  assert.equal(moodOldAt({ ...morning, during: true }, now), null);        // already says "during the session"
  const card = read("src/pages/PulseMood.tsx");
  assert.match(card, /data-testid="pulse-mood-old">These lines and the tables below are from the \{old\} read; the index levels above are newer\./);
  assert.match(card, /old \? `At \$\{old\}: \$\{m\.headline\}`/);
  assert.match(card, /!closedDay && oldAt \? `At \$\{oldAt\}`/);
  assert.match(card, /oldAt \? `Move at \$\{oldAt\}`/);
  assert.match(read("src/pages/Research.tsx"), /<SectorsTable s=\{mood\.sectors\} closedDay=\{moodDay\(mood, pulseClosedDay\(data\?\.indices\)\)\} oldAt=\{moodOldTime\(mood, region\)\} \/>/);
});
