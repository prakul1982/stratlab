// Lane ui1 (owner, 18 Nov). Item 6 ("fix ui dude", the Themes page): one line under the title, the box and "Map it" on one row with the market
// switch, the shared library as equal chips with short names (at most two rows, then "All N themes"), the ideas folded under it.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the app's files import each other without an extension (the bundler adds it); Node needs a hint to find the .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a theme's chip says its short name: the words before a bracket or a dash that explain it", async () => {
  const { shortTheme } = await import("../src/lib/themeFormat.ts");
  assert.equal(shortTheme("Utilities (Indian power, gas and water-linked infrastructure)"), "Utilities");
  assert.equal(shortTheme("Pharmaceuticals (generic drug makers and APIs)"), "Pharmaceuticals");
  assert.equal(shortTheme("Defence — aerospace and shipyards"), "Defence");
  assert.equal(shortTheme("Cement"), "Cement");
  assert.equal(shortTheme("EV and battery supply chain"), "EV and battery supply chain");
  assert.equal(shortTheme("(odd)"), "(odd)");
});

test("the Themes page: one-line lede with the method behind the (i); box, Map it and market switch in one form row", () => {
  const page = read("src/pages/ThemesPage.tsx");
  const lede = page.match(/lede="([^"]*)"/)[1];
  assert.ok(lede.length <= 80, `the lede is one line (${lede.length} chars)`);
  assert.match(page, /infoLabel="How a theme is mapped"/);
  assert.match(page, /<form className="theme-map" aria-label="Map a theme"[^\n]*\n\s*<RegionSwitch region=\{region\} setRegion=\{setRegion\} \/>\s*<div className="theme-field">/);
  const css = read("src/styles.css");
  assert.match(css, /\.theme-field \{ flex: 1 1 320px; display: flex; align-items: center;/);
  // (changed on purpose, site87, owner: "31 equal bordered pills in 5 columns" looked plain and heavy: compact chips, centred, wrapping)
  assert.match(css, /\.theme-ready \{ display: flex; flex-wrap: wrap; justify-content: center;/);
});

test("Ready to open: short names (full name and date in the title), two rows of the grid's columns, then All N themes", () => {
  const page = read("src/pages/ThemesPage.tsx");
  // (changed on purpose, site87, owner: the updated day small inside the chip, not a hover box over the next row; every ready theme, the area
  // scrolling past three lines, no "All N themes" / "Fewer themes"; the ideas a row of their own with none the chips already show, no fold)
  assert.match(page, /aria-label=\{libraryLabel\(i, \(d\) => fmtDate\(d, \{ year: false \}\), false\)\}/);
  assert.match(page, /<span className="theme-chip-name">\{shortTheme\(i\.name\)\}<\/span>/);
  assert.doesNotMatch(page, /theme-chip-day/);     // (changed on purpose, site88, owner: no date on the chips at all)
  assert.doesNotMatch(page, /title=\{libraryLabel|All \{items\.length\} themes|<Disclosure summary="More ideas"/);
  assert.match(page, /const ideas = ideasBeside\(THEME_IDEAS\[region\], items, region, shortTheme\);/);
});

// item 3 (owner, 18 Nov: HDFC Bank's update filings, "NSE filing ↗" dropped to its own line under a long subject)
test("update filings: the same subject filed again is one row with its other days, in the list's order", async () => {
  const { foldFilings } = await import("../src/lib/biz.ts");
  const lodr = "Intimation under SEBI (LODR) Regulations, 2015";
  const rows = [{ id: 1, title: lodr }, { id: 2, title: "Business update Q2" }, { id: 3, title: `${lodr} ` }, { id: 4, title: "INTIMATION UNDER SEBI (LODR) REGULATIONS, 2015" }, { id: 5, title: "Business update Q1" }];
  const g = foldFilings(rows);
  assert.deepEqual(g.map((x) => x.items.map((i) => i.id)), [[1, 3, 4], [2], [5]]);
  assert.equal(g[0].title, lodr);
});

test("update filings: date | subject (two lines at most) | link on one grid; five rows, then Show all N", () => {
  const panel = read("src/components/BizUpdates.tsx"), css = read("src/styles.css");
  // (changed on purpose, site87, owner: no "Show all N": every filing, the list a block sized to the screen that scrolls inside itself)
  assert.doesNotMatch(panel, /const FILINGS_FIRST = 5;|Show all \{groups\.length\}/);
  assert.match(panel, /const files = foldFilings\(v\.filings\);/);
  assert.match(panel, /<ScrollList label="Business update filings">/);
  assert.match(panel, /<span className="biz-title" title=\{title\}>\{title\}<\/span>/);
  assert.match(css, /\.biz-title \{ display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; \}/);
  assert.match(css, /\.biz-link \{ white-space: nowrap; justify-self: end; \}/);
});

// item 2 (owner, 18 Nov: "hide these type of information in a drop down … everything this just clutters the pages")
test("a long page intro shows one short sentence (or the words before its colon); the rest is behind More", async () => {
  const { splitLede, LEDE_MAX } = await import("../src/lib/lede.ts");
  assert.equal(splitLede("A short intro that fits."), null);
  const two = "Pick the conditions; see every company that meets them. Nothing here scores companies: the list starts with the largest market value; sort by any column.";
  assert.deepEqual(splitLede(two), { first: "Pick the conditions; see every company that meets them.", joint: "", rest: "Nothing here scores companies: the list starts with the largest market value; sort by any column." });
  const colon = "What foreign and domestic institutions bought and sold in India's cash market, in ₹ crore: the exchange's provisional figures, published each evening, and every recorded day.";
  // (updated on purpose, fix18: an intro is cut only at a sentence's end, never at its colon, which left half a sentence showing)
  assert.equal(splitLede(colon), null);
  assert.equal(splitLede("For each India watchlist company: the price trend, where its sector sits in the rotation, red-flag filings, the investor checklist and how well management delivered on past targets. Facts to read, not advice."), null);
  // a first sentence longer than the limit, with no early colon, shows whole
  const long = "x".repeat(LEDE_MAX + 5) + ". Then more.";
  assert.equal(splitLede(long), null);
  const ph = read("src/components/kit/PageHeader.tsx");
  assert.match(ph, /<span hidden=\{!more\} data-testid="lede-rest">/);
  assert.match(ph, /aria-expanded=\{more\}/);
});

test("a card's method and source notes are one closed fold at its foot (kit/CardNote), on the company page, the deep dive and more", () => {
  const note = read("src/components/kit/CardNote.tsx");
  assert.match(note, /<Disclosure className="k-cardnote" summary=\{summary\}/);
  assert.match(note, /summary = "About these figures"/);
  for (const [f, re] of [["src/components/Filings.tsx", /<CardNote><p>From the company's filings/], ["src/components/Deals.tsx", /<CardNote><p>From exchange disclosures/],
    ["src/components/BizUpdates.tsx", /<CardNote><p>\{v\.note\}<\/p><\/CardNote>/], ["src/components/NamedHolders.tsx", /<CardNote><p>\{v\.note\}/],
    ["src/components/CompanyLinks.tsx", /<CardNote><p>\{v\.note\}<\/p><\/CardNote>/], ["src/components/ShareholdingHistory.tsx", /<CardNote><p>\{v\.pledge_note\}<\/p><\/CardNote>/],
    ["src/components/CompanyPeers.tsx", /<CardNote summary="About this list">/], ["src/pages/DeepDive.tsx", /<CardNote summary="How each target is checked">/],
    ["src/pages/HoldingsPage.tsx", /<CardNote summary="How your holdings are kept">/], ["src/pages/ThemesPage.tsx", /<CardNote summary="About this page">/]]) assert.match(read(f), re, f);
  // the deep dive's valuation note no longer repeats its (i)
  assert.doesNotMatch(read("src/pages/DeepDive.tsx"), /<p className="k-note">\{v\.valuation\.why\}/);
});

// item 1 (owner, 18 Nov: "center align everything properly")
test("figure rows centred, a head's top control on its title's line, table cells vertically centred, and the checker's R28", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.k-stats > \.k-stat \{ display: grid; grid-row: span 3; grid-template-rows: subgrid; row-gap: 0; align-content: start; text-align: center; \}/);
  assert.match(css, /\.mine-mkt \{ display: flex; flex-direction: column; gap: 4px; min-width: 0; padding: var\(--s3\); border: 1px solid var\(--line\); border-radius: 12px; text-align: center; \}/);
  assert.match(css, /\.k-chart-plain > \.k-card-head > \.k-card-actions \{ height: calc\(var\(--t-card\) \* 1\.5\); \}/);
  assert.match(css, /\.ai-table \.k-table :is\(th, td\) \{ white-space: normal; vertical-align: middle;/);
  assert.doesNotMatch(css, /\.ca-table \.k-table td \{[^}]*vertical-align: top/);
  const rules = read("e2e/ui-lint-rules.ts");
  assert.match(rules, /add\("R28", th, `the header/);
  assert.match(rules, /add\("R28", act, `the head's controls sit/);
});

// item 4 (owner, 18 Nov: "in deep dive why are we putting repeated thing which we already have in the normal stock page?")
test("the deep dive keeps what it adds and points to the company page for price, valuation, peers, statements, shareholding, updates and filings", () => {
  const dd = read("src/pages/DeepDive.tsx");
  for (const gone of [/<CompanyTables /, /<BizUpdatesPanel /, /How it's valued/, /label="The last eight quarters"/, /<Badge tone="live">/]) assert.doesNotMatch(dd, gone);
  assert.match(dd, /data-testid="dd-elsewhere">Price, valuation, peers, the statements, shareholding, business updates and filings are on the/);
  for (const kept of [/<Panel title="Growth and margins"/, /<Panel title="Investor checklist"/, /<Panel title="Capex and cash"/, /title="Management report card"/, /<Panel title="Business model">/]) assert.match(dd, kept);
});
