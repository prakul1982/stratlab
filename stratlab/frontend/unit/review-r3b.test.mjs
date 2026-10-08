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

test("an event on a weekend says the exchanges are closed (R3-007)", async () => {
  const { eventWhen: evWhen } = await import("../src/lib/format.ts");
  assert.equal(evWhen({ date: "2026-10-11", weekend: "Sunday" }), "Sun 11 Oct (exchanges closed)");
  assert.equal(evWhen({ date: "2026-10-12" }), "Mon 12 Oct");
});

test("an empty journal has nothing to delete (R3-019)", async () => {
  const { journalEmpty } = await import("../src/lib/journalEmpty.ts");
  assert.equal(journalEmpty({ practice_count: 0, real_count: 0, removed: 0, files: [] }), true);
  assert.equal(journalEmpty({ practice_count: 0, real_count: 3, removed: 0, files: [] }), false);
  assert.equal(journalEmpty({ practice_count: 2, real_count: 0, removed: 0, files: [] }), false);   // practice trades are kept too
  assert.equal(journalEmpty({ practice_count: 0, real_count: 0, removed: 1, files: [] }), false);
  assert.equal(journalEmpty({ practice_count: 0, real_count: 0, removed: 0, files: [{ name: "a.csv" }] }), false);
  const page = src("pages/trade/JournalPage.tsx");
  assert.match(page, /summary="How this works"/);
  assert.match(page, /!journalEmpty\(j\) && .*Delete my journal/);
});

test("one name for the person's own space, and the company lookup and the Invest home are different pages (R3-016)", async () => {
  const { MINE_NAME } = await import("../src/lib/spaces.ts");
  assert.equal(MINE_NAME, "My space");
  for (const f of ["components/Shell.tsx", "components/PageBreadcrumb.tsx", "components/LevelPrompt.tsx", "components/Tour.tsx", "pages/NavPages.tsx", "lib/title.ts", "lib/features.ts"]) {
    const text = src(f).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, "");
    assert.doesNotMatch(text, /["'`>]Mine["'`<.,]|\bMine is\b|and Mine\b/, f + " names the space \"Mine\"");
  }
  const research = src("pages/Research.tsx"), invest = src("pages/SpaceHomes.tsx");
  assert.match(research, /title="Look up a company"/);
  assert.match(invest, /title="Your research desk"/);
  // the watchlist lives on the desk (and its own page), not on both
  const lookup = research.slice(research.indexOf("export function ResearchHome"), research.indexOf("/* ================= One company"));
  assert.doesNotMatch(lookup, /title="Your watchlist"/);
});

test("library groups say what they hold, and ST S2 is spelled out (R3-014)", async () => {
  const { groupLabel, plainTerms } = await import("../src/lib/plainTerms.ts");
  assert.equal(groupLabel("NIFTY 50 stocks", 5), "5 of the NIFTY 50 stocks");
  assert.equal(groupLabel("20 US large caps", 5), "5 of the 20 US large caps");
  assert.equal(groupLabel("NIFTY 50 stocks", 50), "NIFTY 50 stocks");
  assert.equal(groupLabel("My banks", 3), "My banks · 3 in the test");
  assert.equal(groupLabel("NIFTY 50 stocks", undefined), "NIFTY 50 stocks");
  assert.equal(plainTerms("ST S2: Stage 2 + Supertrend · NIFTY 50 stocks"), "Stage 2 + Supertrend · NIFTY 50 stocks");
  assert.equal(plainTerms("Fresh ST S2"), "Fresh Stage 2 + Supertrend");
  assert.equal(plainTerms(null), "");
  for (const f of ["pages/ResearchScans.tsx", "pages/InvestorHome.tsx", "components/IdeaComposer.tsx", "pages/LibraryPage.tsx"]) {
    assert.doesNotMatch(src(f).replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ""), /["'`>]ST S2\b|\bST S2["'`<]/, f);
  }
});

test("options premiums and what is left after charges are rounded alike (R3-020)", async () => {
  const { optMoney } = await import("../src/lib/options.ts");
  assert.equal(optMoney(22455), "₹22,455");
  assert.equal(optMoney(22307.57), "₹22,308");          // was ₹22,307.57 beside ₹22,455
  assert.equal(optMoney(17414.16), "₹17,414");
  assert.equal(optMoney(-6593.4), "−₹6,593");
  assert.equal(optMoney(-92.68), "−₹92.68");            // a small figure keeps its paise: they are the answer
  assert.equal(optMoney(null), "–");
});
