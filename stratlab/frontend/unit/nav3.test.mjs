// NAV3 (CX-1 review, 16 Nov: crowdedness 3/10, ~55 menu links, the Calendar in three spaces, Themes twice, "16/24/6/9 more tools" teasers,
// a ~60-row plans table, three public navs; owner OK the same day: merge or hide menu entries and pages, nothing deleted, every old URL
// working). Plus LIVE9A-019 (one public header; real samples from several markets), LIVE9A-025 (Themes highlighted twice) and LIVE9B-009
// (the Free card's grace line). Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const { ALL_PAGES, NAV, SPACE_LIST, locate, locateGroup } = await import("../src/lib/nav.ts");
const { pickExamples, exampleEyebrow } = await import("../src/lib/landingExamples.ts");
const { graceLine } = await import("../src/lib/freeChange.ts");

// (updated on purpose, R61: the owner asked for the Release 59 sidebar back, "restore it as it was before"; its own tests are back in
// ia1/ia2/nav/r16-nav/spaces-shared/review-*.test.mjs, so the one-menu test of 16 entries is gone. Every address either menu had still opens.)
// every address the menu and its old entries ever had (IA-1's map and the old group pages), plus old shared-Calendar links
const OLD = ["/notebooks", "/library", "/import", "/trade/signals", "/paper", "/options", "/trade/replay", "/trade/positioning", "/trade/positioning/stocks",
  "/trade/fo-changes", "/trade/closing-auction", "/trade/events", "/trade/journal", "/research", "/research/compare", "/invest/business-updates",
  "/invest/groups", "/invest/holders", "/research/search", "/research/screens", "/research/scan", "/research/filings", "/research/themes", "/research/pulse",
  "/invest/breadth", "/invest/heatmap", "/invest/movers", "/research/rotation", "/invest/flows", "/news", "/invest/etf-gaps", "/invest/margin-funding",
  "/invest/stock-lending", "/calendar", "/research/results", "/research/corporate-actions", "/invest/ipos", "/research/earnings-calls", "/research/watchlist",
  "/research/investor", "/alerts", "/money/net-worth", "/holdings", "/money/mutual-funds", "/tax-report", "/money/tax-tools", "/money/us-tax", "/money/itr",
  "/money/sip-test", "/money/rates", "/money/calendar"];
const OLD_GROUPS = ["/trade/g/my-trades", "/trade/g/strategies", "/trade/g/build-and-test", "/trade/g/practise", "/trade/g/fo-desk", "/trade/g/calendar",
  "/invest/g/companies", "/invest/g/find-stocks", "/invest/g/themes", "/invest/g/market-today", "/invest/g/market-view", "/invest/g/market-data",
  "/invest/g/calendar", "/invest/g/company-news", "/invest/g/watch", "/money/g/portfolio", "/money/g/what-you-own", "/money/g/tax", "/money/g/plan", "/money/g/calendar",
  // R61: Release 60's one menu had a More tools entry page; its address still opens an entry
  "/invest/g/more", "/trade/g/more", "/money/g/more"];

test("every old address still opens its own page in the menu, and every old entry page opens the entry that has its pages now", () => {
  for (const to of OLD) assert.ok(locate(to), `${to} lost its place`);
  for (const to of OLD) if (!to.startsWith("/research/investor") && to !== "/trade/positioning/stocks") assert.equal(locate(to).page.to, to);
  for (const g of OLD_GROUPS) assert.ok(locateGroup(g), `${g} opens nothing`);
  // nothing removed: every page of the map is reachable from a space's menu (R61: the R59 sidebar)
  const inMenu = new Set(SPACE_LIST.flatMap((s) => NAV[s].groups.flatMap((g) => g.pages.map((p) => p.to))));
  for (const l of ALL_PAGES) assert.ok(inMenu.has(l.page.to), l.page.to);
  // the routes themselves are unchanged
  const main = read("src/main.tsx");
  for (const to of OLD) if (!/\/research\/investor/.test(to)) assert.ok(main.includes(`path="${to}"`), `${to} has no route`);
});

test("the landing page has no teaser counts and one public header, the same list as every public page and index.html's", async () => {
  const login = read("src/pages/Login.tsx");
  assert.doesNotMatch(login, /\{items\.length - shown\} more|\{rest\} more|\$\{FAQ\.length - 5\} more|more Trade tools/);
  assert.match(login, /const NAV_LINKS = PUBLIC_MENU;/);
  const { PUBLIC_MENU } = await import("../src/components/PublicFrame.tsx").catch(() => ({ PUBLIC_MENU: null }));
  const frame = read("src/components/PublicFrame.tsx");
  const list = [...frame.matchAll(/\["(\/[a-z]*)", "([A-Za-z]+)"\]/g)].map((m) => [m[1], m[2]]).filter(([h]) => h !== "/");
  const boot = read("index.html").match(/<nav class="boot-nav" aria-label="Site">(.*?)<\/nav>/)[1];
  assert.deepEqual([...boot.matchAll(/<a href="([^"]+)">([^<]+)<\/a>/g)].map((m) => [m[1], m[2]]), list.slice(0, 7));
  const server = read("../backend/app/stock_pages.py").match(/PUBLIC_MENU = \(([\s\S]*?)\)\n/)[1];
  assert.deepEqual([...server.matchAll(/\("([^"]+)", "([^"]+)"\)/g)].map((m) => [m[1], m[2]]), list.slice(0, 7));
  void PUBLIC_MENU;
  // one promise in the hero, who it is for, and a real result anyone can open without signing in
  assert.match(login, /<h1 className="serif lp-h1">Is your trading idea <em>skill<\/em> or luck\?<\/h1>/);
  assert.match(login, /<Link className="btn quiet lp-cta-2" to="\/library">See real results, no sign-in<\/Link>/);
  assert.doesNotMatch(read("src/styles.css"), /\.lp-cta-2 \{ display: none; \}|, \.lp-cta-2 \{ display: none; \}/, "a phone keeps the way to a real result");
  // the hero's samples start with one that held up
  assert.ok(login.indexOf('tab: "Bitcoin"') < login.indexOf('tab: "NIFTY 50"'));
});

test("the landing page's real verdicts: one that passed every check and one that failed, from different markets, stocks before currency pairs", () => {
  const e = (id, market, passed, total, verdict, extra = {}) => ({ id, name: id, market, instrument: { symbol: id }, group: null, verdict: { verdict, passed, total }, ...extra });
  const rows = [e("fx1", "CDS", 0, 4, "no_edge"), e("fx2", "CDS", 1, 4, "luck"), e("fx3", "CDS", 4, 4, "edge"),
    e("in1", "IN", 4, 4, "edge"), e("us1", "US", 2, 4, "luck"), e("cr1", "CRYPTO", 1, 4, "no_edge"), e("in2", "IN", 0, 4, "no_edge", { ran: false })];
  const got = pickExamples(rows).map((r) => r.id);
  assert.deepEqual(got, ["in1", "us1", "cr1"]);
  // with only currency pairs, it still shows a pass and a fail
  assert.deepEqual(pickExamples(rows.filter((r) => r.market === "CDS")).map((r) => r.id).slice(0, 2), ["fx3", "fx1"]);
  assert.deepEqual(pickExamples([]), []);
  // the eyebrow is dropped when the title already says it (LIVE9A-019)
  const g = { ...e("x", "CDS", 0, 4, "luck"), group: { name: "4 rupee currency pairs" } };
  assert.equal(exampleEyebrow(g, "Breakout · 4 rupee currency pairs"), null);
  assert.equal(exampleEyebrow(e("RELIANCE", "IN", 0, 4, "luck"), "Moving average cross"), "RELIANCE");
});

test("the plans table shows 12 rows at a glance; the full comparison is one fold below, its rows unchanged", () => {
  const src = read("src/components/PlanCompare.tsx");
  const glance = src.slice(src.indexOf("const glance: Row[] = ["), src.indexOf("];", src.indexOf("const glance: Row[] = [")));
  const rows = (glance.match(/\{ id: "g-[a-z]+"/g) ?? []).length + (/\.\.\.FLAG_GROUPS\.map/.test(glance) ? 3 : 0);
  assert.equal(rows, 12);
  assert.match(src, /<Disclosure summary="The full comparison, row by row">/);
  // same plans, same prices, same limits: the glance reads the same LIMITS and features as the full table
  assert.match(glance, /num\(p, "backtests_per_month"\)/);
  assert.doesNotMatch(glance, /\b\d{2,}\b(?! a day)/);
});

test("LIVE9B-009: the Free card's grace line is one short sentence, with AI never lower-cased, and the counts in Account's table", () => {
  const fc = { on: "2026-11-27T00:00:00Z", moves: [], rows: [
    { label: "Fresh AI reads a day", before: 60, after: 5 }, { label: "AI answers in the search box a day", before: 40, after: 10 },
    { label: "AI strategy builds a month", before: 10, after: 5 }, { label: "Saved screens", before: 3, after: 3 }] };
  const line = graceLine(fc);
  // (updated on purpose, LIVE13B-006: "limits on 3 counts" read like a count of backtests; it says how many of the card's limits stay higher)
  // (updated on purpose, site76 LIVE14B-016: "of the limits above" stood under a card of 5 lines with 10 changed: "of your Free limits")
  assert.equal(line, "Until 27 Nov 2026, 3 of your Free limits stay at your earlier, higher levels.");
  assert.doesNotMatch(line, /aI/);
  assert.ok(line.length < 110);
  assert.match(read("src/pages/PlansPage.tsx"), /\{graceLine\(me\.free_change\)\} <Link className="link" to="\/account#free-change">See what changes<\/Link>/);
});
