// VFA (26 Oct 2026): the visual review's findings VR1-001 to VR1-095 (My space, Invest and Trade homes, notebooks, the experiment page, Positioning,
// the F&O desk, Paper, Options, Journal, Signals): the pure pieces and the CSS they rest on.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("VR1-062: the experiment's verdict block drops the sentence that restates both returns, and a 'lost money' sentence the caption already says", async () => {
  const { heroSummary } = await import("../src/lib/tradeUi.ts");
  const lost = "After costs, the strategy lost money over the period. The strategy returned −4.8% after costs, less than buying and holding over the same period (+50.2%).";
  assert.deepEqual(heroSummary(lost, "Lost money after costs."), []);
  assert.deepEqual(heroSummary(lost, ""), ["After costs, the strategy lost money over the period."]);
  const edge = "It made money after costs and kept making money on unseen data. The strategy returned +12.0% after costs, more than buying and holding over the same period (+4.0%). A year at a time, that is about +3.0% (buying and holding: +1.0%).";
  assert.deepEqual(heroSummary(edge, "4 of 4 checks run · 3 passed."), ["It made money after costs and kept making money on unseen data.", "A year at a time, that is about +3.0% (buying and holding: +1.0%)."]);
  assert.deepEqual(heroSummary("Only 3 trades in this period. That's too few to tell a real edge from a lucky streak, whatever the return says.", ""), ["Only 3 trades in this period.", "That's too few to tell a real edge from a lucky streak, whatever the return says."]);
  assert.deepEqual(heroSummary(null), []);
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /heroSummary\(v\.summary, head\.checks\)/);
});

test("VR1-002: the gold line's second half (the world price and the duty) goes behind the Markets card's (i); the one-line fact stays", async () => {
  const { goldLine, goldLineParts } = await import("../src/lib/gold.ts");
  const inr = (v) => `₹${v.toLocaleString("en-IN")}`;
  const india = { per_10g: 142150, as_of: null, duty_pct: 15, duty_note: "India's import duty on gold is 15%" };
  const p = goldLineParts(india, 122336, inr);
  assert.equal(p.short, "₹1,42,150 per 10 g in India, the price Net worth uses.");
  assert.equal(`${p.short} ${p.more}`, goldLine(india, 122336, inr));
  assert.deepEqual(goldLineParts(null, 122336, inr), { short: goldLine(null, 122336, inr), more: null });
  assert.equal(goldLineParts(null, null, inr), null);
  const mine = read("src/pages/MineHome.tsx");
  assert.doesNotMatch(mine, /mine-mkt-key/);                                           // the "Lines: ..." key is in the (i), not a paragraph
  assert.match(mine, /the dollar and gold stay blue/);
});

test("VR1-003, VR1-004, VR1-005: My space's heading says only the market state, one corner link on every card, no boxed placeholder chart", () => {
  const mine = read("src/pages/MineHome.tsx");
  assert.doesNotMatch(mine, /Next up:/);
  assert.match(mine, /const firstSentence = /);
  assert.equal((mine.match(/className="btn quiet sm" to="[^"]+" aria-label="Open [^"]+">Open<\/Link>/g) ?? []).length, 6);   // net worth, P&L, paper, markets, calendar, watchlist
  assert.doesNotMatch(mine, /<svg viewBox="0 0 100 30"/);
  assert.match(mine, /!v\.history_allowed && <HistoryPlaceholder \/>/);
});

test("VR1-010, VR1-011, VR1-012, VR1-013, VR1-014: Invest home's panels, tiles, card heads and the lead card's link", () => {
  const homes = read("src/pages/SpaceHomes.tsx");
  const inv = homes.slice(homes.indexOf("export function InvestHome"), homes.indexOf("/** The next few market events"));
  assert.match(inv, /<WatchPanel region=\{region\} \/>\s*<div className="space-col">\s*<NextEvents region=\{region\} \/>\s*<ResultsToday region=\{region\} \/>\s*<\/div>/);
  assert.match(inv, /<\/div>\s*<RedFlags region=\{region\} \/>/);
  assert.doesNotMatch(inv, /space-panels even/);
  assert.doesNotMatch(css, /\.space-panels \.inv-tiles \{ align-items: start; \}/);   // VR2-002: the tiles of a row are as tall as each other
  assert.match(css, /\.space-home \.k-card-head:has\(> \.k-card-actions > a\.link:only-child\) \{ flex-wrap: nowrap;/);
  assert.doesNotMatch(css, /\.space-card-lead \.space-card-foot:not\(\.live\) \{/);       // the lead's link has the colour of the others
  assert.match(css, /\.trade-market \.space-card-line \{ min-height: 0; \}/);
});

test("VR1-021, VR1-022, VR1-031: the 'more you can do' tiles keep a card's width, one name, whole lines on a phone", () => {
  assert.match(css, /\.k-explore \.explore-grid \{ grid-template-columns: repeat\(auto-fit, minmax\(230px, 1fr\)\);/);
  assert.match(css, /\.k-explore \.explore-card \.small \{ display: block; -webkit-line-clamp: unset;/);
  assert.match(read("src/components/Explore.tsx"), /title = "More you can do"/);
});

test("VR1-030: two notebooks fill the row, a lone one is a card's width, the pin is an icon at the top right", () => {
  const tcss = read("src/pages/trade/trade.css");
  assert.match(tcss, /\.k-cards\.nb-cards \{[^}]*repeat\(auto-fit, minmax\(min\(100%, 320px\), 1fr\)\)/);
  assert.match(tcss, /\.nb-cards > \.k-card:only-child \{ max-width: 520px; \}/);
  assert.match(tcss, /\.nb-cards \.k-card-head \{ flex-wrap: nowrap;/);
  const home = read("src/pages/Home.tsx");
  assert.match(home, /<TileGrid className="k-cards nb-cards">/);
  assert.doesNotMatch(home, /\{n\.pinned \? "Pinned" : "Pin"\}<\/span>/);
});

test("VR1-040, VR1-041, VR1-042: /new has the app's column, one numbered list, and its hint behind the (i)", () => {
  const home = read("src/pages/Home.tsx");
  const page = home.slice(home.indexOf("export function NewNotebook"));
  assert.match(page, /<div className="k-page">/);
  assert.doesNotMatch(page, /k-narrow/);
  assert.doesNotMatch(page, /aria-label="How StratLab works"/);
  assert.doesNotMatch(home, /Optional: if your idea names a stock or coin, we'll find it for you\.<\/p>/);
  assert.match(home, /Picking a stock or coin is optional: if your idea names one, we'll find it for you\./);
});

test("VR1-050, VR1-051, VR1-052, VR1-053, VR1-054: the notebook page", () => {
  // the Lab notes tab: a zero-height sticky dock at the page's end, its tab flush with the bottom of the screen, room kept under the last card
  const dock = css.match(/\.ln-dock \{[^}]*\}/)[0];
  assert.match(dock, /position: sticky/);
  assert.match(dock, /bottom: 0/);
  assert.match(css, /\.ln-dock-in \{ position: absolute; right: 0;/);
  assert.match(css, /\.k-page:has\(> \.ln-dock\) \{ padding-bottom: 44px; \}/);
  assert.match(css, /\.ln-btn \{[^}]*min-height: 44px;[^}]*border-radius: 12px 12px 0 0;/);
  assert.match(read("src/components/LabNotes.tsx"), /<div className="ln-dock-in">/);
  // the saving text no longer holds a row of its own under the question
  assert.match(css, /\.k-page-head:has\(> \.k-meta > \.nb-save:only-child\) > \.k-meta \{ position: absolute;/);
  const nb = read("src/pages/NotebookPage.tsx");
  assert.match(nb, /className="k-note nb-save"/);
  assert.match(nb, /<ChipBar label="Test period" wrap /);                                // wraps on a phone, no cut chips
  assert.match(css, /\.cond-row \.sentence \{ flex: 0 1 auto;/);                         // the × follows the rule
  assert.match(css, /\.market-btn \{[^}]*border: 1px solid var\(--line-2\)/);
  assert.match(read("src/pages/trade/trade.css"), /\.k-textarea\.nb-q \{ min-height: 76px; \}/);
  assert.match(read("src/pages/MarketPage.tsx"), /· Costs: \{market\.costs\}/);          // VR1-055
});

test("VR1-060, VR1-061, VR1-063, VR1-064, VR1-065: the experiment page's layout", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  // the chart across the page, then the numbers beside what you'd keep
  assert.ok(page.indexOf('title="Where the money came from, and went"') < page.indexOf('<Card label="The numbers" className="k-numbers">'));
  assert.ok(page.indexOf('<Card label="The numbers" className="k-numbers">') < page.indexOf('<Card label="What you\'d keep">'));
  assert.ok(page.indexOf('<Card label="What you\'d keep">') < page.indexOf('<Card label="Price and trades">'));
  assert.match(page, /\["Period", periodName\(e\.days\), null, HELP\.period, `\$\{e\.candles\.toLocaleString\("en-IN"\)\} candles`\]/);
  assert.match(page, /className="unseen-mark split"/);
  assert.match(page, /data-testid="unseen-legend"/);
  assert.doesNotMatch(page, /<span className="k-sub-line">Unseen part<\/span>/);
  const tcss = read("src/pages/trade/trade.css");
  assert.match(tcss, /\.k-numbers \.k-stats \{ grid-template-columns: repeat\(4, minmax\(0, 1fr\)\); \}/);
  assert.match(tcss, /\.k-verdict-hero > \.k-card \{ flex: none; width: 290px;/);
  assert.match(tcss, /\.k-verdict-hero \.k-card-titlerow > \.verdict-head \{ display: inline;/);
  const cmp = read("src/pages/CompareExperiments.tsx");
  assert.match(cmp, /<div className="k-two k-two-start">\s*\{pickers\}\s*<Card label="What changed">/);
});

test("VR1-070, VR1-071, VR1-072, VR1-073: Positioning", async () => {
  const page = read("src/pages/PositioningPage.tsx");
  assert.match(page, /<span className="k-stat-v">\{long == null \|\| short == null \? "–" : pct\(long\)\}<\/span>/);       // a number among numbers
  assert.match(page, /futures, \$\{words\[0\]\} share/);
  assert.match(page, /<span data-testid="part-source">/);                                      // the source and the "as of" line in one paragraph
  assert.match(page, /<span data-testid="part-status">/);
  const { vixIvLine, vixIvNote } = await import("../src/lib/positioning.ts");
  const f = (v) => v.toLocaleString("en-IN");
  assert.equal(vixIvLine(25000, "Chain at the close, 26 Oct, 15:40 IST", f), "At the 25,000 strike · Chain at the close, 26 Oct, 15:40 IST.");
  assert.match(vixIvLine(25000, "Live chain, 09:40 IST", f, true), /^At the 25,000 strike · Live chain, 09:40 IST\. The IV of the next expiry's options, as today's expire today\.$/);
  assert.ok(vixIvNote(25000, "x", f).length > vixIvLine(25000, "x", f).length);              // the long note is unchanged, the card shows its first sentence
  assert.match(read("src/components/VixPanel.tsx"), /India VIX measures the next 30 days while the IV is of one expiry/);
  assert.match(read("src/pages/trade/positioning.css"), /part-table"\] \.k-tbl-wrap\.stack \.k-table td:last-child:nth-child\(even\) \{ grid-column: 1 \/ -1; \}/);
});

test("VR1-080, VR1-081, VR1-082: the F&O desk", () => {
  assert.match(read("src/pages/trade/fo.css"), /\.fo-row > \.k-row > \.k-badge:first-child \{ min-width: 9\.5em; \}/);
  const page = read("src/pages/trade/FoChangesPage.tsx");
  assert.match(page, /const circulars = \(e\.sources \?\? \[\]\)\.filter\(\(s\) => s\.no \|\| s\.url\);/);
  assert.match(page, /const sources = circulars\.length \? circulars : e\.sources \?\? \[\];/);
  assert.match(read("src/pages/trade/events.css"), /\.ev-weekgrid \{ display: grid;/);
});

test("VR1-090, VR1-091, VR1-092, VR1-093, VR1-094, VR1-095: Paper, Options, Journal, Signals", () => {
  const risk = read("src/components/RiskOverview.tsx");
  assert.match(risk, /value=\{c\.worst_day \? money\(c\.worst_day\.pnl, c\.currency\) : "–"\}/);
  assert.match(risk, /: "None yet"\} \/>/);
  assert.match(risk, /\{rows\.length > 1 && <DataTable stack label=\{`Running sessions in/);
  const paper = read("src/pages/PaperPage.tsx");
  assert.match(paper, /<Badge tone="plain" dot=\{false\}>\{sub\}<\/Badge>\}<Info label="About paper trading">\{HELP\.paper\}<\/Info>/);
  assert.match(paper, /<ChartEmpty height=\{72\}>Your equity curve starts/);
  const o = read("src/pages/trade/options.css");
  assert.match(o, /\.legs-box > summary > span:first-of-type \{ flex: 1;/);
  assert.match(o, /\.k-struct \.k-row > select\.k-input \{ width: auto; min-width: 260px;/);
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /\{!\(!has && taxTrades > 0 && j\.show !== "practice"\) && <button type="button" className="btn outline"/);
  assert.match(read("src/pages/trade/journal.css"), /\[data-testid="j-how"\] \.k-disclosure-body \{ padding-left: 0; max-width: 72ch; \}/);
  const sig = read("src/pages/trade/SignalsPage.tsx");
  assert.match(sig, /<FormActions>\s*<CheckField label="Allow short positions"/);
});
