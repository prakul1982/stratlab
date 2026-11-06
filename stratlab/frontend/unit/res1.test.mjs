// RES-1: the results calendar's table, its filters and what is read for the rows in view.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const page = read("src/pages/ResultsPage.tsx");

test("RES-1: one table a day with the figures a person looks at on a results day", () => {
  assert.match(page, /<DataTable (?:csv=(?:"[^"]*"|\{[^\n]*?\}) )?label=\{`Results on \$\{resultDay\(d\)\}`\} rows=\{on\} rowKey=\{\(r\) => `\$\{r\.symbol\}-\$\{r\.date\}`\} columns=\{on\.some\(\(r\) => r\.fo\) \? columns : columns\.filter\(\(c\) => c\.key !== "im"\)\} stack compact phonePage=\{10\} \/>/);      // R15 #11
  // LIVE4-010: shorter headers that fit one line (the (i) says the rest); the CSV keeps the full names
  // LIVE5-002: revenue and profit share the "Quarter" column (a CSV-only pair keeps them apart); "Implied" fits a 1280 screen
  for (const h of ["Company", "Market value", "Price", '"Day"', "Quarter", "Revenue", "Profit", "Usual move", "Implied"])
    assert.ok(page.includes(`header: ${h.startsWith('"') ? h : `"${h}"`}`), h);
  for (const h of ["Price now", "Revenue YoY", "Profit YoY", "Past results-day moves", "Options imply"]) assert.ok(page.includes(`csvHeader: "${h}"`), h);
  assert.doesNotMatch(page, /className="inv-row"/);        // no chips and no two uneven columns
  assert.doesNotMatch(page, /k-cols/);
});

const filters = read("src/components/CalendarFilters.tsx");
const quotes = read("src/lib/rowQuotes.ts");
const corp = read("src/pages/CorpActionsPage.tsx");

test("RES-1: the filters are size, sector, index, day, purpose, sort and F&O, with counts, kept on this device", () => {
  for (const label of ['label="Company size"', 'label="Index"', 'label="Day"', 'label="Sort by"', "F&amp;O stocks only"]) assert.ok(filters.includes(label), label);
  for (const label of ["Results only", "With other business", 'label="Meeting"']) assert.ok(page.includes(label), label);
  assert.match(page, /<CalendarFilters region=\{region\}/);
  assert.match(page, /keptFilters\(KEEP, NO_FILTERS\)/);
  assert.match(page, /keepFilters\(KEEP, filters\)/);
  assert.match(filters, /localStorage\.getItem\(key\)/);
  assert.match(filters, /localStorage\.setItem\(key, JSON\.stringify\(f\)\)/);
  assert.match(filters, /\$\{total\.toLocaleString\("en-IN"\)\} \$\{plural\(total\)\} · \$\{matching\.toLocaleString\("en-IN"\)\} shown/);
  assert.match(filters, /"Filters"\}\{active \? ` \(\$\{active\}\)` : ""\}/);          // a phone's "Filters (n)"
  assert.match(filters, /\{phone && <button/);
  assert.match(filters, /no market value kept yet, so a size can't place/);
});

test("RES-1: live prices, earlier moves and implied moves are read for every row shown, in the order shown, a few calls at a time", () => {
  // LIVE4-001 (behaviour changed on purpose): every row the page shows, not the first 48 in the list's order (often the folded days gone by)
  assert.match(quotes, /export const LIVE_ROWS = 1000;/);                         // LIVE5-001: a day opened in full ran past 240
  assert.match(page, /shownOrder\(data\.weeks, data\.today\)/);
  assert.match(page, /const quoted = useMemo\(\(\) => symbols\.slice\(0, LIVE_ROWS\), \[symbols\]\)/);
  assert.match(quotes, /useMarketRefresh\(\[region\], read, symbols\.length > 0\)/);          // each minute while the market trades, never otherwise
  assert.match(quotes, /quoteAsk\(\(part\) => researchApi\.quotesPending\(region, part\)\)/);   // LIVE5-001: busy rows are asked again
  assert.doesNotMatch(quotes, /setQuotes\(\{\}\);\n\s*if \(symbols\.length\) read\(\)/);   // more rows keep the prices already read
  assert.match(page, /useRowQuotes\(region, quoted\)/);
  assert.match(page, /readRows<MovesAnswer>\(newMoves,[\s\S]*?\{ size: 12, parallel: 3, alive, untilMs: READ_UNTIL_MS \}/);   // only the rows not asked yet ("Show 50 more")
  assert.match(page, /readRows<Implied>\(list,[\s\S]*?\{ size: 8, parallel: 1, alive, untilMs: READ_UNTIL_MS \}/);
  assert.doesNotMatch(page, /READ_ROUNDS/);                                       // no give-up count that left cells on "Reading"
  assert.match(page, /pending: r\.pending \?\? \[\]/);                          // what the server could not reach in time is asked again (owner, 5 Nov)
  assert.match(page, /if \(r\.available === false && alive\(\)\) setOptionsOn\(false\)/);   // LIVE4-002: no option prices: the column hides, one line says why
  assert.match(page, /Option prices can't be read right now, so the move they imply is not shown\./);
  assert.doesNotMatch(page, /Reading…/);                                           // the kit's bar while a cell loads, a dash when there is nothing
  assert.match(page, /\/research\/results\/moves\?region=/);
  assert.match(page, /\/research\/results\/implied\?symbols=/);
  assert.match(page, /pricesNote\(\{ live: isLive/);                                // LIVE5-001: the footer names the session the prices are of
});

test("RES-1: the corporate actions calendar is a table a day with the same filters and live prices", () => {
  assert.match(corp, /<DataTable (?:csv=(?:"[^"]*"|\{[^\n]*?\}) )?label=\{`Corporate actions going ex on \$\{exDay\(d\)\}`\} rows=\{on\} rowKey=\{\(r\) => r\.id\} columns=\{columns\} stack phonePage=\{10\} \/>/);
  for (const h of ["Company", "Action", "Amount or ratio", "Record date", "Price now", "Yield of this payment", "Market value"]) assert.ok(corp.includes(`header: "${h}"`), h);
  assert.match(corp, /<CalendarFilters region=\{region\}/);
  assert.match(corp, /useRowQuotes\(region, symbols\)/);
  assert.match(corp, /Kind of action/);
  for (const sort of ["Ex-date, soonest first", "Market value, largest first", "Yield of the payment, highest first", "Company name"]) assert.ok(corp.includes(sort), sort);
  assert.doesNotMatch(corp, /inv-row|ActionLine/);
  assert.match(corp, /\(r\.amount \/ x\) \* 100/);          // a dividend's amount over the price now
  assert.match(corp, /The yield is one payment over the price now, not the year's\./);
});

test("RES-1: facts and arrows, never a view: no advice words on the page", () => {
  assert.doesNotMatch(page, /\b(buy|sell|should|accumulate|avoid|trade this)\b/i);
  // the arrow and the sign; the latest moves in a row drop their % (the heading says percent, owner 5 Nov: rows fit the card)
  // LIVE5-011: the arrow from arrowOf, none on a move that prints as 0.0
  assert.match(page, /const t = `\$\{Math\.abs\(v\)\.toFixed\(1\)\}\$\{bare \? "" : "%"\}`;\n\s*return <Signed value=\{v\}>\{`\$\{arrowOf\(v, t\)\}\$\{t\}`\}<\/Signed>;/);
  assert.match(page, /Facts, not a forecast\./);
});

test("RES-1 follow-up: business updates have a chart per company on one range, a category total and the companies that file none", () => {
  const b = read("src/pages/BizUpdatesPage.tsx");
  assert.match(b, /import \{[^}]*Spark[^}]*\} from "\.\.\/components\/kit"/);
  assert.match(b, /\{ value: "6", label: "6 months" \}, \{ value: "12", label: "1 year" \}, \{ value: "24", label: "2 years" \}/);
  assert.match(b, /<Seg label="Range of the small charts" value=\{range\} onChange=\{setRange\}/);
  assert.match(b, /figureColumns\(months\)/);                                  // the sector table
  assert.match(b, /figureColumns\(months, \{ key: "k", header: "From"/);       // and My stocks, on the same range
  assert.match(b, /foot=\{d\.total \?/);
  assert.match(b, /Total of \$\{d\.total\.companies\} companies/);
  assert.match(b, /data-testid="biz-none">No business update among their exchange filings:/);
  assert.match(b, /data-testid="biz-mine-none">No business update among their exchange filings:/);
  assert.doesNotMatch(b, /\b(buy|sell|beat|miss)\b/i);
});

test("owner 5 Nov: the calendars, the filings page and Invest home open on every company unless the account chose its own stocks", async () => {
  const { companiesPref, SCOPE_OPTIONS } = await import("../src/lib/companyScope.ts");
  assert.equal(companiesPref(null), "all");
  assert.equal(companiesPref({ prefs: { level: null } }), "all");
  assert.equal(companiesPref({ prefs: { level: null, companies: "mine" } }), "mine");
  assert.deepEqual(SCOPE_OPTIONS.map((o) => o.value), ["all", "mine"]);                       // every company first
  for (const f of ["src/pages/ResultsPage.tsx", "src/pages/CorpActionsPage.tsx", "src/pages/CalendarPage.tsx"]) {
    const src = read(f);
    assert.match(src, /= useCompanyScope\(\);/, f);
    assert.match(src, /options=\{SCOPE_OPTIONS\}/, f);
    assert.doesNotMatch(src, /params\.get\("scope"\) === "all" \? "all" : "mine"/, f);         // no page defaults to "My stocks" on its own
  }
  assert.match(read("src/pages/ResearchScans.tsx"), /useCompanyScope\("view"\)/);
  assert.match(read("src/pages/SpaceHomes.tsx"), /const scope = companiesPref\(me\);[\s\S]*\/research\/results\?region=\$\{r\}&scope=\$\{scope\}/);
  assert.match(read("src/pages/SettingsPage.tsx"), /savePrefs\(\{ companies: v as CompanyScope \}\)/);
  assert.match(read("src/components/LevelPrompt.tsx"), /savePrefs\(\{ focus: f, level: lvl, space: view, companies \}\)/);
});
