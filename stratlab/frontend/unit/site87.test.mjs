import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as S from "../src/lib/scrollRows.ts";
import * as T from "../src/lib/themeMarket.ts";
import { minus, minusNode } from "../src/lib/format.ts";

// site87 (Release 87): the owner's rules. The pages are proved in the browser (e2e/site87.spec.ts); these pin the arithmetic and the contract.
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("SCROLL BY SCREEN: content that fits its room is drawn whole; past it, whole rows, never for fewer than three hidden", () => {
  const rows = Array.from({ length: 16 }, (_, i) => 44 * (i + 1) + 40);     // a header row of 40, then 16 rows of 44: 744 px
  assert.equal(S.scrollCut(rows, 800).over, false, "Mood's 16 sectors fit a laptop screen: no scroll");
  const small = S.scrollCut(rows, 480);
  assert.equal(small.over, true);
  assert.equal(small.fit, 44 * 10 + 40, "ends on a whole row");
  assert.equal(rows.length - small.shown, 6);
  // one or two rows past the room: drawn whole, the block grows
  assert.equal(S.scrollCut(rows, 744 - 44).over, false, "one row hidden: no scroll");
  assert.equal(S.scrollCut(rows, 744 - 88).over, false, "two rows hidden: no scroll");
  assert.equal(S.scrollCut(rows, 744 - 132).over, true, "three rows hidden: it scrolls");
  assert.equal(S.MIN_HIDDEN, 3);
});

test("the room on a screen: the viewport less the sticky header, the block's head (at most a quarter of the screen) and its foot (a tenth)", () => {
  assert.equal(S.screenRoom(900, 0, 80, 20), 900 - 80 - 20 - S.SCREEN_GAP);
  assert.equal(S.screenRoom(844, 56, 70, 0), 844 - 56 - 70 - S.SCREEN_GAP);
  assert.equal(S.screenRoom(600, 0, 500, 0), Math.floor(600 - 0.25 * 600 - S.SCREEN_GAP), "a tall head leaves the rows a useful box");
  assert.equal(S.screenRoom(100, 0, 0, 200), 100 - 10 - S.SCREEN_GAP, "what sits under the rows counts up to a tenth of the screen");
  assert.equal(S.screenRoom(900, 0, 0, 5000), 900 - 90 - S.SCREEN_GAP);
});

test("AUTO-LOAD: the next rows are asked for near the end of the rows drawn", () => {
  assert.equal(S.nearEnd(0, 600, 3000), false);
  assert.equal(S.nearEnd(2000, 600, 3000), true);
  assert.equal(S.nearEnd(1999, 600, 3000, 400), false);
});

test("the one scroll: every table and list block uses it; no phone paging, no row counts, no show-more anywhere", () => {
  const dt = read("src/components/kit/DataTable.tsx");
  assert.match(dt, /useScrollRows\(box, \{ items: bodyRows, onEnd: loadMore \}\);/);
  assert.doesNotMatch(dt, /phonePage \* pages|Show \{Math\.min|<ShowLess /);
  assert.match(dt, /Loaded \{allRows\.length\.toLocaleString\("en-IN"\)\} of /);
  const sl = read("src/components/kit/ScrollList.tsx");
  assert.doesNotMatch(sl, /new ResizeObserver\(/);                          // R7T-014
  assert.match(sl, /let avail = screenRoom\(window\.innerHeight, stickyTop\(\), head, below\);/);
  assert.match(sl, /window\.addEventListener\("resize", run\);/);
  // a card beside a column of stacked cards: the column's stacked content is the peer
  assert.match(sl, /return last\.getBoundingClientRect\(\)\.top - p\.getBoundingClientRect\(\)\.top \+ peerNatural\(last\);/);
  for (const f of ["src/components/ThemeDive.tsx", "src/components/LibraryBits.tsx", "src/components/BizUpdates.tsx", "src/pages/TaxReportPage.tsx",
    "src/pages/EtfGapsPage.tsx", "src/pages/ResultsPage.tsx", "src/pages/CalendarPage.tsx", "src/pages/trade/JournalPage.tsx", "src/pages/trade/StockFuturesPage.tsx",
    "src/pages/trade/ClosingAuctionPage.tsx", "src/pages/admin/AuditPanel.tsx", "src/pages/admin/RulesPanel.tsx", "src/pages/admin/UsersSection.tsx",
    "src/pages/Screens.tsx", "src/pages/ResearchScans.tsx", "src/pages/DocSearchPage.tsx", "src/pages/HoldersPage.tsx", "src/pages/ThemesPage.tsx",
    "src/components/InstrumentSearch.tsx", "src/components/kit/ChartFrame.tsx", "src/pages/DevKit.tsx"]) {
    const src = read(f);
    assert.doesNotMatch(src, /<ShowLess |<Pager |phonePage=|scrollRows=\{|>Show all \{(?![^<]*on the chart)|Show \{Math\.min|Show more \(|Show 12 more<|label="Fewer themes"|summary="More ideas"/, f);
  }
  // long server lists load on their own
  assert.match(read("src/pages/ResearchScans.tsx"), /more=\{\{ total: data\.pages > pageAt \? Math\.max\(data\.total, items\.length \+ 1\) : items\.length, load: loadMore/);
  assert.match(read("src/pages/Screens.tsx"), /more=\{out \? \{ total: out\.rows\.length \? out\.total : rows\.length, load: \(\) => run\(rows\.length\), busy: loading, noun: "companies" \} : undefined\}/);
  assert.match(read("src/pages/HoldersPage.tsx"), /const pages = useAutoPages\(data,/);
  assert.match(read("src/pages/DocSearchPage.tsx"), /<ScrollList label=\{`Results for \$\{ans\.q\}`\} testId="ds-hits-box" onEnd=/);
});

test("side by side ends level: panels stretch, a column's last card fills it; the watchlist's CSV in the card's menu, no inner box", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.space-panels \{ align-items: stretch; \}/);
  assert.match(css, /\.grid2 > \.space-col > :last-child, \.k-cols > \.space-col > :last-child \{ flex: 1 0 auto; \}/);
  assert.match(css, /\.k-card > \.k-card-head \+ \.k-tbl-wrap:not\(\.pinhead\):not\(\.stack\)/);
  assert.match(read("src/components/Research.tsx"), /<DataTable csv=\{`watchlist \$\{label\}`\} csvInMenu /);
  const sec = read("src/components/kit/Section.tsx");
  assert.match(sec, /\.\.\.frame\.extra\.map\(\(e\) => \(\{ \.\.\.e, ok: true \}\)\),/);
  assert.match(read("src/components/kit/DataTable.tsx"), /setExtra\(csvKey, menuCsv \? \{ label: "Download CSV", run: \(\) => saveRef\.current\(\), testId: "card-menu-csv" \} : null\);/);
});

test("THEMES: a theme naming one market's country is that market's own", () => {
  for (const q of ["India defence", "Indian railways", "Bharat electronics"]) assert.equal(T.countryOf(q), "IN", q);
  for (const q of ["US shale", "American banks", "United States housing", "U.S. utilities"]) assert.equal(T.countryOf(q), "US", q);
  for (const q of ["Defence", "Railways capex", "Business services", "Bonus issues"]) assert.equal(T.countryOf(q), null, q);
  assert.equal(T.foreignTheme("India defence", "US"), true);
  assert.equal(T.foreignTheme("India defence", "IN"), false);
  assert.equal(T.withoutCountry("India defence"), "Defence");
  assert.deepEqual(T.twinNames("India defence", "US"), ["Aerospace and defense", "Defence"]);
  assert.deepEqual(T.twinNames("Railways capex", "US"), ["Railways capex"]);
  assert.equal(T.sameByName([{ name: "Aerospace and Defense", q: "aerospace and defense" }], "Aerospace and defense")?.name, "Aerospace and Defense");
  assert.equal(T.sameByName([{ name: "Banks", q: "banks" }], "Defence"), null);
  // never the same theme twice: an idea the chips already show is left out, and never the other market's
  assert.deepEqual(T.ideasBeside(["India defence", "Specialty chemicals", "Digital payments"], [{ name: "Specialty chemicals", q: "specialty chemicals" }], "IN"), ["India defence", "Digital payments"]);
  assert.deepEqual(T.ideasBeside(["India defence", "AI data centers"], [], "US"), ["AI data centers"]);
});

test("THEMES page: a market switch clears the open theme (or opens the other market's own of the same name); the chips are compact", () => {
  const page = read("src/pages/ThemesPage.tsx");
  assert.match(page, /setRegion\(to, \(p\) => p\.delete\("q"\)\);/);
  assert.match(page, /for \(const name of twinNames\(open, to\)\)/);
  assert.match(page, /if \(q && foreignTheme\(q, region\)\)/);
  assert.match(page, /const items = useLibrary\(region, text\)\.filter\(\(i\) => !foreignTheme\(i\.name, region\)\);/);
  assert.match(read("src/lib/research.ts"), /const p = new URLSearchParams\(params\); p\.set\("region", r\); edit\?\.\(p\); setParams\(p, \{ replace: true \}\);/);
});

test("SEARCH FILINGS: one compact form, the market in its top row with Search, two lists as drop-downs, no dashed chips", () => {
  const page = read("src/pages/DocSearchPage.tsx");
  assert.match(page, /<div className="ds-row ds-top">\n\s+<div className="ds-market">/);
  assert.match(page, /<button className="btn ds-go" type="submit"/);
  assert.equal((page.match(/<MultiPick /g) || []).length, 2);
  assert.doesNotMatch(page, /<div className="k-toolbar"><RegionSwitch/);
  assert.match(page, /placeholder=""\n\s+info="Type a day, like 14 Aug 2025, or pick it from the calendar\." \/>/);
  assert.match(read("src/styles.css"), /\.k-chipset \.k-chip\[aria-pressed="false"\] \{ background: transparent; border-style: solid;/);
  assert.match(read("src/pages/docsearch.css"), /\.ds-three \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); \}/);
});

test("a rounded zero is \"0\", never \"−0\", app-wide (owner: Breadth's McClellan on 30 Oct)", () => {
  for (const [a, b] of [["-0", "0"], ["−0", "0"], ["-0.0", "0.0"], ["-0.00%", "0.00%"], ["-₹0", "₹0"], ["(-0)", "(0)"], ["-0.5", "−0.5"], ["-10", "−10"], ["-0.04", "−0.04"]])
    assert.equal(minus(a), b, a);
  assert.equal(minusNode((-0.04).toLocaleString("en-IN", { maximumFractionDigits: 1 })), "0");
  assert.equal(minusNode(-0), "0");
});

test("ui-lint R30 (site87): blocks sized to the screen, scrolls that hide three rows or more, no paging control, a card level with a column", () => {
  const rules = read("e2e/ui-lint-rules.ts");
  assert.match(rules, /\(a\) a \$\{l\.matches\("tbody"\) \? "table" : "list"\}/);
  assert.match(rules, /\(b\) a scroll box that hides/);
  assert.match(rules, /\(c\) a scroll box \$\{Math\.round\(b\.height\)\}px tall/);
  assert.match(rules, /\(d\) "\$\{t\.slice\(0, 40\)\}": a paging or show-more control on a list/);
  assert.match(rules, /column of cards/);
});
