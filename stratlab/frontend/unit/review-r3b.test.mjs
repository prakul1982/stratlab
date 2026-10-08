import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const src = (p) => readFileSync(new URL("../src/" + p, import.meta.url), "utf8");

// Round 3, builder B: connection check wording, events on weekends, plans interest, space names, tap targets, journal, options.

test("Connection check: the server's address and the hosting steps are for admins only (R3-009)", async () => {
  const { serverRow, aiMissingRow } = await import("../src/lib/connection.ts");
  const person = [serverRow(true, false, "https://api.example.app"), serverRow(false, false, "https://api.example.app"), aiMissingRow(false)];
  for (const r of person) assert.doesNotMatch(r.d, /https?:|api\.example|Railway|GROQ|FRONTEND_ORIGIN|redeploy|Variables/i);
  assert.equal(serverRow(true, false, "https://api.example.app").d, "Online");
  assert.equal(aiMissingRow(false).s, "warn");                 // nothing a person can fix is a "Problem"
  assert.equal(serverRow(true, true, "https://api.example.app").d, "api.example.app");
  assert.match(serverRow(false, true, "x").d, /Railway/);
  assert.match(aiMissingRow(true).d, /GROQ_API_KEY/);
});
