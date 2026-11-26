// cal94 (owner, 26 Nov: "should we put calendar only in My space? … any better idea?" → "yes sounds good"): one Calendar, fixed in the
// sidebar's top part in every space and in no space's menu list, opening on the dates for where you are, with one row of filters inside
// it whose choice is the address and is kept per space. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { ALL_PAGES, CALENDAR, NAV, SPACE_LIST, locate, locateGroup, startOf } = await import("../src/lib/nav.ts");
const { CAL_SHOWS, askedShow, calDefault, calEntry, calHref, keptShow } = await import("../src/lib/calendarShow.ts");
const { match } = await import("../src/lib/features.ts");

test("one Calendar: fixed, in no space's menu list; the research tables stay in Invest's menu, nothing lost", () => {
  assert.ok(CALENDAR.fixed);
  for (const s of SPACE_LIST) assert.ok(!NAV[s].groups.some((g) => g.fixed || g.id === "calendar"), s);
  const invest = NAV.invest.groups.flatMap((g) => g.pages.map((p) => p.to));
  for (const to of ["/research/results", "/research/corporate-actions", "/invest/ipos", "/research/earnings-calls"]) {
    assert.ok(invest.includes(to), to);
    assert.equal(locate(to).space, "invest");
  }
  // its addresses are its filters, each found where it was; every space's old entry page still opens something
  for (const to of ["/calendar", "/trade/events", "/money/calendar"]) assert.equal(locate(to).group.id, "calendar", to);
  for (const s of SPACE_LIST) assert.equal(locateGroup(`/${s}/g/calendar`).group.id, "calendar", s);
  assert.equal(ALL_PAGES.filter((l) => l.group.id === "calendar").length, 3);
});

test("it opens on the dates for where you are", () => {
  assert.equal(startOf(CALENDAR, "trade"), "/trade/events");
  assert.equal(startOf(CALENDAR, "money"), "/money/calendar");
  assert.equal(startOf(CALENDAR, "invest"), "/calendar");
  assert.equal(calDefault("trade", true), "events");
  assert.equal(calDefault("money", true), "money");
  for (const s of ["invest", "mine"]) { assert.equal(calDefault(s, true), "mine"); assert.equal(calDefault(s, false), "all"); }
  // the sidebar's entry: the space's own start, or the filter last picked in that space
  assert.equal(calEntry("trade", {}), "/trade/events");
  assert.equal(calEntry("money", null), "/money/calendar");
  assert.equal(calEntry("mine", {}), "/calendar");
  assert.equal(calEntry("trade", { trade: "results" }), "/calendar?show=results");
  assert.equal(calEntry("invest", { invest: "money" }), "/money/calendar");
  // a kept value that is no filter (an old or edited one) counts as none
  assert.equal(keptShow({ trade: "nope" }, "trade"), null);
  assert.equal(keptShow("junk", "trade"), null);
});

test("the filter is the address: its own, the two old addresses, and the older ?type= and ?scope= links", () => {
  assert.deepEqual(CAL_SHOWS.map((s) => s.label), ["All", "My stocks", "Market events & expiries", "Results", "Dividends & splits", "IPOs", "My money dates"]);
  for (const { value } of CAL_SHOWS) { const href = calHref(value); assert.equal(askedShow(href.split("?")[0], href.includes("?") ? `?${href.split("?")[1]}` : ""), value, value); }
  assert.equal(askedShow("/trade/events", "?space=money"), "events");
  assert.equal(askedShow("/money/calendar/", ""), "money");
  assert.equal(askedShow("/calendar", ""), null);
  assert.equal(askedShow("/calendar", "?type=ipo"), "ipos");
  assert.equal(askedShow("/calendar", "?type=ipo,results"), "all");
  assert.equal(askedShow("/calendar", "?scope=mine"), "mine");
  assert.equal(askedShow("/calendar", "?show=bad&scope=all"), "all");
});

test("search still finds it by calendar, expiry and tax due; breadcrumbs say Calendar; storage is wrapped", () => {
  assert.equal(match("calendar", 1)[0].to, "/calendar");
  assert.equal(match("expiry", 5).some((f) => f.to === "/trade/events"), true);
  assert.equal(match("tax due", 5).some((f) => f.to === "/money/calendar"), true);
  const crumb = read("src/components/PageBreadcrumb.tsx");
  assert.match(crumb, /const label = group\.fixed \? group\.label : page\.label;/);
  const shell = read("src/components/Shell.tsx");
  // one entry, in the top part beside the search button, in every space (My space's own list has none of its own)
  assert.equal((shell.match(/data-testid="side-calendar"/g) ?? []).length, 1);
  assert.doesNotMatch(shell, /item\("\/calendar"/);
  // the kept choice goes through the app's storage helper, which never throws with storage off (lib/persist)
  assert.match(read("src/pages/CalendarPage.tsx"), /usePersisted<CalKept>\(CAL_KEPT, \{\}\)/);
  assert.match(read("src/lib/persist.ts"), /try \{ localStorage\.setItem\(key, JSON\.stringify\(value\)\); \} catch/);
});
