// Round 6, the owner's review on the live site (8 Oct 2026): frontend side, each on the reviewer's real example.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("Admin's AI tile counts paused and out-of-quota providers honestly (R6O-003)", async () => {
  const { aiTile } = await import("../src/pages/admin/attention.ts");
  const row = (label, extra) => ({ label, configured: true, in_use: true, model: "m", last_error: null, answering: true, ...extra });
  const ai = [row("Groq"), row("Hugging Face", { paused_models: 1 }), row("Cerebras", { answering: false, quota_used: true, state_text: "Free quota used up" }),
    { label: "Unset", configured: false, in_use: false, model: null, last_error: null }];
  const t = aiTile(ai);
  assert.equal(t.detail, "2 of 3 answering · 1 out of free quota · 1 with a model paused");
  assert.equal(t.state, "warn");
  assert.equal(aiTile([row("Groq"), row("Mistral")]).state, "ok");
  assert.equal(aiTile([row("Groq", { paused_models: 2 })]).state, "warn");          // a paused model is never "OK, all answering"
});

test("A results day whose quarter is already in the table reads as filed (R6O-016)", async () => {
  const { resultsFiled } = await import("../src/lib/researchFormat.ts");
  assert.equal(resultsFiled("2026-10-08", "Sep 2026", "2026-10-08"), true);         // TCS at 23:47 IST, Sep 2026 in the table
  assert.equal(resultsFiled("2026-10-08", "Jun 2026", "2026-10-08"), false);        // still to come: the table ends in June
  assert.equal(resultsFiled("2026-10-29", "Jun 2026", "2026-10-08"), false);        // a day ahead
  assert.equal(resultsFiled(null, "Sep 2026", "2026-10-08"), false);
  assert.match(read("src/lib/mine.ts"), /results_out/);                           // filed results aren't "coming up"
});
