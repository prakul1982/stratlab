import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// UI-FIX-1: the layout problems the UI checker (e2e/ui-lint.spec.ts) found, and the checker itself as a blocking CI check

test("UI-FIX-1 (R9): a grid of equal tiles never leaves the last one alone on its line", async () => {
  const { fillCols } = await import("../src/lib/noOrphan.ts");
  assert.equal(fillCols(4, 3), 2);          // 3 + 1 becomes 2 + 2
  assert.equal(fillCols(5, 4), 3);          // 4 + 1 becomes 3 + 2
  assert.equal(fillCols(6, 5), 3);          // 5 + 1 becomes 3 + 3
  assert.equal(fillCols(7, 3), 3);          // 3 + 3 + 1 would leave one, but 2 + 2 + 2 + 1 does too: the widest count that does not is kept
  assert.equal(fillCols(4, 4), 4);          // a full row stays
  assert.equal(fillCols(3, 4), 4);          // fewer tiles than columns: untouched
  assert.equal(fillCols(8, 3), 3);          // 3 + 3 + 2 is fine
  for (let n = 4; n <= 14; n++) for (let fit = 3; fit <= 6; fit++) {
    const c = fillCols(n, fit);
    assert.ok(c <= fit && c >= 2, `${n} in ${fit}`);
    if (n > fit) assert.ok(n % c !== 1 || c === fit, `${n} tiles in ${fit} columns gave ${c}, leaving one alone`);
  }
});

test("UI-FIX-1 (R9): the stat rows, form grids, health grids and tile grids use it", () => {
  assert.match(read("src/components/kit/Stat.tsx"), /useNoOrphan/);
  assert.match(read("src/components/kit/Form.tsx"), /useNoOrphan/);
  assert.match(read("src/components/kit/Health.tsx"), /useNoOrphan/);
  assert.match(read("src/components/TileGrid.tsx"), /useNoOrphan/);
  assert.match(read("src/pages/NavPages.tsx"), /<TileGrid className="nav-cards" fill>/);
  assert.match(read("src/components/Explore.tsx"), /<TileGrid className="explore-grid">/);
});

test("UI-FIX-1 (R1): the Invest home pairs short cards with short cards, and the notebook's checks are two columns of their own", () => {
  const home = read("src/pages/SpaceHomes.tsx");
  assert.ok(home.indexOf("<NextEvents region={region} />") < home.indexOf("<ResultsToday region={region} />"));
  assert.ok(home.indexOf("<WatchPanel region={region} />") < home.indexOf("<RedFlags region={region} />"));
  assert.match(home, /<RedFlags region=\{region\} \/>\s*<BreadthCard region=\{region\} \/>/);      // VR1-010/011: the red flags across the page, the two short cards stacked
  assert.match(read("src/pages/ExperimentPage.tsx"), /className="k-checks-col"/);
  assert.match(read("src/pages/trade/trade.css"), /\.k-checks-col \{ display: flex; flex-direction: column;/);
});

test("UI-FIX-1 (R2): lists spread over the card instead of one narrow column", () => {
  assert.match(read("src/pages/CorpActionsPage.tsx"), /className="inv-days"/);
  assert.match(read("src/components/CorpActions.tsx"), /className=\{wide \? "k-stack" : "inv-pair"\}/);   // (VR1-105: with a short "Coming up" beside a long past list, the past rows run two across under it)
  assert.match(read("src/pages/HoldingsPage.tsx"), /className="h-filings"/);
  assert.match(read("src/pages/AccountPage.tsx"), /className="k-dl spread"/);
  assert.match(read("src/pages/SettingsPage.tsx"), /<div className="k-two">/);
});

test("UI-FIX-1 (R8): a figure is not said twice on a card", () => {
  assert.match(read("src/pages/money/MoneyCalendarPage.tsx"), /!e\.title\.includes\(inr\(e\.amount\)\)/);
  assert.doesNotMatch(read("src/components/LibraryBits.tsx"), /\{e\.description && <p className="k-small lib-line">/);
});

test("UI-FIX-1 (R3, R4, R10, R11): one row for Yours and one for Popular, labels that stay on a line, chips and badges that fit, taps that are 44px", () => {
  const search = read("src/components/InstrumentSearch.tsx");
  assert.ok(search.indexOf(">Yours:<") < search.indexOf(">Popular:<"));
  assert.match(search, /<div className="k-row">\s*<span className="k-small k-muted">Popular:<\/span>/);
  const css = read("src/styles.css");
  assert.match(css, /\.chip-name \{ min-width: 0; overflow: hidden; text-overflow: ellipsis; \}/);
  assert.match(css, /@media \(pointer: coarse\) \{\s*\/\*[^*]*\*\/\s*\.link-btn\.small, \.link-btn\.k-small \{ min-height: 44px;/);
  assert.match(read("src/pages/admin/SystemSection.tsx"), /"Send this week's summary now"/);
  assert.match(read("src/styles-invest.css"), /\.tbar-year\.long \.tbar-full \{ display: none; \}/);
});

test("UI-FIX-1: the checker runs in CI as a blocking check and keeps its report", () => {
  const ci = readFileSync(new URL("../../../.github/workflows/tests.yml", import.meta.url), "utf8");
  assert.match(ci, /ui-lint:/);
  assert.match(ci, /UI_LINT_STRICT: "1"/);
  assert.match(ci, /npm run ui-lint/);
  assert.match(ci, /name: ui-lint-report/);
  // the merge job waits for it
  assert.match(ci, /needs: \[backend, frontend, browser, ui-lint\]/);
});

test("UI-FIX-1: an allowlist entry says what and why", () => {
  const allow = JSON.parse(read("e2e/ui-lint.allow.json")).allow;
  for (const a of allow) {
    assert.ok(a.page && a.rule && a.element, JSON.stringify(a));
    assert.ok(typeof a.reason === "string" && a.reason.length > 30, `${a.rule} on ${a.page} needs a written reason`);
  }
});
