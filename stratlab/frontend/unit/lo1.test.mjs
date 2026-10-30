// LO-1: the last leftovers before the weekly reset (30 Oct 2026). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LO1-1: on a phone undo, redo and the shortcuts (i) move from the chart's top bar into the Draw sheet", () => {
  const chart = read("src/charts/price/PriceChart.tsx");
  assert.match(chart, /\{!phone && <span className="pc-endtools"><HistoryButtons /);
  const sheet = read("src/charts/price/DrawToolbar.tsx");
  assert.match(sheet, /<div className="pc-sheet-more"><HistoryButtons \{\.\.\.p\} \/><ShortcutsButton \/><\/div>/);
  assert.match(read("src/charts/price/priceChart.css"), /\.pc-sheet-more \{ display: flex;/);
});

test("LO1-2: the holder card shows the promoter/public split and says plainly when the table couldn't be read", () => {
  const page = read("src/pages/IpoPage.tsx");
  assert.match(page, /testId="ipo-holding">\s*<CardHead level=\{2\} title="Who holds the shares" \/>\s*<p className="k-small k-muted" data-testid="ipo-holding-unread">/);
  assert.match(page, /label="Promoters and public, before the offer"/);
  assert.match(page, /\{\(any \|\| !f\.holding_unread\) && <Holding f=\{f\} \/>\}/);
  assert.match(read("src/lib/ipo.ts"), /holding_unread\?: boolean;/);
});

test("LO1-3: Admin → Data has the NIFTY 100's business updates coverage line, its reasons as a table", () => {
  const panel = read("src/pages/admin/BizCoveragePanel.tsx");
  assert.match(panel, /api<IndexCoverage>\("\/admin\/business-updates\/index"\)/);
  for (const why of ["No filing found", "Filing unreadable", "Not fetched yet"]) assert.match(panel, new RegExp(`label: "${why}"`));
  assert.match(panel, /have a business update read in the last \{cov\.days\} days/);
  assert.match(read("src/pages/admin/DataSection.tsx"), /<BlogPanel \/>\s*<BizCoveragePanel \/>/);
});
