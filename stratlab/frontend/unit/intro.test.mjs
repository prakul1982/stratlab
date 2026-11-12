// Release 42, lane i1 (owner, 12 Nov: "the intro we have on the website itself is also trash, it only shows like 5 steps to get in or
// smth, fix that too"): one short tour per space, each step on a real page pointing at a real control, offered the first time a
// person is in that space, and all of them from "Take the tour". These check the step lists, the plan notes and the rules.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const I = await import("../src/lib/intro.ts");
const { locate } = await import("../src/lib/nav.ts");
const { gateFor } = await import("../src/lib/gates.ts");
const { LIMITS, PLAN_IDS } = await import("../src/lib/plans.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
const ALL = I.TOUR_IDS.flatMap((t) => I.TOURS[t].steps.map((s) => ({ tour: t, ...s })));

test("four tours, one per space, each with what is worth knowing there (the old tour was five steps of menu)", () => {
  assert.deepEqual(I.TOUR_IDS, ["mine", "trade", "invest", "money"]);
  for (const t of I.TOUR_IDS) {
    const tour = I.TOURS[t];
    assert.equal(tour.id, t);
    assert.ok(tour.steps.length >= 4 && tour.steps.length <= 6, `${t}: ${tour.steps.length} steps`);
    assert.ok(tour.name && tour.line.endsWith("."), t);
  }
  assert.ok(ALL.length >= 18, `${ALL.length} steps in all`);
  assert.equal(new Set(ALL.map((s) => s.id)).size, ALL.length, "step ids are unique");
  // what StratLab is for, not only its chrome: the real strengths each have a step
  const titles = ALL.map((s) => `${s.title} ${s.body}`).join("\n");
  for (const must of [/deep dive/i, /AI read/i, /Themes?/, /slides/i, /Heatmap|tile/i, /Mood, Breadth, Sectors and Flows/, /Results/, /IPO/, /plain words/,
    /past prices|real prices/, /paper trad/i, /options|straddle/i, /holdings/i, /capital gains|Capital gains/, /net worth|own and owe/i, /brief/i, /Ask or do anything/, /Market Watch/])
    assert.match(titles, must);
});

test("every step's page is a real page of the menu map, and a step not on a page is about the menu or the top bar", () => {
  for (const s of ALL) {
    const page = s.go ?? s.via?.page;
    if (page) assert.ok(page === "/mine" || locate(page), `${s.id}: ${page} is not in the menu map`);
    else assert.ok(s.at.every((sel) => /^\.(sidebar|topbar|mw-launch)/.test(sel)), `${s.id}: a step with no page points at the menu, the top bar or Market Watch`);
    assert.ok(s.at.length > 0, s.id);
    // steps on a page point inside the page
    if (page) assert.ok([...s.at, s.or ?? "main"].every((sel) => sel.startsWith("main")), `${s.id}: ${s.at}`);
    // a step in the menu opens it on a phone
    if (s.at.some((sel) => sel.startsWith(".sidebar")) && !s.at.some((sel) => sel.startsWith(".topbar"))) assert.ok(s.menu, `${s.id}: in the menu, so it opens the menu on a phone`);
    assert.equal(I.onStepPage(s, page ?? "/anywhere") || !!s.via, true, `${s.id}: its own page counts as its page`);
  }
  // the company step is happy on any company's page and opens the first suggestion from Look up a company
  const company = ALL.find((s) => s.id === "company");
  assert.ok(I.onStepPage(company, "/research/US/ANY") && I.onStepPage(company, "/research/IN/ANY") && !I.onStepPage(company, "/research/IN/ANY/deep"));
  assert.equal(company.via.page, "/research");
  // no company or theme is named in the steps: the company comes from the page's own suggestions
  assert.doesNotMatch(read("src/lib/intro.ts"), /RELIANCE|TCS|HDFC|INFY|NVDA|AAPL|defence|railways/i);
});

test("plan gating: no step points at a page its plan locks as a whole, and every step on a part-locked page says what is locked", () => {
  for (const s of ALL) {
    assert.equal(I.lockedWhole(s), false, `${s.id} points at a locked page`);
    const page = s.go ?? s.via?.page;
    const gate = page && gateFor(page);
    if (gate) assert.equal(s.flag, gate.feature, `${s.id}: ${page} is part ${gate.feature}: the step carries it`);
  }
  // on a plan that lacks it, the note says the feature and its plan, in facts
  const options = ALL.find((s) => s.id === "options");
  assert.equal(I.lockLine(options, { options: false }), "Options paper trading at set times: on the Basic plan.");
  assert.equal(I.lockLine(options, { options: true }), null);
  assert.equal(I.lockLine(options, null), null, "nothing said before the plan is known");
  const tools = ALL.find((s) => s.id === "taxtools");
  assert.match(I.lockLine(tools, { tax_tools: false }), /: on the Pro plan\.$/);
  // a Free limit is said on Free only
  const company = ALL.find((s) => s.id === "company");
  // (updated on purpose, FREE-TIER: Free has 1 deep dive a month and no slide decks)
  assert.deepEqual(I.planLines(company, {}, "free"), [`On Free: ${LIMITS.free.deepdives_per_month} deep dive a month; slide decks are on Basic.`]);
  const tax = ALL.find((s) => s.id === "tax");
  assert.equal(I.lockLine(tax, { tax_export: false }), "Tax report downloads: CSV and PDF: on the Basic plan.");
  assert.deepEqual(I.planLines(company, {}, "pro"), []);
  assert.ok(PLAN_IDS.includes("basic"));
});

test("facts only: no advice, no buy or sell words, no tips, in any step or tour line", () => {
  const text = [...I.TOUR_IDS.map((t) => I.TOURS[t].line), ...ALL.flatMap((s) => [s.title, s.body, s.phone ?? "", s.free ?? "", s.act?.label ?? ""])].join("\n");
  assert.doesNotMatch(text, /\b(buy|buys|buying|sell|sells|selling|should|recommend\w*|best|tips?|profit(able)?|winning|beat)\b/i);
  // the menu's words for the things it names
  assert.match(text, /Dark mode is in Settings, under Experience\./);
  assert.match(text, /The Account button opens your plan, Settings and Help\./);
});

test("the welcome answer picks the tour; the state remembers done, waved away and where a tour stopped", () => {
  assert.equal(I.tourForFocus("trade"), "trade");
  assert.equal(I.tourForFocus("money"), "money");
  assert.equal(I.tourForFocus("both"), "mine");
  assert.equal(I.tourForFocus(null), "mine");
  let s = I.parseState(null);
  assert.deepEqual(s, { on: false, done: [], no: [], at: null });
  assert.equal(I.offerFor(s, "/invest"), null, "no offers to someone who never started the intro (every existing account)");
  s = I.started(s, "trade");
  assert.equal(s.on, true);
  s = I.finished(s, "trade");
  assert.equal(I.offerFor(s, "/trade"), null, "a space whose tour was taken");
  assert.equal(I.offerFor(s, "/invest/heatmap"), "invest");
  assert.equal(I.offerFor(s, "/money"), "money");
  assert.equal(I.offerFor(s, "/mine"), "mine");
  assert.equal(I.offerFor(s, "/calendar"), null, "a page every space shares belongs to none");
  assert.equal(I.offerFor(s, "/settings"), null);
  s = I.declined(s, "money");
  assert.equal(I.offerFor(s, "/holdings"), null, "Not now is kept");
  s = I.stopped(s, "invest", 2);
  assert.deepEqual(s.at, { tour: "invest", step: 2 });
  assert.equal(I.offerFor(s, "/invest"), null, "a tour closed part way isn't offered again by itself");
  s = I.started(s, "invest");
  assert.ok(!s.no.includes("invest"), "picking it from the list takes back its Not now");
  s = I.finished(s, "invest");
  assert.equal(s.at, null, "finished: nothing to resume");
  // what was stored survives a round trip, and junk reads as nothing
  assert.deepEqual(I.parseState(JSON.stringify(s)), s);
  assert.deepEqual(I.parseState("{bad"), { on: false, done: [], no: [], at: null });
  assert.deepEqual(I.parseState(JSON.stringify({ on: 1, done: ["trade", "nope"], no: 3, at: { tour: "x", step: 1 } })), { on: true, done: ["trade"], no: [], at: null });
});

test("the tours' note: keyboard, a live region, a focus trap, and it waits for its page instead of pointing at nothing", () => {
  const coach = read("src/components/kit/Coachmark.tsx");
  assert.match(coach, /aria-live="polite"/);
  assert.match(coach, /useDialogFocus\(note, true, \{ onEscape: \(\) => close\.current\(\), coach: true \}\)/);
  assert.match(coach, /const WAIT = 5000, FALLBACK_AFTER = 1800;/);
  assert.match(coach, /if \(!box \|\| !hole \|\| !found\) return;/, "nothing is placed in the middle first while the page loads");
  // content that loads late (My Holdings' figures above its import row) brings the thing back into view, unless the person scrolled
  assert.match(coach, /const SETTLE = 4000;/);
  assert.match(coach, /for \(const ev of \["wheel", "touchmove", "keydown", "pointerdown"\]\) window\.addEventListener\(ev, theirs/);
  assert.match(coach, /if \(r\.top < 0 \|\| r\.top >= vh - EDGE \|\| r\.bottom <= 0\) \{/);
  const tour = read("src/components/Tour.tsx");
  assert.match(tour, /e\.key === "ArrowRight" && !last/);
  assert.match(tour, /e\.key === "ArrowLeft" && i > 0/);
  assert.match(tour, /if \(paused\) return null;/);
  // it ends where it began, so the welcome tour hands over to the home page's checklist
  assert.match(tour, /if \(`\$\{loc\.pathname\}\$\{loc\.search\}` !== from\.current\) nav\(from\.current\);/);
  // the offer floats (no layout shift) under every dialog, and takes no focus
  const css = read("src/components/intro.css");
  assert.match(css, /\.intro-offer \{ position: fixed; z-index: 54;/);
  assert.doesNotMatch(read("src/components/IntroOffer.tsx"), /autoFocus|\.focus\(/);
  // "Take the tour" opens the list; a space's id opens its tour
  const onb = read("src/components/Onboarding.tsx");
  assert.match(onb, /setTour\(t && TOUR_IDS\.includes\(t\) \? \{ tour: t, step: 0 \} : "pick"\)/);
});
