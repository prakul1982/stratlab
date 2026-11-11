// R16 (owner, 7 Nov: Themes is one of StratLab's best tools but buried in Invest → Themes): a highlighted Themes row heads the menu
// in every space, laptop and phone drawer alike, right under the search box. Invest's own Themes entry stays.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("R16: the menu's first row, in every space, carries the highlighted Themes link with the Themes icon, beside the space's home", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /export const THEMES = "\/research\/themes";/);
  // the first row of the scrolling menu, before the space's own entries, so every space (and the phone's drawer) shows it; it shares
  // the home link's row, so the menu is no taller (IA-2: a 1280x800 laptop's menu doesn't scroll)
  // owner, 7 Nov (changed on purpose): on My space and Invest only, not Trade or Money
  assert.match(shell, /<div className="side-list side-home">\s*<NavLink to=\{homeOf\(space\)\} end>[^\n]*\n[^\n]*\n\s*\{\(space === "invest" \|\| space === "mine"\) && <Link to=\{THEMES\} className=\{`side-feature[^`]*`\}[^>]*><Compass size=\{16\} \/>Themes<\/Link>\}/);
  const nav = shell.slice(shell.indexOf('<nav ref={sideScroll} className="side-groups"'));
  assert.ok(nav.indexOf('className={`side-feature') < nav.indexOf("{spaceGroups ?? minePart}"));
  // never marked current: on the Themes page Invest's own entry is the one highlighted item (ui-lint R7)
  assert.doesNotMatch(shell.match(/<Link to=\{THEMES\}[^>]*>/)[0], /aria-current|active/);
});

test("R16: the Themes link has an accent edge and tint", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.side-home \{ flex-direction: row;/);
  assert.match(css, /\.side-list a\.side-feature \{[^}]*border-left: 3px solid var\(--orange\);[^}]*background: var\(--orange-soft\);/);
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
