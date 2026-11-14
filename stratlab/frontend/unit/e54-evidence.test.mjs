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
  // l55 (R55, updated on purpose): the deck's state names, the three always named
  assert.equal(T.evidenceLine(dive, ["A", "B", "C", "D", "D"]), "1 description-verified · 2 industry-supported · 1 not checked");
  assert.equal(T.evidenceOf({}), undefined);          // a dive kept before the states were: nothing claimed
  assert.equal(T.evidenceLine({}, ["A"]), "");
  assert.equal(T.EVIDENCE_ONE.industry_code_supported, "Industry-supported (official industry only)");          // l55 (updated on purpose)
});

test("e54: the members card says each base company's evidence and the counts line", () => {
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /data-testid="member-evidence">\{EVIDENCE_ONE\[ev\(c\.ticker\)\]\}/);
  assert.match(src, /data-testid="theme-evidence">\{evLine\}\./);          // l55: "Membership checked N of M: ..." (updated on purpose)
});

// l55 (R55, the owner's review of the live R54 decks: FMCG "160 checked" = 97 + 63, said "confirmed"): the membership check's count by state,
// apart from the count with figures, and each layer's companies by state
test("l55: the members card says the membership check's count by state and each layer's states, never a confirmed total", async () => {
  const T = await import("../src/lib/theme.ts");
  const dive = { evidence: { A: "description_verified", B: "industry_code_supported" }, membership_check: { outside: { C: "industry_code_supported" }, checked: 3, total: 4, history: [] } };
  assert.equal(T.membershipLine(dive, ["A", "B", "C", "D"]), "Membership checked 3 of 4: 1 description-verified · 2 industry-supported · 1 not checked");
  assert.equal(T.evidenceLine(dive, ["A"]), "1 description-verified · 0 industry-supported · 0 not checked");
  assert.equal(T.membershipLine({}, ["A"]), "");
  for (const v of Object.values(T.EVIDENCE_ONE)) assert.doesNotMatch(v, /confirmed/i);
  const src = read("src/components/ThemeDive.tsx");
  assert.match(src, /data-testid="layer-evidence">\{evidence\}/);
  assert.match(src, /With figures: \{withFigures\.toLocaleString\("en-IN"\)\} \(the membership check reads no figures\)/);
  assert.doesNotMatch(src, /confirmed from/);
});
