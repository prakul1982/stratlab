// The owner's manual check of 25 Oct: no "New" tags anywhere, a Net worth page whose main action can be found, and My
// Holdings' recent filings in lined-up columns.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("MO-2: no page is tagged New (everything is new at launch)", () => {
  assert.doesNotMatch(read("src/lib/nav.ts"), /isNew|NEW_SINCE/);
  const tags = read("src/components/PageTags.tsx");
  assert.doesNotMatch(tags, />New</);
  assert.doesNotMatch(tags, /isNew/);
});

test("MO-2: Net worth: a full-size add button at the top and one-tap chips for the usual kinds", () => {
  const src = read("src/pages/money/NetWorthPage.tsx");
  assert.match(src, /actions=\{view \? <button type="button" className="btn" onClick=\{\(\) => openAdd\(\)\}><Plus size=\{16\} \/>Add an entry<\/button>/);
  assert.doesNotMatch(src, /className="btn sm" onClick=\{\(\) => setAdding\(true\)\}>Add an entry/);
  assert.match(src, /const QUICK: Kind\[\] = \["cash", "fd", "epf", "ppf", "gold", "property", "loan"\]/);
  assert.match(src, /QUICK\.map\(\(k\) => <button key=\{k\} type="button" className="chip" onClick=\{\(\) => openAdd\(k\)\}>/);
  assert.match(src, /Something else…/);
  // a chip opens that kind's boxes straight away
  assert.match(src, /if \(k\) \{ setKind\(k\); setAddStart\(fresh\(k\)\); setStep\("form"\); \} else setStep\("pick"\);/);
  assert.match(read("src/styles.css"), /\.nw-quick \{ max-height: none; overflow: visible;/);
});

test("MO-2: recent filings line up: date, tag and title in fixed grid columns", () => {
  assert.match(read("src/pages/HoldingsPage.tsx"), /<div key=\{i\} className="h-filing k-small">/);
  const css = read("src/styles.css");
  assert.match(css, /\.h-filing \{ display: grid; grid-template-columns: 7\.5em 17em minmax\(0, 1fr\); align-items: center;/);
});
