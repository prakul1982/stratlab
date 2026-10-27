// VR2-B (27 Oct 2026): the twelve Low findings the second visual review left (VR2-012 to VR2-023): what the CSS and the pages now say.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");

test("VR2-013: a live India VIX tile on Trade home gives its change where the day would be, so it is as tall as its neighbours", () => {
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /type VixBrief = \{ value: number \| null; value_day\?: string \| null; quote\?: VixQuote \| null \};/);
  assert.match(home, /vixChange\(vix\?\.quote \?\? null\) \?\? ""/);
});

test("VR2-014: the experiment page's Period stat has no note, so The numbers is as tall as What you'd keep; the candles are in its (i)", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /\["Period", periodName\(e\.days\), null, `\$\{HELP\.period\} This run used \$\{e\.candles\.toLocaleString\("en-IN"\)\} candles\.`\]/);
});

test("VR2-016: a right-aligned head's (i) in the fund table is spaced from its words", () => {
  assert.match(css, /\.k-fold-head \.k-num > \.info \{ margin-left: 0; margin-right: 6px; \}/);
});

test("VR2-017: Holdings' Edit button sits at the top right of a position card on a phone", () => {
  assert.match(read("src/pages/HoldingsPage.tsx"), /key: "edit", header: "", action: true, corner: true/);
  assert.match(read("src/components/kit/DataTable.tsx"), /c\.action && c\.corner && "k-corner"/);
  assert.match(css, /td\.k-act\.k-corner \{ position: absolute; top: var\(--s2\); right: var\(--s2\); grid-column: auto; \}/);
});

test("VR2-018: the company header's second row takes the price column's extra height, so the buttons stay under the badges", () => {
  assert.match(read("src/styles-invest.css"), /\.inv-head \{ display: grid; grid-template-columns: minmax\(0, 1fr\) auto; grid-template-rows: auto 1fr;/);
});

test("VR2-019: the IPO alert events and markets share one row of chips", () => {
  assert.match(read("src/pages/IposPage.tsx"), /<div className="ipo-alert-sets">\s*<ChipSet label="Which events"[\s\S]*<ChipSet label="Which markets"[\s\S]*<\/div>\s*<CheckField checked=\{p\.sme\}/);
  assert.match(read("src/pages/ipo.css"), /\.ipo-alert-sets \{ display: flex; flex-wrap: wrap;/);
});

test("VR2-020: the funds' cost and behaviour card is four figures across (4 + 3), not five (5 + 2)", () => {
  assert.match(css, /\n\.mf-stats \.k-stats \{ grid-template-columns: repeat\(auto-fit, minmax\(220px, 1fr\)\); \}/);
});

test("VR2-021: Invest home's red flags say the window once, not at the start of every line", () => {
  const f = read("src/components/Filings.tsx");
  assert.match(f, /bare\?: boolean/);
  assert.equal((f.match(/\{since\}<b>/g) ?? []).length, 2);
  const home = read("src/pages/SpaceHomes.tsx");
  assert.match(home, /data-testid="invest-redflags-window">Last \{flagged\[0\]\.summary\.days\} days</);
  assert.match(home, /<SummaryLine bare s=\{r\.summary\}/);
});

test("VR2-022: Positioning's intro lines run the card's width", () => {
  assert.match(css, /\.pos-source \{ margin-top: -6px; \}/);
});
