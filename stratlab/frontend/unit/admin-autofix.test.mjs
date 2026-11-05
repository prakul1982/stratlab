// Admin's checks (owner, 4 Nov: "a whole check on admin pages — there are a lot of warnings") and the self-healing on top of them
// ("fix it so that in real time everything is fixed, and only if it's not able to, then bug me"). Every value is fixed; no clock matters.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

const ai = (name, result, extra = {}) => ({ name, label: name, configured: true, in_use: true, model: "m", last_error: null, answering: result === "working", result, ...extra });
const ov = (server = {}) => ({ server: { kite_ready: true, kite_token_day: null, feed_connected: true, live_sessions: 0, india_sessions: 0,
  auto_login: { at: null, ok: true, message: "ok" }, auto_login_configured: true, billing_enabled: true, billing_hook: { mode: "live", last_at: "2026-10-28" },
  ai: [ai("groq", "working")], research: { finnhub: true }, recent_errors: [], server_started_at: "2026-11-04T22:00:00+05:30", ...server }, stats: {} });

test("The AI light is amber only when a provider needs the owner; credit, rests and passing faults are notes", async () => {
  const { aiTile, attention, needsOwner } = await import("../src/pages/admin/attention.ts");
  const live = [ai("groq", "working"), ai("gemini", "working"), ai("zai", "quota"), ai("hf", "quota"), ai("mistral", "untested", { answering: true }), ai("sambanova", "untested", { answering: true })];
  assert.deepEqual([aiTile(live).state, aiTile(live).detail], ["ok", "2 of 6 working · 2 out of credit · 2 not tried yet"]);
  const key = ai("nvidia", "failed", { state_text: "Failing: 401 invalid key" });
  assert.equal(needsOwner(key), true);
  assert.equal(needsOwner(ai("gemini", "failed", { state_text: "Failing: server error 503 (high demand)" })), false);
  assert.equal(aiTile([...live, key]).state, "warn");
  assert.ok(attention(ov({ ai: [...live, key] }), null, []).some((a) => a.text.startsWith("AI, nvidia: Failing: 401 invalid key")));
});

test("The self-healing's escalations are listed once under Needs your attention, with what was tried and the action", async () => {
  const { attention } = await import("../src/pages/admin/attention.ts");
  const key = ai("mistral", "failed", { state_text: "Failing: 401 invalid key" });
  const autofix = { trying: [], history: [], escalated: [
    { id: "ai:mistral", name: "AI provider Mistral", problem: "rejected its key (401)", since: null, to: "/admin/system", tries: 0, of: 3, next: null,
      action: "Make a new key at console.mistral.ai, put it in Railway → Variables as MISTRAL_API_KEY.", mailed: "2026-11-04T17:00:00+00:00" },
    { id: "platform", name: "Feature check", problem: "1 check failing after a retry: Prices: FX", since: null, to: "/admin/system", tries: 0, of: 3, next: null,
      action: "Open Admin → System → Check every feature.", mailed: null },
    { id: "job:ipo", name: "IPOs", problem: "The SEC is having trouble (500).", since: null, to: "/admin/data", tries: 3, of: 3, next: null, action: "x", mailed: "2026-11-04" }] };
  const todo = attention(ov({ ai: [ai("groq", "working"), key], autofix }), null, []);
  const texts = todo.map((a) => a.text);
  // the provider's escalation replaces its own AI line (said once), the feature check gets a line, a job's is left to its own Problem line
  assert.equal(texts.filter((t) => /Mistral|mistral/.test(t)).length, 1, texts.join("\n"));
  const m = todo.find((a) => a.text.startsWith("AI provider Mistral"));
  assert.ok(m.bad && m.to === "/admin/system" && m.label === "System");
  assert.equal(m.text, "AI provider Mistral: rejected its key (401). Only you can fix this; you were emailed. Make a new key at console.mistral.ai, put it in Railway → Variables as MISTRAL_API_KEY.");
  assert.ok(texts.some((t) => t.startsWith("Feature check: 1 check failing after a retry: Prices: FX. Only you can fix this. Open Admin")));
  assert.ok(!texts.some((t) => t.startsWith("IPOs:")));
});

test("Overview shows each automatic fix in a short history: what is being fixed, then what happened", async () => {
  const { fixRows } = await import("../src/pages/admin/attention.ts");
  assert.deepEqual(fixRows(undefined), []);
  const rows = fixRows({ escalated: [],
    trying: [{ id: "job:breadth", name: "Market breadth", problem: "US: 3 stocks failed", since: "2026-11-04T13:30:00+00:00", to: "/admin/data", tries: 1, of: 3,
      next: "2026-11-04T14:30:00+00:00" }],
    history: [{ at: "2026-11-04T13:45:00+00:00", id: "job:ipo", name: "IPOs", event: "fixed", text: "re-ran the job at 4 Nov 7:00 PM IST — fixed", to: "/admin/data" },
      { at: "2026-11-04T13:40:00+00:00", id: "platform", name: "Feature check", event: "escalated", text: "emailed you: Open Admin → System.", to: "/admin/system" }] });
  assert.deepEqual(rows.map((r) => [r.name, r.tone, r.what]), [
    ["Market breadth", "plain", "Being fixed: US: 3 stocks failed. Tried 1 of 3 times. Next try 4 Nov, 20:00 IST."],
    ["IPOs", "ok", "Re-ran the job at 4 Nov 7:00 PM IST — fixed"],
    ["Feature check", "warn", "Couldn't fix it; emailed you: Open Admin → System."]]);
  const page = read("src/pages/admin/OverviewSection.tsx");
  assert.match(page, /<Card label="Automatic fixes">/);
  assert.match(page, /<DataTable label="Automatic fixes" rows=\{fixes\}/);           // a table with a header row, stacked on a phone
  assert.match(page, /Nothing needed fixing in the last 7 days\./);
});
