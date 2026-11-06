// LIVE4 data lane: what the pages say when a source is busy, and requests that are never sent twice.
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

test("LIVE4-004: a company page standing on its last stored figures says so in one line", () => {
  const page = read("src/pages/Research.tsx");
  assert.match(page, /c\.figures_kept && <p className="k-small k-muted" data-figures-kept>/);
  assert.match(page, /the latest couldn't be read just now\./);
  assert.match(read("src/lib/research.ts"), /figures_kept\?: string \| true;/);
});

test("LIVE4-022: the company AI read is asked a few times, once per company, and business updates wait out a slow first read", async () => {
  const { AI_POLL_MS, AI_POLLS, AI_FIRST_POLLS } = await import("../src/lib/research.ts");
  // in the first 14 s: asked at 0, 1.5, 4.5 and 9.5 s (was 0, 0.8, 2.4, 5.4, 8.4, 11.4)
  let t = 0, asks = 1;
  for (let i = 0; t + (AI_FIRST_POLLS[i] ?? AI_POLL_MS) <= 14000; i += 1) { t += AI_FIRST_POLLS[i] ?? AI_POLL_MS; asks += 1; }
  assert.ok(asks <= 4, `${asks} asks in 14 s`);
  assert.ok(AI_POLL_MS * AI_POLLS >= 60_000);
  const research = read("src/lib/research.ts");
  assert.match(research, /const shared = !refresh \? aiWaits\.get\(key\) : undefined;/);       // a second caller shares the wait
  assert.match(research, /if \(shared\) \{ shared\.alive\.add\(alive\); return shared\.wait; \}/);
  const biz = read("src/components/BizUpdates.tsx");
  assert.match(biz, /bizApi\.settled\(symbol, \(\) => live\)/);
  assert.match(biz, /if \(!got\.pending \|\| i >= BIZ_PENDING_TRIES \|\| !alive\(\)\) return got;/);
});
