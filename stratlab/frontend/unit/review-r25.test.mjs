// Round 25, phone and iPhone: bar labels, 16px fields, period tables, annotation clamping, the slow-load note.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const read = (p) => fs.readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { shortYear, compactValue, labelledBar, DENSE_BARS, scrollToEnd, clampNote, SLOW_LOAD_MS, SLOW_LOAD_NOTE } = await import("../src/lib/phoneFit.ts");

test("R25-001: ten yearly bars get short years, compact values, and every other label counting back from the latest", () => {
  assert.equal(shortYear("FY2017"), "FY17");
  assert.equal(shortYear("Mar 2017"), "Mar 17");
  assert.equal(shortYear("2017"), "17");
  assert.equal(shortYear("TTM"), "TTM");
  assert.equal(compactValue(146882, "₹ cr"), "1.47L");
  assert.equal(compactValue(-146882, "₹ cr"), "−1.47L");
  assert.equal(compactValue(28046, "₹ cr"), "28k");
  assert.equal(compactValue(106000, "₹ cr"), "1.06L");
  assert.equal(compactValue(2812, "₹ cr"), null);
  assert.equal(compactValue(5, "USD million"), null);
  assert.ok(DENSE_BARS <= 10);
  const shown = Array.from({ length: 10 }, (_, i) => labelledBar(i, 10));
  assert.equal(shown[9], true);
  assert.equal(shown.filter(Boolean).length, 5);
  assert.ok(shown.every((x, i) => i === 0 || x !== shown[i - 1]), "never two labelled neighbours");
  const css = read("src/styles-invest.css");
  assert.match(css, /\.tbars\.dense \.tbar-num \{[^}]*overflow: visible; text-overflow: clip/);
  assert.match(css, /\.tbars\.dense \.tbar\.alt \.tbar-num/);
});

test("R25-002: on a phone every field is 16px, and the rule outweighs a single-class size", () => {
  const css = read("src/styles.css");
  const at = css.indexOf("R13S-005");
  const rule = css.slice(at, css.indexOf("\n}", at));
  assert.match(rule, /\bhtml :is\(input:not\([^)]*\), select, textarea\) \{ font-size: 16px; \}/);
  // the fields the reviewer found: the question textarea (.k-textarea), the chart pickers (.pc-sel), the three "Find a …" boxes (.k-search input)
  const own = (file, sel) => read(file).match(new RegExp(`^${sel.replace(/[.]/g, "\\.")}[^{]*\\{[^}]*font-size: ([\\d.]+)px`, "m"));
  assert.equal(own("src/charts/price/priceChart.css", ".pc-btn, .pc-sel")[1], "13.5");   // 13.5px by itself: only the global rule fixes it
  for (const f of ["src/pages/NotebookPage.tsx", "src/pages/trade/FoChangesPage.tsx", "src/pages/trade/ClosingAuctionPage.tsx", "src/pages/trade/JournalPage.tsx"]) {
    assert.match(read(f), /k-textarea|k-search/);
  }
  assert.match(read("src/pages/trade/trade.css"), /\.k-search input \{[^}]*font-size: var\(--t-body\)/);
  // specificity: the global rule is (0,1,2) or more, so beats .k-search input (0,1,1) and .pc-sel (0,1,0)
  assert.ok(!/:where\(/.test(rule.match(/html :is[^\n]*/)[0]));
});

test("R25-003: a period table opens at its right end, columns in the same order", () => {
  const el = { scrollLeft: 0, scrollWidth: 900, clientWidth: 360 };
  scrollToEnd(el);
  assert.equal(el.scrollLeft, 540);
  const fits = { scrollLeft: 0, scrollWidth: 300, clientWidth: 360 };
  scrollToEnd(fits); assert.equal(fits.scrollLeft, 0);
  scrollToEnd(null);
  assert.match(read("src/components/Research.tsx"), /<DataTable scrollEnd label="The last quarters/);
  assert.match(read("src/components/kit/DataTable.tsx"), /if \(scrollEnd\) scrollToEnd\(box\.current\)/);
});

test("R25-004: the sticky first column keeps a floor and breaks long words anywhere", () => {
  const css = read("src/styles.css");
  assert.match(css, /:first-child \{ min-width: min\(9rem, 40vw\); overflow-wrap: anywhere; \}/);
});

test("R25-005: a slow load says so after 8 s and offers Retry, on the three pages", () => {
  assert.equal(SLOW_LOAD_MS, 8000);
  assert.equal(SLOW_LOAD_NOTE, "Still loading… this can take a little longer the first time today");
  assert.match(read("src/components/kit/States.tsx"), /Retry/);
  assert.match(read("src/pages/Home.tsx"), /Opening your notebooks" onRetry/);
  assert.match(read("src/pages/Research.tsx"), /Pulling live data for \$\{sym\}`\} lines=\{5\} onRetry/);
  assert.match(read("src/pages/admin/SystemSection.tsx"), /Loading the server errors" lines=\{2\} onRetry/);
});

test("R25-006: a chart note that would run past the plot ends at its right edge", () => {
  assert.deepEqual(clampNote(100, 120, 40, 340), { x: 100, anchor: "start" });
  assert.deepEqual(clampNote(300, 120, 40, 340), { x: 340, anchor: "end" });
  assert.deepEqual(clampNote(220, 120, 40, 340), { x: 220, anchor: "start" });
  assert.match(read("src/components/chart/XYChart.tsx"), /clampNote\(sx\(X\[p\.split\]\) \+ 8/);
});
