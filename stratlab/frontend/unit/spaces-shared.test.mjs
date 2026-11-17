// A page in more than one space's menu opens inside the space it was opened from (owner, 4 Nov: "whenever we click on something
// in Calendar it redirects to Invest — keep the main space there only"). Swept over the whole menu map, not a list of examples.
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { NAV, MENU } = await import("../src/lib/nav.ts");
const { menuView, spaceOf, SPACE_IDS } = await import("../src/lib/spaces.ts");

// (updated on purpose, NAV3, CX-1 "a 7-link Calendar group repeats in Trade, Invest and Money"; owner OK 16 Nov to merge menu entries): the
// Calendar is one entry of one menu, so no page is in two spaces' menus any more, and the rule the owner asked for on 4 Nov ("keep the main
// space there only") holds by construction: a Calendar tab opens in the same place whichever page it was reached from. An old link that
// still carries ?space= opens the same page (the word is ignored).
const menus = {};
for (const sp of SPACE_IDS) for (const g of NAV[sp].groups) for (const p of g.pages) (menus[p.to] ??= new Set()).add(sp);

test("no page is in two spaces' menus, and every entry is listed once in the one menu", () => {
  for (const [to, sps] of Object.entries(menus)) assert.equal(sps.size, 1, to);
  const ids = MENU.flatMap((s) => s.groups.map((g) => g.id));
  assert.equal(new Set(ids).size, ids.length, ids.join(", "));
  assert.equal(ids.filter((id) => id === "calendar").length, 1);
});

test("every page opens in its own address's space, whatever space it was reached from or an old ?space= says", () => {
  for (const to of Object.keys(menus)) for (const from of [...SPACE_IDS, "mine"])
    assert.equal(menuView(to, from), spaceOf(to) ?? "mine", `${to} from ${from}`);
  assert.equal(menuView("/", "trade"), "trade");
});

test("the shell takes the space from the address alone and writes no ?space= into it", () => {
  const shell = readFileSync(new URL("../src/components/Shell.tsx", import.meta.url), "utf8");
  assert.match(shell, /const space = menuView\(path, saved\);/);
  assert.doesNotMatch(shell, /q\.set\("space"|sharedPage|spaceParam/);
});
