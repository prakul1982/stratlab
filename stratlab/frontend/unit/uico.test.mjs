// UI-CO (29 Oct 2026): the owner's company-page, Compare and Screener fixes: tables with headers and aligned columns instead of loose lines.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("item 7: the management report card is a table (Target | For | Said | Result) with the quote under the target, and says why it can't check", () => {
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /<DataTable label="Management targets and how they turned out" stack/);
  for (const h of ['header: "Target"', 'header: "For"', 'header: "Said"', 'header: "Result"']) assert.ok(dd.includes(h), h);
  assert.match(dd, /<span className="k-note rc-quote">"\{r\.quote\}"<\/span>/);       // the quote sits under the target's name
  assert.match(dd, /data-testid="rc-why"/);                                           // one short line on why it can't be checked
  assert.doesNotMatch(dd, /className="promise-facts k-note">\s*\{r\.period/);          // the loose "For / Target / Actual" run of words is gone
  // a multiple is printed as one ("3–4×"), a percentage as said; a net margin has its own name
  assert.match(dd, /unit === "x" \? "×"/);
  assert.match(dd, /net_margin: "Net margin"/);
  assert.match(dd, /gross_margin: "Gross margin"/);
  // a plan with no figure is not "couldn't check": it has its own line under the counts
  assert.match(dd, /more \{c\.no_figure === 1 \? "is a plan" : "are plans"\} with no figure to check/);
});
