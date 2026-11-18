// R16 (owner, 7 Nov: Themes is one of StratLab's best tools but buried in Invest → Themes); since 18 Nov (owner) it is the first entry
// of Invest's menu, above Companies, and the pill beside the space's home is gone.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// (owner, 18 Nov) changed on purpose: "put it at top like above the companies": Themes is one entry, the first of Invest's menu, its own
// row with its compass icon like the other entries; no orange pill beside the space's home (in Invest or My space) and no second entry
test("R16 (owner, 18 Nov): no Themes pill beside the space's home; the first row is the home link alone", () => {
  const shell = read("src/components/Shell.tsx");
  assert.doesNotMatch(shell, /side-feature|export const THEMES/);
  assert.match(shell, /<div className="side-list side-home">\s*<NavLink to=\{homeOf\(space\)\} end>[^\n]*\n\s*<\/div>/);
  const css = read("src/styles.css");
  assert.match(css, /\.side-home \{ flex-direction: row;/);
  assert.doesNotMatch(css, /side-feature/);
});

test("R16 (owner, 18 Nov): Themes is the first entry of Invest's menu, once (unit/nav.test.mjs pins the whole order)", () => {
  const nav = read("src/lib/nav.ts");
  assert.match(nav, /label: "Invest", home: "\/invest", groups: \[\n(\s*\/\/[^\n]*\n)*\s*\{ id: "themes", label: "Themes", icon: "compass"/);
  assert.equal(nav.match(/page\("\/research\/themes"/g).length, 1);
});

test("R16: Themes stays an entry of Invest's menu (its breadcrumb is Invest › Themes)", async () => {
  const nav = read("src/lib/nav.ts");
  assert.match(nav, /\{ id: "themes", label: "Themes", icon: "compass"/);
});

test("R16 (owner, 7 Nov: \"remove the all option\"): the library's Whose filter is StratLab's own (the default) or Everyone's, no All", () => {
  const lib = read("src/pages/LibraryPage.tsx");
  assert.match(lib, /useState<"users" \| "official">\("official"\)/);
  assert.match(lib, /<Seg label="Whose" options=\{\[\{ value: "official", label: "StratLab's own" \}, \{ value: "users", label: "Everyone's" \}\]\}/);
  assert.doesNotMatch(lib, /label: "All"|"all"/);
  // every request names whose strategies it wants, so the API's "both" (no whose) is never shown
  assert.match(lib, /new URLSearchParams\(\{ q, market, verdict, sort, whose \}\)/);
  assert.match(lib, /"Nobody has published a strategy yet\."/);
});
