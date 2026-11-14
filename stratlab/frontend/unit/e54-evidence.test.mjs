// e54 (R54, the owner's review of the live R53 decks): a company kept on its official industry is never said to be confirmed by its own
// description; the theme page says the same evidence states and counts as the deck.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("e54: each company's evidence state, from the figures' window then the membership check, not checked yet otherwise", async () => {
  const T = await import("../src/lib/theme.ts");
  const dive = { evidence: { A: "description_verified", B: "industry_code_supported" }, membership_check: { outside: { C: "industry_code_supported" }, checked: 3, total: 4, history: [] } };
  const of = T.evidenceOf(dive);
  assert.equal(of("A"), "description_verified");
  assert.equal(of("C"), "industry_code_supported");
  assert.equal(of("D"), "membership_unverified");
  assert.equal(T.evidenceLine(dive, ["A", "B", "C", "D", "D"]),
    "1 confirmed by their own description · 2 kept on their official industry only · 1 not checked yet");
  assert.equal(T.evidenceOf({}), undefined);          // a dive kept before the states were: nothing claimed
  assert.equal(T.evidenceLine({}, ["A"]), "");
  assert.equal(T.EVIDENCE_ONE.industry_code_supported, "Kept on its official industry only");
});

test("e54: the members card says each base company's evidence and the counts line", () => {
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /data-testid="member-evidence">\{EVIDENCE_ONE\[ev\(c\.ticker\)\]\}/);
  assert.match(src, /data-testid="theme-evidence">Membership: \{evLine\}/);
});
