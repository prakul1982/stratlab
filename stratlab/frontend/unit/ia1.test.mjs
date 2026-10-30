// IA-1 (owner, 29 Oct): the menu's 42 entries settled into 14, each a page of tabs; nothing removed, every old address still
// opens its page as a tab, search and Help find a feature by its old name and its new one, and the plan locks are unchanged.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { register } from "node:module";
import { readFileSync } from "node:fs";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { ALL_GROUPS, ALL_PAGES, NAV, locate, locateGroup, placeName, startOf } = await import("../src/lib/nav.ts");
const { match } = await import("../src/lib/features.ts");
const { PAGE_GATES } = await import("../src/lib/gates.ts");
const { isAppPath } = await import("../src/lib/deepLinks.ts");
const { titleFor } = await import("../src/lib/title.ts");
const { ipoRows, mergeRows } = await import("../src/lib/calendarRows.ts");
const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

// every address the menu had before IA-1, with the entry and tab it opens now
const MOVED = {
  "/notebooks": ["strategies", "Notebooks"], "/library": ["strategies", "Strategy library"], "/import": ["strategies", "Import"],
  "/trade/signals": ["practise", "Forward test"], "/paper": ["practise", "Paper trading"], "/options": ["practise", "Options builder"], "/trade/replay": ["practise", "Chart replay"],
  "/trade/positioning": ["fo-desk", "Positioning"], "/trade/fo-changes": ["fo-desk", "F&O changes"], "/trade/closing-auction": ["fo-desk", "Closing auction"],
  "/trade/events": ["calendar", "Market events"], "/trade/journal": ["my-trades", "Trade journal"],
  "/research": ["companies", "Look up a company"], "/research/compare": ["companies", "Compare"],
  "/invest/business-updates": ["companies", "Business updates"], "/invest/holders": ["companies", "Named holders"],
  "/research/screens": ["find-stocks", "Figures"], "/research/scan": ["find-stocks", "Chart rules"], "/research/filings": ["find-stocks", "Filings"],
  "/research/themes": ["themes", "Themes"],
  "/research/pulse": ["market-today", "Mood"], "/invest/breadth": ["market-today", "Breadth"], "/research/rotation": ["market-today", "Sectors"], "/news": ["market-today", "Today's brief"],
  "/invest/etf-gaps": ["market-data", "ETF vs NAV"], "/invest/margin-funding": ["market-data", "Margin funding"], "/invest/stock-lending": ["market-data", "Stock lending fees"],
  "/research/results": ["calendar", "Results"], "/research/corporate-actions": ["calendar", "Corporate actions"], "/invest/ipos": ["calendar", "IPOs"],
  "/research/watchlist": ["watch", "Stocks"], "/alerts": ["watch", "Alerts"],
  "/money/net-worth": ["portfolio", "Net worth"], "/holdings": ["portfolio", "Holdings"], "/money/mutual-funds": ["portfolio", "Mutual funds"],
  "/tax-report": ["tax", "Tax report"], "/money/tax-tools": ["tax", "Tax tools"], "/money/us-tax": ["tax", "US stocks tax"], "/money/itr": ["tax", "ITR export"],
  "/money/sip-test": ["plan", "Test a SIP"], "/money/rates": ["plan", "Rates"], "/money/calendar": ["calendar", "My money dates"],
};

test("IA-1: about 15 entries, every old address is a tab of the entry it belongs to, and none was removed", () => {
  assert.equal(ALL_GROUPS.length, 14);
  assert.equal(Object.keys(MOVED).length, 42);
  for (const [to, [entry, tab]] of Object.entries(MOVED)) {
    const at = locate(to);
    assert.ok(at, `${to} has no page`);
    assert.equal(at.page.to, to, `${to} is its own tab`);
    assert.equal(at.group.id, entry, `${to} is in ${entry}`);
    assert.equal(at.page.label, tab);
    assert.ok(isAppPath(to), `${to} is still an app address`);
  }
  // the detail pages under a tab stay where they were
  assert.equal(locate("/invest/ipos/in-abc").page.to, "/invest/ipos");
  assert.equal(locate("/research/US/AAPL").group.id, "companies");
  assert.equal(locate("/options/s/abc").group.id, "practise");
  // the two new tabs are app addresses, and the site sends them (and the Calendar) to the app
  for (const to of ["/calendar", "/invest/flows"]) assert.ok(isAppPath(to) && locate(to)?.page.to === to, to);
  const rule = JSON.parse(read("vercel.json")).rewrites.find((r) => r.destination === "/index.html");
  assert.match(rule.source, /\|calendar\)/);
  assert.match(read("public/sw.js"), /\|dev\|calendar\)/);
  assert.match(read("src/main.tsx"), /<Route path="\/calendar" element=\{<CalendarPage \/>\} \/>/);
  assert.match(read("src/main.tsx"), /<Route path="\/invest\/flows" element=\{<FlowsPage \/>\} \/>/);
});

test("IA-1: the one Calendar is in every space's menu, each opening it pre-filtered for that space", () => {
  const cal = (s) => NAV[s].groups.find((g) => g.id === "calendar");
  assert.ok(cal("trade") && cal("trade") === cal("invest") && cal("invest") === cal("money"));
  assert.equal(startOf(cal("trade"), "trade"), "/trade/events");
  assert.equal(startOf(cal("invest"), "invest"), "/calendar");
  assert.equal(startOf(cal("money"), "money"), "/money/calendar");
  assert.deepEqual(cal("invest").pages.map((p) => p.label), ["All dates", "Results", "Corporate actions", "IPOs", "Market events", "My money dates"]);
  // each tab keeps its own space, so the trail and the menu agree with its address
  assert.equal(locate("/trade/events").space, "trade");
  assert.equal(locate("/money/calendar").space, "money");
  assert.equal(locate("/research/results").space, "invest");
  // listed once in All features and in "More you can do"'s other spaces
  assert.equal(ALL_GROUPS.filter((g) => g.group.id === "calendar").length, 1);
});

test("IA-1: the old group pages open the entry that took them over", () => {
  for (const [path, id] of [["/trade/g/build-and-test", "strategies"], ["/trade/g/practise", "practise"], ["/trade/g/my-trades", "my-trades"],
    ["/invest/g/market-view", "market-today"], ["/invest/g/company-news", "calendar"], ["/invest/g/watch", "watch"], ["/money/g/what-you-own", "portfolio"], ["/money/g/plan", "plan"]]) {
    assert.equal(locateGroup(path)?.group.id, id, path);
  }
  assert.match(read("src/pages/NavPages.tsx"), /if \(pathname\.replace\(\/\\\/\$\/, ""\) !== groupPath\(g\.space, g\.group\)\) return <Navigate to=\{groupPath\(g\.space, g\.group\)\} replace \/>;/);
});

test("IA-1: search finds every page by its old name and its new one, and says where it is now", () => {
  for (const [old, to] of [["Screener", "/research/screens"], ["Trend scan", "/research/scan"], ["Red flags", "/research/filings"], ["Market pulse", "/research/pulse"],
    ["Market breadth", "/invest/breadth"], ["Sector rotation", "/research/rotation"], ["Stock alerts", "/alerts"], ["Money calendar", "/money/calendar"], ["Briefs", "/news"],
    ["Import a strategy", "/import"], ["ITR-ready export", "/money/itr"]]) {
    assert.equal(match(old, 3)[0]?.to, to, `"${old}" finds ${to}`);
  }
  for (const [name, to] of [["Figures", "/research/screens"], ["Chart rules", "/research/scan"], ["Find stocks", "/research/screens"], ["Market today", "/research/pulse"],
    ["Calendar", "/calendar"], ["Flows", "/invest/flows"], ["Portfolio", "/money/net-worth"], ["Market data", "/invest/etf-gaps"]]) {
    assert.equal(match(name, 3)[0]?.to, to, `"${name}" finds ${to}`);
  }
  const screener = match("Screener", 1)[0];
  assert.equal(screener.title, "Find stocks › Figures (Screener)");
  assert.equal(placeName(locate("/research/themes")), "Themes");
  // a renamed tab's browser title names its entry; an unchanged one keeps its title
  assert.equal(titleFor("/research/screens"), "Figures · Find stocks · StratLab");
  assert.equal(titleFor("/holdings"), "Holdings · StratLab");
});

test("IA-1: the plan locks are the ones they were, now on the tabs", () => {
  const before = {
    "/trade/signals": ["signal_webhooks", true], "/trade/replay": ["chart_replay", true], "/research/scan": ["scans", true], "/research/investor": ["investor_home", true],
    "/research/filings": ["filings", true], "/invest/breadth": ["breadth", false], "/trade/positioning": ["positioning", false], "/trade/positioning/stocks": ["stock_futures", false],
    "/trade/journal": ["journal", false], "/trade/closing-auction": ["cas_history", false], "/trade/fo-changes": ["fo_alerts", false], "/trade/events": ["event_reminders", false],
    "/invest/etf-gaps": ["etf_gaps", false], "/invest/margin-funding": ["mtf", false], "/invest/ipos": ["ipo_alerts", false], "/invest/business-updates": ["biz_updates", true],
    "/invest/holders": ["holders", true], "/money/net-worth": ["networth", false], "/money/mutual-funds": ["mf_gains", false], "/money/tax-tools": ["tax_tools", false],
    "/money/us-tax": ["us_tax", false], "/money/itr": ["itr_export", false], "/money/sip-test": ["sip_luck", false], "/money/rates": ["rates_slab", false],
    "/money/calendar": ["money_reminders", false], "/options": ["options", false],
  };
  for (const [to, [feature, whole]] of Object.entries(before)) assert.deepEqual(PAGE_GATES[to], { feature, whole }, to);
  // the only new gate: Flows is Positioning's cash card and history, on Positioning's plan
  assert.deepEqual(PAGE_GATES["/invest/flows"], { feature: "positioning", whole: false });
  assert.equal(Object.keys(PAGE_GATES).length, Object.keys(before).length + 1);
  const tabs = read("src/components/HubTabs.tsx");
  assert.match(tabs, /const locked = off && gate!\.whole;/);
  assert.match(tabs, /<span className="side-lock" data-plan=\{plan\} aria-hidden="true" \/>/);
});

test("IA-1: the menu is one short list of entries; the tabs show on each tab's page, not on a company's or a notebook's", () => {
  const shell = read("src/components/Shell.tsx");
  assert.match(shell, /<div className="side-list side-nav side-entries">/);
  assert.doesNotMatch(shell, /side-toggle|aria-label="Open or close this group"/);
  assert.match(shell, /<div className="crumb-row"><PageBreadcrumb mine=\{space === "mine"\} space=\{space\} \/>\{at && <HubTabs at=\{at\} path=\{path\} \/>\}<\/div>/);
  assert.match(read("src/styles.css"), /\.hub-tabs \{ display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 0 auto; \}/);          // on the breadcrumb's row: every title starts at one height (R17)
  assert.match(read("src/styles.css"), /@media \(max-width: 640px\) \{ \.hub-tabs \{ display: none; \} \}/);          // a phone has them in the breadcrumb's menu
  assert.match(read("src/components/PageBreadcrumb.tsx"), /const tabs = !one && phone \? group\.pages\.map/);
  const tabs = read("src/components/HubTabs.tsx");
  assert.match(tabs, /if \(at\.group\.pages\.length < 2 \|\| \(p !== at\.page\.to && !TAB_VIEWS\.includes\(p\)\)\) return null;/);
  // Help lists every page by its old name with where it is now; the tour has a step on the menu's entries and tabs
  const help = read("src/pages/AppGates.tsx");
  assert.match(help, /testId="help-places"/);
  assert.match(help, /cell: \(l\) => l\.page\.was \?\? l\.page\.label/);
  assert.match(read("src/components/Tour.tsx"), /\{ title: "One page for each job", at: \[".sidebar .side-groups"\], menu: true,/);
});

test("IA-1: All dates merges the calendars in date order, and an IPO's dates each make a row", () => {
  const ipo = { id: "in-x", market: "IN", name: "Acme", stage: "upcoming", open: "2026-11-02", close: "2026-11-04", listing: "2026-11-09", low: 100, high: 105, lot: 140, currency: "INR" };
  const rows = ipoRows([ipo], "2026-10-30", "2026-11-06");
  assert.deepEqual(rows.map((r) => [r.date, r.detail.split(" · ")[0]]), [["2026-11-02", "Opens"], ["2026-11-04", "Closes"]]);        // the listing is past the window
  assert.match(rows[0].detail, /price band ₹100–₹105 · lot 140/);
  assert.equal(rows[0].to, "/invest/ipos/in-x");
  const m = mergeRows([[{ id: "a", date: "2026-11-02", type: "event", name: "RBI policy", to: "/trade/events", detail: "" }],
    [{ id: "b", date: "2026-11-02", type: "results", name: "TCS", to: "/research/IN/TCS", detail: "" }, { id: "c", date: "2026-10-31", type: "money", name: "Advance tax", to: "/money/calendar", detail: "" }]]);
  assert.deepEqual(m.map((r) => r.id), ["c", "b", "a"]);
});

test("IA-1: the space homes and 'More you can do' follow the menu's entries", () => {
  const ex = read("src/components/Explore.tsx");
  assert.match(ex, /const sections = NAV\[own\]\.groups\.map\(\(g\) => \(\{ g, tiles: tilesOf\(g\) \}\)\)/);
  assert.match(ex, /<DataTable stack label="Menu entries in the other spaces"/);
  assert.match(ex, /const ones = sections\.filter\(\(x\) => x\.tiles\.length === 1\)/);          // no heading over one card saying the same
  const homes = read("src/pages/SpaceHomes.tsx");
  assert.match(homes, /const entries = NAV\.money\.groups\.map/);
  assert.match(homes, /<Link to="\/calendar" className="link small">Calendar →<\/Link>/);
});
