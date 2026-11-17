// LIVE10A (17 Nov 2026): the scored live review of Release 60. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-001: a market-hours mood copy served after the close says it was read during the session", () => {
  assert.match(read("src/pages/PulseMood.tsx"), /Read \{readAt\}\{m\.during \? ", during the session" : ""\}/);
  assert.match(read("src/lib/research.ts"), /during\?: boolean;/);
});

test("LIVE10A-010: while the newer session trades, the note says its figures so far are being read", async () => {
  const { moodBehindNote } = await import("../src/lib/pulseMood.ts");
  const dayText = (d) => (d === "2026-11-16" ? "16 Nov" : "17 Nov");
  assert.equal(moodBehindNote({ session: "2026-11-16", behind: "2026-11-17", is_open: true }, null, dayText),
    "These figures are of the 16 Nov session; the 17 Nov session's figures so far are being read.");
  assert.equal(moodBehindNote({ session: "2026-11-16", behind: "2026-11-17", is_open: false }, "2026-11-17", dayText),
    "These figures are of the 16 Nov session; the 17 Nov session's are being read.");
});

test("LIVE10A-002: on a desktop the Lab notes sit left of a docked Markets panel, above the Markets button, and the page makes room", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.ln-btn \{ right: var\(--mw-dock, 0px\); \}/);
  assert.match(css, /\.ln-panel \{ position: fixed; right: calc\(var\(--mw-dock, 0px\) \+ 52px\); bottom: 76px;/);
  assert.match(css, /body:has\(\.ln-panel:not\(\[hidden\]\)\) \.shell > \.main \{ padding-right: 448px; \}/);
});

test("LIVE10A-003: a deck press over the month's count shows the plan line beside the buttons; /plans states a Free account's grace", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /if \(\(e as \{ status\?: number \}\)\?\.status === 402\) setSpent\(/);
  assert.match(dive, /\{spent && <div className="theme-wb-lock" role="status" data-testid="deck-spent"><PlanNote plan="basic">\{spent\}<\/PlanNote>/);
  const cmp = read("src/components/PlanCompare.tsx");
  assert.match(cmp, /\$\{changeCount\(kept\.before\)\} for you until \$\{graceDay\}/);
  const plans = read("src/pages/PlansPage.tsx");
  assert.match(plans, /grace=\{me\?\.free_change\}/);
  assert.match(plans, /Slide decks are on Basic and Pro\{deckGrace \? ` \(your Free account keeps \$\{deckGrace\}\)` : ""\}/);
});

test("LIVE10A-008: a dive being read again behind the page is asked for quietly, and the price bar shows for the first read only", () => {
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /if \(d\.updating && \+\+diveTries <= DIVE_TRIES\) diveTimer = setTimeout\(\(\) => getDive\(false\), DIVE_EVERY_MS\);/);
  assert.match(page, /if \(!tries\) setPricesBusy\(true\);/);
  assert.match(page, /setPrices\(p\);\n\s+setPricesBusy\(false\);\n\s+if \(p\.pending > 0 && \+\+tries < PRICE_TRIES\)/);
});

test("LIVE10A-020: a US day that is no session gets no chip; India keeps Saturday's; an empty Usual move column is dropped", async () => {
  const R = await import("../src/lib/resultsRows.ts");
  const days = [{ date: "2026-11-19", count: 3, session: true }, { date: "2026-11-22", count: 1, session: false }, { date: "2026-11-26", count: 2, session: false }];
  assert.deepEqual(R.laterDays(days, "2026-11-17", "US"), ["2026-11-19"]);
  assert.deepEqual(R.laterDays(days, "2026-11-17", "IN"), ["2026-11-19", "2026-11-22", "2026-11-26"]);
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /laterDays\(\(data\?\.weeks \?\? \[\]\)\.flatMap\(\(w\) => w\.days \?\? \[\]\), todayIn\(region\), region\)/);
  assert.match(page, /\.\.\.\(mvEmpty \? \[\] : \[\{ key: "mv", header: "Usual move"/);
});

test("LIVE10A-026: My space's market tiles go six across by the card's width and a name never wraps", () => {
  const css = read("src/styles.css");
  assert.match(css, /\[data-testid="mine-markets"\] \{ container-type: inline-size; \}/);
  assert.match(css, /@container \(min-width: 720px\) \{ \.mine-markets \{ grid-template-columns: repeat\(6, minmax\(0, 1fr\)\); \} \}/);
  assert.doesNotMatch(css, /@media \(min-width: 1360px\) \{ \.mine-markets/);
  assert.match(css, /\.mine-mkt > \.k-stat-k \{ white-space: nowrap;/);
  assert.match(css, /\[data-testid="mine-paper"\] \.k-card-title \{ white-space: nowrap; \}/);
});

test("LIVE10A-030/041: Movers says the market is open beside the last close, and a Free plan line is drawn before the first read", () => {
  const page = read("src/pages/MoversPage.tsx");
  assert.match(page, /\{open \? ", the last close · the market is open; the lists are redrawn after today's close" : ""\}/);
  assert.match(page, /const locked = !!view\?\.locked \|\| \(!view && \(me\?\.paid_plan \?\? me\?\.plan\) === "free"\);/);
});

test("LIVE10A-023: a Settings change says Saved or that it couldn't save, and an unset choice says so", () => {
  const app = read("src/lib/app.tsx");
  assert.match(app, /try \{ await sent; return true; \} catch \(e\) \{ if \(!quiet\) fail\(e\); return false; \}/);
  const page = read("src/pages/SettingsPage.tsx");
  assert.match(page, /data-testid="prefs-saved">\{saved === "saving" \? "Saving…" : saved === "saved" \? "Saved" : "Couldn't save the change\. Pick it again to retry\."\}/);
  assert.equal((page.match(/"Not set yet: pick one\."/g) || []).length, 2);
});
