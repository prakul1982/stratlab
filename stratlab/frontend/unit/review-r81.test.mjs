// Round 81 (22 Oct 2026): the owner's app and the US close — the frontend side.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R81-019: a company search with few matches points to the other market's tab", () => {
  const s = read("src/components/CompanySearch.tsx");
  assert.match(s, /rows\.length <= 2 && <p className="small muted results-none" data-testid="other-market">/);
  assert.match(s, /"A US company\? Search it on the US tab\."/);
});

test("R81-020: the journal offers the tax report's newer trades and says how far each goes", () => {
  const s = read("src/pages/trade/JournalPage.tsx");
  assert.match(s, /setTaxLast\(t\.last_trade \?\? null\)/);
  assert.match(s, /taxLast\.slice\(0, 10\) > newestReal/);
  assert.match(s, /Bring in the newer ones/);
  assert.match(s, /t\.src !== "practice"/);
});

test("R81-012: an options trade's note about paused prices is shown on the session page", () => {
  assert.match(read("src/pages/OptionsSession.tsx"), /\{x\.note && <span className="k-note" data-testid="trade-gap">\{x\.note\}\.<\/span>\}/);
});

test("R82-005: on Free and Basic the instrument search says F&O contracts are on Pro", () => {
  const s = read("src/components/InstrumentSearch.tsx");
  assert.match(s, /const fnoLocked = market\.id === "IN" && !!me && !me\.plan_info\?\.features\?\.fno;/);
  assert.match(s, /\{fnoLocked && !kinds && <p className="k-small k-muted k-pad" role="presentation" data-testid="fno-locked">Futures and options contracts are on the Pro plan\.<\/p>\}/);
});

test("R82-009: Pro's AI builds line names the daily cap the Plans page names", () => {
  assert.match(read("src/components/IdeaComposer.tsx"), /`Unlimited AI builds\$\{u\.ai_builds_per_day \? ` \(up to \$\{u\.ai_builds_per_day\} a day\)` : ""\}`/);
});
