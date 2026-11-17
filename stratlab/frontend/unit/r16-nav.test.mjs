// R16 (owner, 7 Nov: Themes is one of StratLab's best tools but buried in Invest → Themes): a highlighted Themes row heads the menu
// in every space, laptop and phone drawer alike, right under the search box. Invest's own Themes entry stays.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// (updated on purpose, NAV3, CX-1 "Themes appears twice"; owner OK 16 Nov to merge menu entries): Themes is no longer buried behind the Invest
// switch, so the highlighted pill that answered R16 is gone: Themes is an entry of the one menu, in view in every view and in the phone's
// drawer, once.
test("R16/NAV3: Themes is in view in the one menu on every page, as one entry, not a second highlighted link", async () => {
  const shell = read("src/components/Shell.tsx");
  assert.doesNotMatch(shell, /side-feature/);
  // the one menu draws every space's entries on every page (MENU), so Themes is never behind a switch
  assert.match(shell, /\{MENU\.map\(\(sec\) =>/);
  assert.doesNotMatch(shell, /SpaceSwitch|space-switch/);
  const { MENU } = await import("../src/lib/nav.ts");
  const all = MENU.flatMap((s) => s.groups.map((g) => g.label));
  assert.equal(all.filter((l) => l === "Themes").length, 1);
});

test("R16/NAV3: the menu's first row is My space, the one home in the menu", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /<div className="side-list side-home">\s*<NavLink to=\{MINE_HOME\} end>/);
  assert.match(read("src/styles.css"), /\.side-home \{ flex-direction: row;/);
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
