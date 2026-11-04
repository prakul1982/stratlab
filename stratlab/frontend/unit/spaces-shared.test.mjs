// A page in more than one space's menu opens inside the space it was opened from (owner, 4 Nov: "whenever we click on something
// in Calendar it redirects to Invest — keep the main space there only"). Swept over the whole menu map, not a list of examples.
// Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { NAV } = await import("../src/lib/nav.ts");
const { menuView, sharedPage, spaceOf, spaceParam, SPACE_IDS } = await import("../src/lib/spaces.ts");

// every page address and the spaces whose menus list it
const menus = {};
for (const sp of SPACE_IDS) for (const g of NAV[sp].groups) for (const p of g.pages) (menus[p.to] ??= new Set()).add(sp);
const shared = Object.keys(menus).filter((to) => menus[to].size > 1);

test("the menu map's shared pages are exactly the ones sharedPage() names (today: the Calendar's six tabs)", () => {
  assert.ok(shared.length >= 6, shared.join(", "));
  for (const to of ["/calendar", "/research/results", "/research/corporate-actions", "/invest/ipos", "/trade/events", "/money/calendar"]) assert.ok(shared.includes(to), to);
  for (const to of Object.keys(menus)) assert.equal(sharedPage(to), shared.includes(to), to);
});

test("every shared page, reached from every space that lists it, keeps that space; its ?space= keeps it on a fresh load", () => {
  for (const to of shared) for (const sp of menus[to]) {
    for (const saved of [...SPACE_IDS, "mine"]) {
      assert.equal(menuView(to, saved, false, { from: sp }), sp, `${to} from ${sp} (saved ${saved})`);
      assert.equal(menuView(to, saved, false, { search: `?space=${sp}` }), sp, `${to}?space=${sp}`);
      assert.equal(menuView(to, saved, false, { search: `?tab=x&space=${sp}`, from: SPACE_IDS.find((x) => x !== sp) }), sp, "the address wins");
    }
    // a fresh load with no ?space= (a link in an email, a typed address) opens the address's own space, as before
    assert.equal(menuView(to, sp, false, {}), spaceOf(to), `${to} fresh`);
    // reached from My space's own menu, it keeps Mine's when Mine links it; else its own space
    assert.equal(menuView(to, "mine", true, { from: "mine" }), "mine");
    assert.equal(menuView(to, "mine", false, { from: "mine" }), spaceOf(to));
  }
});

test("a page in one space's menu still opens in its own space, whatever space it was reached from", () => {
  for (const to of Object.keys(menus).filter((t) => !shared.includes(t))) for (const from of SPACE_IDS)
    assert.equal(menuView(to, from, false, { from, search: `?space=${from}` }), spaceOf(to) ?? "mine", `${to} from ${from}`);
  assert.equal(spaceParam("?space=nope"), null);
  assert.equal(spaceParam(""), null);
});

test("the shell passes the address and the last page's space, and writes ?space= on a shared page opened in another space", () => {
  const shell = readFileSync(new URL("../src/components/Shell.tsx", import.meta.url), "utf8");
  assert.match(shell, /menuView\(path, saved, keepsMine, \{ search: loc\.search, from: lastSpace\.current \}\)/);
  assert.match(shell, /sharedPage\(path\) && space !== spaceOf\(path\) && spaceParam\(loc\.search\) !== space/);
  assert.match(shell, /q\.set\("space", space\);/);
});
