// FIX-1B (28 Oct 2026): the findings of the live-site review LIVE-1B, each with its check. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// the lib modules import each other without an extension: the loader adds it
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

// ---------- Holdings ----------
test("LIVE1B-002: a refused or oversized file's reason stays in the import card and clears the last file's answer", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /setResult\(null\); clearProblem\(\);/);                                  // the last answer goes the moment another file is picked
  assert.match(page, /if \(f\.size > MAX_MB \* 1024 \* 1024\) \{ reject\(`That file is larger than/);   // not a toast
  assert.match(read("src/components/kit/UploadButton.tsx"), /const reject = \(message: string\) => setProblem\(message\);/);
});

test("LIVE1B-001: a read that takes more than a few seconds says it is still at it", () => {
  const src = read("src/components/kit/UploadButton.tsx");
  assert.match(src, /export const SLOW_READ_MS = 4000;/);
  assert.match(src, /busy && slow && <span className="k-note" role="status" data-testid="upload-slow">Still reading\./);
});

test("LIVE1B-004: 'a' or 'an' before a broker's name", async () => {
  const { aFile } = await import("../src/lib/format.ts");
  assert.equal(aFile("Angel One"), "an Angel One file");
  assert.equal(aFile("Upstox"), "an Upstox file");
  assert.equal(aFile("HDFC Securities"), "an HDFC Securities file");
  assert.equal(aFile("ICICI Direct", "tradebook"), "an ICICI Direct tradebook");
  assert.equal(aFile("Zerodha Kite"), "a Zerodha Kite file");
  assert.equal(aFile("Groww"), "a Groww file");
  assert.equal(aFile("CSV"), "a CSV file");
  assert.match(read("src/pages/HoldingsPage.tsx"), /Read as \{aFile\(result\.broker\)\}/);
});

test("LIVE1B-005: a replace says the US stocks are kept; LIVE1B-065: reading the same file twice says so", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /a file replaces your Indian holdings only/);
  assert.match(page, /result\.duplicate \? "you added this same file before, so your holdings are unchanged\./);
});

test("LIVE1B-007: the rupee rate is said once under Holdings' totals", async () => {
  const { usTodayNote } = await import("../src/lib/marketHours.ts");
  const us = { id: "US", name: "US", venues: "", currency: "USD", symbol: "", tz: "America/New_York", hours: { open: "09:30", close: "16:00", days: "Mon-Fri" },
    what: "", costs: "", brokerage: 0, status: "live", max_days: null };
  const closed = new Date("2026-10-09T03:00:00Z");
  assert.equal(usTodayNote([us], { day: -16.35, in_total: true }, 95.21, closed, false), "Today includes your US stocks at their last close: −$16.35 (₹1,557).");
  assert.match(usTodayNote([us], { day: -16.35, in_total: true }, 95.21, closed), /at ₹95\.21 a dollar/);       // elsewhere it still says it
});

test("LIVE1B-008: one 'as of' for each market's prices", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /asOfLabel=\{view\?\.us_prices_at \? "India prices as of" : "Prices as of"\}/);
  assert.match(page, /US prices as of \{asOfText\(view\.us_prices_at, \{ tz: marketTz\("US"\) \}\)\}/);
});

test("LIVE1B-046: Indian shares are whole units, US ones may be fractions; a quantity already held stays allowed", async () => {
  const { qtyProblem } = await import("../src/lib/validate.ts");
  const lim = { min: 0, above: true, max: 1e9 };
  assert.match(qtyProblem("2.5", "IN", lim), /^Whole shares only/);
  assert.equal(qtyProblem("2.5", "US", lim), null);
  assert.equal(qtyProblem("3", "IN", lim), null);
  assert.equal(qtyProblem("2.5", "IN", lim, 2.5), null);          // a bonus left a fraction: saving the average alone is fine
  assert.equal(qtyProblem("0", "IN", lim), "Enter more than 0.");
});

test("LIVE1B-047: a button that is working is dimmed, not drawn as one that cannot be pressed; Add says 'Adding…'", () => {
  const css = read("src/styles.css");
  assert.match(css, /\.btn:disabled\[aria-busy="true"\]:not\(\.quiet\):not\(\.blue\):not\(\.outline\):not\(\.danger\) \{ opacity: \.6; background: var\(--ink\)/);
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /\{busy \? "Adding…" : "Add"\}/);
  assert.match(page, /busy=\{reading\}/);                         // "Reading…" only while a file is read
});

test("LIVE1B-048: Remove from holdings asks first and is a small quiet button, not a twin of Save", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /Remove \{row\.symbol\} from your holdings\? Its quantity and average price are deleted from StratLab\./);
  assert.match(page, /className="btn danger sm" disabled=\{busy\} onClick=\{\(\) => setAsking\(true\)\}/);
  assert.match(page, /Yes, remove \{row\.symbol\}/);
});

test("LIVE1B-019: a figure never breaks inside its digits; ₹100 crore and more is written in crore; thousands of a percent are grouped", async () => {
  const { longRupees, isOneWord, pct } = await import("../src/lib/format.ts");
  assert.equal(longRupees("₹6,85,30,01,63,680"), "₹68,530 cr");
  assert.equal(longRupees("−₹13,50,00,00,000"), "−₹1,350 cr");
  assert.equal(longRupees("₹99,99,99,999"), null);               // nine digits fit as they are
  assert.equal(longRupees("Not available"), null);
  assert.equal(isOneWord("₹1,06,50,136"), true);
  assert.equal(isOneWord("Not available yet"), false);
  assert.equal(pct(13605.84), "+13,605.8%");
  assert.equal(pct(-1234.5, 2), "−1,234.50%");
  assert.equal(pct(12.34), "+12.3%");
  const stat = read("src/components/kit/Stat.tsx");
  assert.match(stat, /const short = text \? longRupees\(text\) : null;/);
  assert.match(stat, /fitFigure\(el\)/);
  assert.match(read("src/styles.css"), /\.k-stat-v\.one \{ white-space: nowrap; overflow: hidden; \}/);
});

// ---------- Tax report ----------
test("LIVE1B-009, 010, 011: one tax figure beside the total; the notes said once; the workings folded; no card for one link", () => {
  const t = read("src/pages/TaxReportPage.tsx");
  assert.doesNotMatch(t, /<Stat label=\{<>Tax on share gains/);                                      // 009: no second tax figure in the gains card
  assert.match(t, /<Stat label=\{`Estimated tax for \$\{y\.label\}`\}/);                           // 010: the top figure is not the next card's heading again
  assert.match(t, /<CardHead title=\{`Total tax estimate, \$\{y\.label\}`\}/);
  assert.doesNotMatch(t, /rep\?\.disclaimer/);                                                      // the long note was the "Covers only..." paragraph twice
  assert.match(t, /for an individual of the age band and residency you choose\. House property, foreign income[^"]*advance tax and TDS already paid aren't included\./);
  assert.match(t, /<Disclosure summary="How we got here">/);                                        // folded
  assert.doesNotMatch(t, /<Disclosure summary="How we got here" open>/);
  assert.doesNotMatch(t, /<Card label="Tax tools">/);                                              // 011
  assert.match(t, /are in <Link className="link" to=\{fyLink\("\/money\/tax-tools", y\.fy\)\}>Tax tools<\/Link>\./);
});

test("LIVE1B-012: the sales table opens with every column from 1280px up", () => {
  const m = read("src/components/MoreColumns.tsx");
  assert.match(m, /export const WIDE_FROM = 1280;/);
  assert.match(m, /stored\(key\) \?\? \(wide && typeof window !== "undefined" && window\.innerWidth >= WIDE_FROM\)/);
  const t = read("src/pages/TaxReportPage.tsx");
  assert.match(t, /useMoreColumns\("tax-sales", 3, true\)/);
  assert.match(t, /useMoreColumns\("tax-below", 3, true\)/);
});

test("LIVE1B-013: the tax upload says 'an Angel One tradebook'", () => {
  assert.match(read("src/pages/TaxReportPage.tsx"), /`Read as \$\{aFile\(result\.broker, result\.kind === "trades" \? "tradebook" : "tax P&L"\)\}`/);
});

test("LIVE1B-014: a year with no trades says so in the year list", () => {
  assert.match(read("src/pages/TaxReportPage.tsx"), /\$\{hasTrades\(x\) \? "" : " · no trades"\}/);
});

test("LIVE1B-068, 069: a year with no trades says so above the figure; the note comes after it; the two downloads are one pair", () => {
  const t = read("src/pages/TaxReportPage.tsx");
  const hint = t.indexOf('label="A year with trades"'), head = t.indexOf("<Headline y={y}"), note = t.indexOf('<Notice label="Estimate only">');
  assert.ok(hint > 0 && hint < head && head < note, "hint, then the figure, then the estimate note");
  assert.equal(t.split('label="A year with trades"').length - 1, 1);                                // said once
  assert.match(t, /<span className="k-btn-pair">/);
  assert.match(read("src/styles.css"), /@media \(max-width: 640px\) \{ \.k-btn-pair \{ display: grid; grid-template-columns: 1fr; width: 100%; \} \.k-btn-pair \.btn \{ width: 100%; \} \}/);
});

// ---------- Mutual funds ----------
test("LIVE1B-015: nothing held says so first; no empty tiles or table", () => {
  const p = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(p, /<EmptyState title="Every scheme in your files has been fully redeemed">/);
  assert.match(p, /\{held\.length > 0 && <Card className="mf-stats">/);
  assert.match(p, /\{held\.length > 0 && <FoldTable label="Schemes" columns=\{schemeCols\} rows=\{held\}/);
  assert.doesNotMatch(p, /<p className="k-note">Every scheme in your files has been fully redeemed\.<\/p>/);
});

test("LIVE1B-016, 018, 049: the 'pick first' hint goes after a read, the choice goes back to Add, a wrong password is said under its box", () => {
  const p = read("src/pages/money/MutualFundsPage.tsx");
  assert.match(p, /\{!picked && !result && <span className="k-note">Pick your statement first\./);
  assert.match(p, /setMode\("add"\);/);
  assert.match(p, /const passwordProblem = isPdf && problem && \/password\/i\.test\(problem\) \? problem : null;/);
  assert.match(p, /label="PDF password"[^\n]*error=\{passwordProblem\}/);
});

test("LIVE1B-017: a total with nothing to say is left out of the costs and habits row", () => {
  const c = read("src/pages/money/FundCosts.tsx");
  assert.match(c, /export const costStatsShown = \(q: CostsQuery\) => q\.c\?\.state === "ok" && !!q\.c\.total && q\.c\.total\.funds > 0;/);
  const b = read("src/pages/money/FundBehaviour.tsx");
  assert.match(b, /return \{ gap: t\.compared > 0, sips: \(t\.sips \?\? 0\) > 0, falls: b\.pending > 0 \|\| \(t\.falls \?\? 0\) > 0, held: t\.avg_days_held != null, long: t\.long_share != null \};/);
  assert.match(b, /\{parts\.sips && <Stat label="SIPs"/);
  assert.match(read("src/pages/money/MutualFundsPage.tsx"), /\{\(costStatsShown\(costs\) \|\| behaviourStatsShown\(habits\)\) && <StatRow>/);
});

test("LIVE1B-064: the footer date is the day it was worked out, not a second 'as of'", () => {
  assert.match(read("src/pages/money/MutualFundsPage.tsx"), /Worked out on \{dateOnly\(view\.as_of\)\}\./);
});

// ---------- Money home, Net worth, US tax, ITR, Tax tools, Calendar, Journal ----------
test("LIVE1B-020: a signed US figure is one unbreakable piece; the US tile's label is short", async () => {
  const nb = read("src/components/NoBreak.tsx");
  assert.match(nb, /text\.split\(\/\(\[−\+-\]\?\[\$₹\]\[\\d,\]\+\(\?:\\\.\\d\+\)\?\)\/\)/);
  assert.match(nb, /className="k-nb"/);
  assert.match(read("src/styles.css"), /\.k-nb \{ white-space: nowrap; \}/);
  for (const f of ["src/pages/HoldingsPage.tsx", "src/pages/MineHome.tsx", "src/pages/SpaceHomes.tsx"]) assert.match(read(f), /<NoBreak text=/, f);
  assert.match(read("src/pages/SpaceHomes.tsx"), /<Fig label="US stocks" value=\{money\(h\.us\.value, "USD"\)\}/);
});

test("LIVE1B-021: Money home's two summary cards are one height", () => {
  assert.match(read("src/styles.css"), /\.space-panels\.money-panels \{ align-items: stretch; \}/);
});

test("LIVE1B-022: a part-paid page's tag says which part", async () => {
  const { featureTag } = await import("../src/lib/offer.ts");
  assert.equal(featureTag("pro", null, { canUse: false, part: true, what: "advance tax" }).label, "Pro for advance tax");
  assert.equal(featureTag("basic", null, { canUse: false, part: true }).label, "Basic for part");        // a page with no named part keeps the old words
  const { PART_WORDS } = await import("../src/lib/gates.ts");
  for (const f of ["tax_tools", "us_tax", "itr_export"]) assert.ok(PART_WORDS[f], f);
  assert.match(read("src/components/PageTags.tsx"), /what: flag \? PART_WORDS\[flag\] : undefined/);
});

test("LIVE1B-024: the restated-holdings note is plain words", async () => {
  const { restatedNote } = await import("../src/lib/networth.ts");
  const n = restatedNote([{ d: "2026-10-28", m: 1 }, { d: "2026-10-29", m: 2 }], 2, (d) => d, "2026-10-29");
  assert.equal(n, "Holdings are valued a different way from 2026-10-29, so no change is shown against earlier days. A change shows from the next day.");
  assert.doesNotMatch(n, /snapshot/);
});

test("LIVE1B-025: a group of two, three or five tiles fills its row", () => {
  assert.match(read("src/components/kit/TilePicker.tsx"), /<div className="k-tiles" data-n=\{g\.tiles\.length\}>/);
  const css = read("src/styles.css");
  assert.match(css, /@container \(min-width: 720px\) \{\n  \.k-tiles\[data-n="2"\] \{ grid-template-columns: repeat\(2, minmax\(0, 1fr\)\); \}\n  \.k-tiles\[data-n="3"\] \{ grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); \}\n  \.k-tiles\[data-n="5"\] \{ grid-template-columns: repeat\(5, minmax\(0, 1fr\)\); \}/);
});

test("LIVE1B-026: the loan sentence is not a live region; LIVE1B-073: a full plan says its limit once in the dialog", () => {
  assert.doesNotMatch(read("src/pages/money/LoanCheck.tsx"), /<p className="k-small" role="status">Your entered rate is/);
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /\{view\.limit != null && !full && <span className="k-note">/);
});

test("LIVE1B-027: each sale in rupees is eight columns, the rate under each rupee figure", () => {
  const p = read("src/pages/money/UsTaxPage.tsx");
  const cols = p.slice(p.indexOf("const saleCols"), p.indexOf("const divCols"));
  assert.equal((cols.match(/\{ key: "/g) ?? []).length, 8);
  assert.doesNotMatch(cols, /header: "Rate used"/);
});

test("LIVE1B-060, 061: the add-a-trade form says what is wrong under each box", async () => {
  const { tradeProblems } = await import("../src/lib/validate.ts");
  assert.deepEqual(tradeProblems({ d: "2024-01-05", sym: "AAPL", qty: "2", price: "100", fees: "" }), {});
  const bad = tradeProblems({ d: "", sym: " ", qty: "-3", price: "", fees: "-1" });
  assert.equal(bad.d, "Pick the date.");
  assert.equal(bad.sym, "Type the ticker, like AAPL.");
  assert.equal(bad.qty, "Enter more than 0 shares.");
  assert.equal(bad.price, "Enter the price in dollars.");
  assert.match(bad.fees, /^Enter \$0 or more\./);
  assert.equal(tradeProblems({ d: "2024-01-05", sym: "A", qty: "", price: "5", fees: "" }).qty, "Enter the number of shares.");
  const p = read("src/pages/money/UsTaxPage.tsx");
  assert.match(p, /error=\{errs\.sym\}/);
  assert.match(p, /error=\{errs\.qty\}/);
  assert.doesNotMatch(p, /min=\{0\} step="any"/);                                              // the browser's own bubble no longer stops a negative count silently
  assert.match(p, /share\$\{q === 1 \? "" : "s"\}/);                                            // "1 share", not "1 shares"
});

test("LIVE1B-028: the ITR page's answers are tiles, its other figures a list, its schedules one card, its sources a fold", () => {
  const p = read("src/pages/money/ItrExportPage.tsx");
  assert.match(p, /const HEADLINE = \/\^\(Total tax estimate\|Payable now\)\/;/);
  assert.match(p, /<dl className="k-dl figs" aria-label="The year's figures">/);
  assert.match(p, /<ul className="k-fold-rows" aria-label="Schedules with lines">/);
  assert.match(p, /<Disclosure summary="Where the figures come from, and the assumptions">/);
  assert.match(read("src/styles.css"), /\.k-dl\.figs > div \{ flex-direction: row; justify-content: space-between;/);
});

test("LIVE1B-029: dividends left out of the total are said beside it", () => {
  const t = read("src/pages/TaxReportPage.tsx");
  assert.match(t, /dividends_left_out\?: number;/);
  assert.match(t, /<Notice tone="warn" label="Dividends left out"/);
  assert.match(t, /are not counted in this total\.<\/b>/);
});

test("LIVE1B-030: the Tax tools page is titled Tax tools", () => {
  assert.match(read("src/pages/money/TaxToolsPage.tsx"), /<PageHeader eyebrow="Money · Tax" title="Tax tools"/);
});

test("LIVE1B-031, 072: the form for your own dates takes the row; the feed's four buttons are one height", () => {
  const p = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(p, /<Card label="Your own dates">/);
  assert.match(p, /<div className="k-two mc-grid">\n\s*<Card label="Calendar feed">/);
  assert.match(p, /<div className="mc-actions">/);
  assert.match(read("src/styles.css"), /\.mc-actions \{ display: grid; grid-template-columns: repeat\(auto-fit, minmax\(150px, 1fr\)\);/);
});

test("LIVE1B-032, 050: the trade journal is a private page for the question and the trackers; the question's height is kept clear at the page's foot", async () => {
  const ads = await import("../src/lib/ads.ts");
  assert.equal(ads.trackAllowedOn("/trade/journal"), false);
  assert.equal(ads.adsAllowedOn("/trade/journal"), false);
  assert.equal(ads.trackAllowedOn("/trade/positioning"), true);
  assert.match(read("src/components/Tracking.tsx"), /root\.style\.setProperty\("--consent-h", `\$\{el\.offsetHeight \+ 16\}px`\)/);
  const css = read("src/styles.css");
  assert.match(css, /body:not\(:has\(\.shell\)\) \{ padding-bottom: var\(--consent-h, 0px\); \}/);
  assert.match(css, /@media \(max-width: 900px\) \{ \.shell \{ padding-bottom: var\(--consent-h, 0px\); \} \}/);
});

test("LIVE1B-033, 056, 057, 058: the journal's line under the title is one sentence, its choice a compact control, its checks two by two, its curve placed by date", async () => {
  const { JOURNAL_LEDE, JOURNAL_COVERS } = await import("../src/lib/journalTax.ts");
  assert.ok(JOURNAL_LEDE.length < 90 && JOURNAL_COVERS.length > JOURNAL_LEDE.length);
  const p = read("src/pages/trade/JournalPage.tsx");
  assert.match(p, /\{anyTrades && <Seg label="What the file does" options=\{\[\{ value: "add", label: "Add to my trades" \}, \{ value: "replace", label: "Replace imported trades" \}\]\}/);
  assert.doesNotMatch(p, /label="Add to or replace the imported trades"/);
  assert.doesNotMatch(p, /<p className="k-mono k-small">(Yours|Gross)/);
  assert.match(p, /x=\{pts\.map\(\(p\) => Date\.parse\(p\.t\)\)\}/);
  assert.match(read("src/pages/trade/journal.css"), /minmax\(min\(100%, 380px\), 1fr\)/);
});

test("LIVE1B-062: a line below zero gets a tick at or below its lowest point; the area runs to the zero line", () => {
  const x = read("src/components/chart/XYChart.tsx");
  assert.match(x, /if \(ymin < 0 && all\.length && all\[0\] > floor\)/);
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /area: \{ color: "var\(--series-1\)", base: 0 \}/);
});

test("LIVE1B-071: the calendar's link is on the site, forwarded to the server", () => {
  const v = JSON.parse(read("vercel.json"));
  const r = v.rewrites.find((x) => x.source === "/money/calendar/feed/:token");
  assert.equal(r.destination, "https://stratlab-production-ca25.up.railway.app/money/calendar/feed/:token");
  assert.ok(v.rewrites.indexOf(r) < v.rewrites.findIndex((x) => x.destination === "/index.html"), "before the page rewrite that would catch /money/...");
  const p = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(p, /return window\.location\.origin\.replace\(\/\\\/\$\/, ""\) \+ path;/);
  assert.doesNotMatch(p, /CFG\.API_BASE/);
});

test("LIVE1B-019, 037: a Stat in a half-width tile still fits (the duo check counts a shrunk figure as not fitting)", () => {
  assert.match(read("src/components/kit/Stat.tsx"), /\(v\.classList\.contains\("one"\) \? fitFigure\(v\)/);
});
