// Release 15, the page frame (owner, 7 Nov): sections that close and move, remembered; "Show less" after every "Show more"; standing notes
// at the top; one click that acts at once; the kit's own calendar; no light stripe at a table's edge.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("a page is its route with the thing it shows left out, so a closed section stays closed on every company", async () => {
  const { routeKey } = await import("../src/lib/sections.ts");
  assert.equal(routeKey("/research/IN/RELIANCE"), "/research/IN/*");
  assert.equal(routeKey("/research/US/AAPL/deep"), "/research/US/*/deep");
  assert.equal(routeKey("/research/watchlist"), "/research/watchlist");
  assert.equal(routeKey("/n/abc/e/3"), "/n/*/e/*");
  assert.equal(routeKey("/n/abc/compare"), "/n/*/compare");
  assert.equal(routeKey("/paper/s1"), "/paper/*");
  assert.equal(routeKey("/tax-report/"), "/tax-report");
  assert.equal(routeKey("/money/g/tax"), "/money/g/tax");
});

test("a section is named by its id, else by its title's words", async () => {
  const { sectionSlug } = await import("../src/lib/sections.ts");
  assert.equal(sectionSlug("co-owners", "Who owns it"), "co-owners");
  assert.equal(sectionSlug(undefined, "Dividends, FY 2025-26"), "dividends-fy-2025-26");
  assert.equal(sectionSlug(null, "F&O, commodity and currency"), "f-o-commodity-and-currency");
});

test("Move up and Move down swap a section with its neighbour; the ends stay put; other groups keep their order", async () => {
  const { moved, keptWith } = await import("../src/lib/sections.ts");
  assert.deepEqual(moved(["a", "b", "c"], "b", -1), ["b", "a", "c"]);
  assert.deepEqual(moved(["a", "b", "c"], "b", 1), ["a", "c", "b"]);
  const same = ["a", "b"];
  assert.equal(moved(same, "a", -1), same);
  assert.equal(moved(same, "b", 1), same);
  assert.deepEqual(keptWith(["x", "y", "a", "b"], ["b", "a"]), ["x", "y", "b", "a"]);
  assert.deepEqual(keptWith(undefined, ["b", "a"]), ["b", "a"]);
});

test("the kept order sets each child's CSS order: sections swap places, everything else keeps its own", async () => {
  const { orders } = await import("../src/lib/sections.ts");
  // header, note, a, b, c: the person put c first
  assert.deepEqual(orders([null, null, "a", "b", "c"], ["c", "a", "b"]), [0, 1, 3, 4, 2]);
  // a non-section between sections keeps its place
  assert.deepEqual(orders(["a", null, "b"], ["b", "a"]), [2, 1, 0]);
  // a section the kept order doesn't know (new since) keeps its own place among them
  assert.deepEqual(orders(["a", "n", "b"], ["b", "a"]), [2, 1, 0]);
  // nothing kept, or nothing of it here: nothing set
  assert.equal(orders(["a", "b"], undefined), null);
  assert.equal(orders(["a", "b"], ["z"]), null);
});

test("each person's sections are their own; a visitor's are a guest's", async () => {
  const { setSectionUser, sectionUser, onSectionUser } = await import("../src/lib/sections.ts");
  let heard = 0;
  const off = onSectionUser(() => heard++);
  assert.equal(sectionUser(), "guest");
  setSectionUser("u1");
  assert.equal(sectionUser(), "u1");
  setSectionUser("u1");
  assert.equal(heard, 1, "the same person again is no change");
  setSectionUser(null);
  assert.equal(sectionUser(), "guest");
  off();
});

test("every Card with a title, and every FoldCard, is a section with the close and move buttons, kept per person and page", () => {
  const card = read("src/components/kit/Card.tsx");
  assert.match(card, /useSectionFrame\(el, \{ id, allowed: !compact \}\)/);
  assert.match(card, /data-section=\{frame\.on \? frame\.key/);
  assert.match(card, /\{mine && frame\.on && <SectionControls frame=\{frame\} \/>\}/);
  assert.match(read("src/components/kit/FoldCard.tsx"), /useSectionFrame\(el, \{ id, title, defaultOpen: initial \}\)/);
  const sec = read("src/components/kit/Section.tsx");
  assert.match(sec, /aria-label=\{frame\.open \? "Close section" : "Open section"\}/);
  assert.match(sec, /aria-expanded=\{frame\.open\}/);
  for (const item of ["Move up", "Move down", "Reset order"]) assert.ok(sec.includes(`label: "${item}"`), item);
  assert.match(sec, /usePersisted<Folds>\(`\$\{FOLDS_KEY\}\.\$\{user\}`/);
  assert.match(read("src/components/Shell.tsx"), /setSectionUser\(me\?\.id\)/);
  const css = read("src/styles.css");
  assert.match(css, /\.k-card\.k-folded > :not\(\.k-card-head\) \{ display: none !important; \}/);
  // "On this page" opens a closed section and follows the person's order
  assert.match(read("src/components/kit/PageNav.tsx"), /openSection\(el\)/);
});

test("every Show more has a Show less (owner, 7 Nov)", () => {
  assert.match(read("src/components/kit/DataTable.tsx"), /\{pages > 1 && <ShowLess onLess=\{\(\) => setPages\(1\)\} \/>\}/);
  for (const f of ["src/components/Filings.tsx", "src/components/Deals.tsx", "src/components/NamedHolders.tsx", "src/components/BizUpdates.tsx",
    "src/components/TaxUnits.tsx", "src/pages/TaxReportPage.tsx", "src/pages/EtfGapsPage.tsx", "src/components/ThemeDive.tsx", "src/components/HoldingsActions.tsx",
    "src/components/CorpActions.tsx", "src/pages/ResultsPage.tsx", "src/pages/trade/ClosingAuctionPage.tsx", "src/pages/trade/StockFuturesPage.tsx",
    "src/pages/trade/JournalPage.tsx", "src/pages/admin/AuditPanel.tsx", "src/pages/Screens.tsx", "src/components/LibraryBits.tsx"]) {
    assert.match(read(f), /<ShowLess /, f);
  }
  assert.doesNotMatch(read("src/components/CorpActions.tsx"), /Show fewer/);
  const less = read("src/components/kit/ShowLess.tsx");
  assert.match(less, /scrollIntoView\(\{ block: "start"/);
});

test("a standing note (Estimate only) goes to the top of the page under its title, on every page", () => {
  const n = read("src/components/kit/Notice.tsx");
  assert.match(n, /const standing = top \?\? \(role === "note" && tone === "info" && !action && !actions\);/);
  assert.match(n, /createPortal\(box, slot\)/);
  assert.match(n, /closest\("\.k-card, form, \[role=dialog\]/);
});

test("one click acts at once: a move to another page is not a transition that leaves the old page standing", () => {
  assert.match(read("src/main.tsx"), /<BrowserRouter useTransitions=\{false\}>/);
  // a press outside an open menu or (i) leaves the focus where it was pressed: no jump back to the menu's button under the pointer
  assert.match(read("src/components/kit/Dialog.tsx"), /\{ was\.current = false; close\.current\(false\); \}/);
});

test("the kit's calendar: day arithmetic that no time zone moves, Monday-first weeks", async () => {
  const { addDays, addMonths, monthGrid, monthTitle, dayName } = await import("../src/lib/dateInput.ts");
  assert.equal(addDays("2026-02-28", 1), "2026-03-01");
  assert.equal(addDays("2026-01-01", -1), "2025-12-31");
  assert.equal(addMonths("2026-01-31", 1), "2026-02-28");
  assert.equal(addMonths("2026-03-15", -12), "2025-03-15");
  const g = monthGrid("2026-11-06");
  assert.equal(g.length, 42);
  assert.equal(g[0], "2026-10-26", "1 Nov 2026 is a Sunday: the grid starts on the Monday before");
  assert.ok(g.includes("2026-11-30"));
  assert.equal(monthTitle("2026-11"), "November 2026");
  assert.equal(dayName("2026-11-06"), "Friday 6 November 2026");
  const d = read("src/components/kit/DateInput.tsx");
  assert.doesNotMatch(d, /showPicker|type="date"/, "never the browser's own calendar");
  assert.match(d, /onClick=\{\(\) => \{ if \(!cal\) setCal\(\{ grid: false \}\); \}\}/, "a click on the box opens it");
});

test("no light stripe at a table's right edge: no painted edge shadow, only the fade while it can scroll", () => {
  const css = read("src/styles.css");
  const wrap = css.slice(css.indexOf(".k-tbl-wrap { position: relative;"), css.indexOf("}", css.indexOf(".k-tbl-wrap { position: relative;")));
  assert.doesNotMatch(wrap, /gradient/);
  assert.doesNotMatch(css, /farthest-side at 100% 50%/);
  assert.match(css, /animation-timeline: scroll\(self inline\)/);
});

test("R15 CI: the date picker's classes are its own (k-dp), never the market calendar's (k-cal), which they had squeezed", () => {
  const css = read("src/styles.css");
  assert.doesNotMatch(css, /^\.k-cal(-row|-grid|-head|-day)?\s*\{/m);
  assert.match(css, /^\.k-dp \{ position: absolute;/m);
  assert.doesNotMatch(read("src/components/kit/DateInput.tsx"), /k-cal/);
});

test("R15 CI: a page whose file has arrived draws at once; the section menu's dots are no svg; a More list's menu entry comes first", () => {
  assert.match(read("src/main.tsx"), /const \[Ready\] = useState<ComponentType \| null>\(\(\) => arrived\.get\(load\)\?\.\[name\] \?\? null\);/);
  assert.doesNotMatch(read("src/components/kit/Section.tsx"), /<svg/);
  const more = read("src/components/MoreTools.tsx");
  assert.ok(more.indexOf('header: "Menu entry"') < more.indexOf('header: "Tool"'));
});
