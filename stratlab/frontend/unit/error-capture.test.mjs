// Browser crashes to PostHog's error tracking: nothing personal leaves in a message. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const { cleanError, trackError } = await import("../src/lib/analytics.ts");

test("an error message loses emails, ids, long numbers and link details", () => {
  const out = cleanError("No profile for a.b@example.com (id 3f2a9c1e-77aa-4b2e-9d1c-0a1b2c3d4e5f, order 1234567) at https://x.example/p?q=secret");
  assert.ok(!out.includes("@example.com") && out.includes(":email"));
  assert.ok(!out.includes("3f2a9c1e") && out.includes(":id"));
  assert.ok(!out.includes("1234567") && out.includes(":n"));
  assert.ok(!out.includes("secret") && out.includes("https://x.example"));
});

test("tokens, keys, amounts, phone-like numbers and a quoted symbol are masked; ordinary words stay", () => {
  const cases = ["Bearer eyJhbGciOiJIUzI1NiIs.eyJzdWIiOiIxMjM0NTY3.SflKxwRJSMeKKF2QT4fw", "key sk_live_AbCdEfGhIjKlMnOp1234",
    "Aadhaar 1234 5678 9012", "call +91 98765 43210", "Holding value 12,34,567.89 invalid", "Holding 1,234,567 bad"];
  for (const c of cases) assert.ok(!/\d{4}|eyJ|AbCdEf/.test(cleanError(c)), `${c} -> ${cleanError(c)}`);
  assert.equal(cleanError("Cannot read properties of undefined (reading 'RELIANCE')"),
    "Cannot read properties of undefined (reading ':sym')");
  assert.equal(cleanError("TypeError: x.map is not a function at line 42"), "TypeError: x.map is not a function at line 42");
});

test("a message is cut to 200 characters, and anything that isn't text reads as text", () => {
  assert.equal(cleanError("x".repeat(500)).length, 200);
  assert.equal(cleanError(undefined), "");
  assert.equal(cleanError(42), "42");
});

test("with no analytics key a crash report does nothing and never throws", () => {
  assert.doesNotThrow(() => trackError(new TypeError("boom"), "window"));
  assert.doesNotThrow(() => trackError("plain text", "promise"));
  assert.doesNotThrow(() => trackError(null, "page"));
});
