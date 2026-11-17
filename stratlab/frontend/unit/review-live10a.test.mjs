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
  // the one-line title never shares its line with a button it could run into (CI UI checker, Release 63: 20px into "Open" at 1280)
  const mine = read("src/pages/MineHome.tsx");
  assert.doesNotMatch(mine, /<CardHead title="Paper sessions" actions=/);
  assert.match(mine, /<Link className="btn quiet sm" to="\/paper">Open paper sessions<\/Link>/);
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

// updated on purpose (Release 63 CI, e2e ia2 item 39): the owner retired the grey ▲/▼ pill (item 39, 30 Oct), so a rise in a bad-news count is
// coloured by meaning (red), the reviewer's other choice, not drawn plain
test("LIVE10A-024: a rise in stocks that fell, 52-week lows or down 4% moves is red, a fall green, never the grey pill", () => {
  const stat = read("src/components/kit/Stat.tsx");
  assert.match(stat, /const tone = badRise && dir !== "flat" \? \(dir === "up" \? "down" : "up"\) : dir;/);
  assert.match(stat, /<span className=\{`k-delta \$\{tone\}`\}>/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<Delta badRise=\{p\.tone === "down"\}/);
  assert.match(read("src/pages/PulseMood.tsx"), /<Delta badRise=\{r\.key === "dec" \|\| r\.key === "lows"\}/);
});

test("LIVE10A-021: the theme ideas are a row of their own under Map it", () => {
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /<FormActions>\n\s+<button className="btn" disabled=\{busy\}>\{busy \? "Mapping…" : "Map it"\}<\/button>\n\s+<\/FormActions>/);
  assert.match(page, /<div className="k-row theme-ideas" data-testid="theme-ideas">/);
  assert.match(read("src/styles.css"), /\.theme-ideas \{ grid-column: 1 \/ -1;/);
});

test("LIVE10A-012: a heatmap group head too narrow for its name shows the short one", async () => {
  const { groupWords } = await import("../src/lib/heatmap.ts");
  const w = (t) => t.length * 6;                // 6px a letter at 10px
  assert.equal(groupWords("Fast Moving Consumer Goods", 90, w), "FMCG");
  assert.equal(groupWords("Fast Moving Consumer Goods", 400, w), "Fast Moving Consumer Goods");
  assert.equal(groupWords("Power", 20, w), "Power");                                   // no short name: as it is (the CSS cuts it)
  assert.match(read("src/components/chart/Treemap.tsx"), /<span className="hm-group-name">\{groupWords\(g\.name,/);
});

test("LIVE10A-040: a theme whose companies are all of one industry has no Industry column", () => {
  const dive = read("src/components/ThemeDive.tsx");
  assert.match(dive, /const oneIndustry = new Set\(groups\.flatMap\(\(g\) => g\.rows\.map\(indOf\)\)\)\.size <= 1;/);
  assert.match(dive, /\.\.\.\(oneIndustry \? \[\] : \[\{ key: "i", header: "Industry"/);
});

test("LIVE10A-039: the index-change notices say what the press release holds, without an excuse", () => {
  const page = read("src/pages/trade/EventsPage.tsx");
  assert.doesNotMatch(page, /couldn't be read from it here/);
  assert.match(page, /Each press release lists the stocks going in and out of the index\./);
});

test("LIVE10A-037: a results row's purpose sits on its own line under the name, never cut after it", () => {
  const css = read("src/styles-invest.css");
  assert.match(css, /\.res-sub > \.res-name, \.res-sub > \.res-purpose \{ display: block;/);
  assert.doesNotMatch(css, /\.res-name \+ \.res-purpose::before \{ content: " · "; \}/);
  assert.match(css, /\.res-name \+ \.res-purpose\.res-plain \{ display: none; \}/);          // a plain results meeting keeps two lines
});
