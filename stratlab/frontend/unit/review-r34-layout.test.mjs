// Round 34 layout fixes: tablet Trade home card, notebook grid, sidebar pill, phone volume legend, question cut. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { questionFrom } from "../src/lib/rules.ts";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

test("R34-003: recent notebook cards wrap with a minimum width", () => {
  assert.match(css, /\.space-recent \{[^}]*repeat\(auto-fit, minmax\(240px, 1fr\)\)/);
});

test("R34-004: the notebook page stacks Lab notes under the table below 1500px", () => {
  assert.match(css, /@media \(max-width: 1500px\) \{ \.nb-grid \{ grid-template-columns: minmax\(0, 1fr\)/);
});

test("R34-013: the More below pill takes its own row, not a negative margin over the list", () => {
  const rule = css.match(/\.side-more \{[^}]*\}/)[0];
  assert.doesNotMatch(rule, /margin: -/);
});

test("R34-012: the volume legend row is hidden on phones", () => {
  const src = readFileSync(new URL("../src/charts/price/PriceChart.tsx", import.meta.url), "utf8");
  assert.match(src, /className="pc-hide-phone"><span><span className="k">Vol</);
});

test("R34-009: a long question is cut at a word and its quote stays closed", () => {
  const idea = "Buy RELIANCE when the 20-day EMA crosses above the 50-day EMA and the volume is above its average, then sell when it crosses back below the setting";
  const q = questionFrom(idea, "RELIANCE");
  assert.match(q, /^Does ".+ [A-Za-z0-9-]+…" work\?$/);
  assert.ok(idea.startsWith(q.slice(6, q.indexOf("…"))), q);
  assert.equal(q.split('"').length - 1, 2);
});
