// price102 (owner, 28 Nov: "all ok to do", GTM P1-P3): the founding-member prices in words, on the plan cards' locks and in the lock wording
// of Free's one theme deck a month. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { foundingCardNote, foundingDeadline, foundingLine, foundingOf, foundingYear, studentLine } = await import("../src/lib/founding.ts");
const { planPriceLine } = await import("../src/lib/planPrice.ts");
const { companyDeckLock, deepDiveLimitLine, pptxLock } = await import("../src/lib/account.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

const F = { open: true, until: "2026-12-31T18:29:00+00:00", seats: 100, prices: { basic: 4999, pro: 14999 }, was: { basic: 6999, pro: 19999 } };
const INR = { symbol: "₹", name: "Indian rupee", basic: 699, pro: 1999, basic_year: 6999, pro_year: 19999, charged_in: "INR", yearly_charged_in: "INR" };

test("the founding offer runs while the server says so and not past its end on this page's clock", () => {
  assert.equal(foundingOf({ founding: F }, Date.parse("2026-12-31T18:28:59Z")), F);
  assert.equal(foundingOf({ founding: F }, Date.parse("2026-12-31T18:29:00Z")), null);          // 31 Dec 2026, 11:59 pm IST
  assert.equal(foundingOf({ founding: null }), null);
  assert.equal(foundingOf({ founding: { ...F, open: false } }), null);
  assert.equal(foundingOf(null), null);
});

test("the words say the prices, the old prices, the deadline and the first 100 members, facts only", () => {
  assert.equal(foundingDeadline(F), "31 Dec 2026, 11:59 pm IST");
  assert.equal(foundingLine(F), "Founding-member prices for the first 100 members, until 31 Dec 2026, 11:59 pm IST: Basic ₹4,999 a year (was ₹6,999), "
    + "Pro ₹14,999 a year (was ₹19,999). The price stays the same for as long as you renew. Monthly prices don't change.");
  assert.equal(foundingCardNote(F, "pro"), "Founding-member price for the first 100 members, until 31 Dec 2026, 11:59 pm IST. Renews at ₹14,999 a year for as long as you keep it.");
  assert.equal(foundingYear(F, "basic"), "₹4,999 a year (founding-member price until 31 Dec 2026, 11:59 pm IST, for the first 100 members; was ₹6,999)");
  assert.match(studentLine(), /^Student\? Basic is ₹2,499 a year for students, approved by hand/);
  for (const t of [foundingLine(F), foundingCardNote(F, "basic"), studentLine()]) assert.doesNotMatch(t, /\b(hurry|only|last chance|buy|sell)\b/i);
});

test("a lock's price line gives the founding year while it runs, and the standard one after", () => {
  const p = { currencies: { INR }, offer: { mode: "paid", payments: true, yearly: true, founding: F }, usd_inr: { rate: 88 } };
  assert.equal(planPriceLine("basic", p), "Basic is ₹699 a month (about $8) or ₹4,999 a year (founding-member price until 31 Dec 2026, 11:59 pm IST, for the first 100 members; was ₹6,999).");
  const after = { ...p, offer: { ...p.offer, founding: null } };
  assert.equal(planPriceLine("basic", after), "Basic is ₹699 a month (about $8) or ₹6,999 a year (about $80).");
});

test("Free's one theme deck a month: the locks say where a company's deck and PowerPoint are", () => {
  assert.equal(companyDeckLock(), "A company's slide deck is on Basic: 5 a month, as PDF or PowerPoint. Free makes 1 theme deck a month, as a PDF.");
  assert.match(pptxLock(), /^PowerPoint decks are on Basic: 5 a month\. Free makes 1 theme deck a month as a PDF, each page marked "Made with StratLab · stratlab\.studio"/);
  assert.equal(deepDiveLimitLine(1, 1, 0, 1, false), "Companies opened this month: 1 of 1 (limit reached). " + companyDeckLock() + " Opening a company again this month doesn't count.");
  assert.match(deepDiveLimitLine(1, 15, 1, 5), /Decks: 1 of 5;/);
});

test("the plan cards, the table and the pages say Free has one theme deck, never none", () => {
  const core = read("src/lib/planCore.ts");
  assert.match(core, /deepdives_per_month: 1, decks_per_month: 1,/);
  for (const f of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) {
    assert.doesNotMatch(read(f), /Slide decks are on Basic and Pro\./, f);
    assert.match(read(f), /Free makes one theme deck a month as a PDF, marked "Made with StratLab"/, f);
  }
  assert.match(read("src/components/PlanCompare.tsx"), /a theme's PDF, marked/);
});
