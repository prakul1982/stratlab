// LIVE9B (16 Nov 2026 live review, reviewer B): the frontend side of lane fix9b.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE9B-001: a company page's wait holds the header's final shape (name, the exchange line, both date chips)", () => {
  const src = read("src/pages/Research.tsx");
  const wait = src.slice(src.indexOf("if (!c) return ("), src.indexOf("const ccy = c.currency"));
  assert.match(wait, /title=\{knownName\(region, sym\) \?\? sym\}/);          // the name this device last saw, not the bare symbol
  assert.match(wait, /lede=\{<span className="k-meta-wait">/);                // the "NSE · TCS" line's place
  assert.equal((wait.match(/className="k-meta-wait" aria-hidden="true"><Badge>/g) || []).length, 2);   // both chips' places
  assert.match(wait, /onRetry=\{\(\) => setTries\(\(n\) => n \+ 1\)\} page \/>/);   // the footer waits below the fold
});

test("LIVE9B-003: a whole-number percentage row or column is written whole, never with a fake '.0'", async () => {
  const { cellText, wholeOnly } = await import("../src/lib/companyTables.ts");
  assert.equal(wholeOnly([25, 26, null, 24]), true);
  assert.equal(wholeOnly([4.6, 7, null]), false);
  assert.equal(cellText(25, "pct", "IN", true), "25%");
  assert.equal(cellText(4.6, "pct", "IN"), "4.6%");
  assert.match(read("src/components/CompanyStatements.tsx"), /cellText\(r\.values\[i\], r\.kind, region, r\.kind === "pct" && wholeOnly\(r\.values\)\)/);
  assert.match(read("src/components/CompanyPeers.tsx"), /pctCell\(r\.ebitda, "ebitda"\)/);
});

test("LIVE9B-007: business updates in one unit per kind, old figures aged, filing years, no tag on every row", async () => {
  const { bizValueOne, monthsBefore } = await import("../src/lib/biz.ts");
  assert.equal(bizValueOne(45520, "₹ million"), "₹4,552 crore");
  assert.equal(bizValueOne(3085, "₹ mn"), "₹309 crore");
  assert.equal(bizValueOne(6.51, "₹ lakh crore"), "₹6,51,000 crore");
  assert.equal(bizValueOne(5542, "₹ crore"), "₹5,542 crore");
  assert.equal(bizValueOne(104.3, "Lac MT"), "104.3 lakh tonnes");
  assert.equal(bizValueOne(19.9, "Mn T"), "19.9 million tonnes");
  assert.equal(bizValueOne(3519, "units"), "3,519 units");
  assert.equal(monthsBefore("2025-03", new Date(2026, 10, 17)), 20);
  const page = read("src/pages/BizUpdatesPage.tsx");
  assert.match(page, /months old/);
  assert.match(page, /new Set\(mine\.rows\.map\(\(r\) => r\.kind\)\)\.size > 1 \?/);       // the From column only when holdings and watchlist mix
  assert.doesNotMatch(page, /<Badge tone="plain" dot=\{false\}>\{kindName/);
  assert.match(read("src/components/BizUpdates.tsx"), /thisYear \? \{ year: false \} : \{\}/);
});

test("LIVE9B-008: the money calendar links the filing instead of writing its address, and tags rows only when kinds mix", () => {
  const src = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(src, /<a className="link" href=\{safeHref\(e\.link\)\} target="_blank" rel="noopener noreferrer">Filing ↗<\/a>/);
  assert.match(src, /const tag = new Set\(events\.map\(\(e\) => e\.cat\)\)\.size > 1;/);
  assert.match(src, /\{tag && <span className=\{`badge mc-cat/);
  assert.match(read("src/styles.css"), /\.mc-ev\.untagged \{ grid-template-columns: minmax\(0, 1fr\); \}/);
});

test("LIVE9B-011: the Trade home's journal card is as short as its neighbours (no four-line caveat, no dangling dot)", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.doesNotMatch(src, /F&O lines in your tax report are kept there as totals, not counted here/);
  assert.doesNotMatch(src, /closed trade"\)\} · /);
});

test("LIVE9B-012: owner patterns: centred sign-in, net worth said once, even home cards, compact holdings totals, sparse bases as notes, screens CSV in the header", () => {
  assert.match(read("src/pages/Login.tsx"), /\$\{login \? " lp-hero-login" : ""\}/);
  const css = read("src/styles.css");
  assert.match(css, /\.lp-hero-login \{ max-width: 640px; \}/);
  assert.match(css, /\.mine-movers li, \.mine-tl-i \{ flex: 1 0 auto; \}/);
  assert.match(css, /@media \(min-width: 900px\) \{ \.h-sum \{ grid-template-columns: minmax\(0, 560px\) minmax\(0, 1fr\); \} \}/);
  assert.match(css, /\.screens-fname \{ display: block; font-size: 14px; \}/);
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.doesNotMatch(nw, /\{ id: "net", k: <b>Net worth<\/b>/);
  assert.match(read("src/pages/HoldingsPage.tsx"), /<div className="h-sum">\n\s*<FigureTable label="Where your stocks stand"/);
  const r = read("src/components/Research.tsx");
  assert.match(r, /const LONG_NOTE = 60;/);
  assert.match(r, /m\.note && \(m\.note\.length > LONG_NOTE \|\| sparse\(g\)\)/);
  const sc = read("src/pages/Screens.tsx");
  assert.match(sc, /<CsvButton name="screen results" label="Companies that match"/);
  assert.doesNotMatch(sc, /<DataTable csv="screen results"/);
});

test("LIVE9B-013: late answers hold their place: plan notes' price line, the corporate actions header and alerts line, the deep dive's tools, the forward test's lock", () => {
  const note = read("src/components/kit/Notice.tsx");
  assert.match(note, /const waiting = !!\(plan \?\? named\) && price === null && canBuy\(me\?\.offer\);/);
  assert.match(note, /\{waiting && <span className="k-meta-wait" aria-hidden="true" data-price-wait>/);
  const ca = read("src/pages/CorpActionsPage.tsx");
  assert.match(ca, /asOfPending=\{!data && !error\}/);
  assert.match(ca, /\{!data && !error && <span className="k-meta-wait" aria-hidden="true"><CheckField/);
  const dd = read("src/pages/DeepDive.tsx");
  assert.match(dd, /asOfPending=\{!v\}/);
  assert.match(dd, /className="k-row dd-tools"/);
  assert.match(read("src/styles.css"), /\.dd-tools \{ min-height: 32px; \}/);
  const sg = read("src/pages/trade/SignalsPage.tsx");
  assert.match(sg, /const lockedNow = me\?\.plan_info\.features\?\.signal_webhooks === false;/);
  assert.match(sg, /: lockedNow \|\| !ov\?\.allowed \? \(/);
});

test("LIVE9B-014: the Trade home's VIX tile has its change in colour with ▲/▼ and its day", () => {
  const src = read("src/pages/SpaceHomes.tsx");
  assert.match(src, /<span className=\{signCls\(vq\.change\)\}>\{vq\.change > 0 \? "▲ " : vq\.change < 0 \? "▼ " : ""\}\{vixChange\(vq\)\}<\/span>\{vixDay \? ` · \$\{vixDay\}` : ""\}/);
});

test("LIVE9B-015: a period grid's column half under the sticky row names fades beside them", () => {
  assert.match(read("src/styles.css"), /data-scrolled\]:not\(\.stack\) \.k-table tbody th\[scope="row"\]:first-child::after,[\s\S]{0,240}right: -28px; width: 28px; pointer-events: none;/);
});
test("LIVE9B-015: the grid marks itself scrolled", () => {
  assert.match(read("src/components/kit/DataTable.tsx"), /onScroll=\{scrollEnd \? \(e\) => markScrolled\(e\.currentTarget\) : undefined\}/);
});

test("LIVE9B-018: the Act's renumbering said once, and the year's sections named one way", () => {
  const src = read("src/pages/TaxReportPage.tsx");
  assert.match(src, /!\/not yet confirmed\/\.test\(n\) && !\/Income-tax Act, 2025\/\.test\(n\)/);
  assert.match(src, /export function actSections\(text: string, map: Record<string, string> \| null \| undefined\): string/);
  assert.match(src, /\{actSections\(l\.label, t\.sections\)\}/);
  // the helper's rule, run here on its own text
  const body = src.slice(src.indexOf("export function actSections"), src.indexOf("/** The year's total tax"));
  const fn = new Function("text", "map", body.replace(/^export function actSections\([^)]*\): string \{/, "").replace(/\}\s*$/, ""));
  assert.equal(fn("at the special rates (sections 111A, 112A and 112)", { "111A": "196", "112A": "198" }), "at the special rates (sections 196 (111A before), 198 (112A before) and 112)");
  assert.equal(fn("Tax on intraday", { "111A": "196" }), "Tax on intraday");
  assert.equal(fn("section 111A", null), "section 111A");
});

test("LIVE9B-019: a T-bill cut-off is the last weekly auction's, read on a day, not 'as on' the read day", () => {
  assert.match(read("src/pages/money/RatesPage.tsx"), /r\.key\.startsWith\("tbill"\) \? `cut-off at the last weekly auction, read \$\{dateOnly\(r\.as_of\)\}`/);
});

test("LIVE9B-020: net worth shares rounded on their own, the snapshots link on the chart's line, the share beside its bar", () => {
  const n = read("src/pages/money/NetWorthPage.tsx");
  assert.match(n, /pct: view\.totals\.assets > 0 \? \(a\.value \/ view\.totals\.assets\) \* 100 : a\.pct/);
  assert.match(n, /footer=\{<div className="nw-hist-foot">/);
  assert.doesNotMatch(n, /History: \{hist\.length\}/);
  assert.match(read("src/styles.css"), /\.dd-share \{ display: flex; flex-direction: row-reverse;/);
});

test("LIVE9B-021: holdings say when they were imported, and that they are old after a week", async () => {
  const { daysOld, HOLDINGS_OLD_DAYS } = await import("../src/lib/format.ts");
  assert.equal(daysOld("2026-10-25T10:00:00Z", new Date("2026-11-17T10:00:00Z")), 23);
  assert.equal(daysOld(null), null);
  assert.equal(HOLDINGS_OLD_DAYS, 7);
  const h = read("src/pages/HoldingsPage.tsx");
  assert.match(h, /` · imported from \$\{sourceWords\(view\.source\)\}`/);
  assert.match(h, /data-testid="holdings-old">These holdings are \{daysOld\(view\.updated_at\)\} days old/);
  assert.match(read("src/pages/SettingsPage.tsx"), /`Imported from \$\{sourceWords\(h\.source\)\}/);
});

test("LIVE9B-022: a leg to fix reads 'Buy CE (distance to fix)', and the market's hours are said once", async () => {
  const { legWords, timingIssues } = await import("../src/lib/options.ts");
  assert.equal(legWords({ side: "buy", opt: "CE", offset: 5000, lots: 1 }, "strikes"), "CE (distance to fix)");
  assert.equal(legWords({ side: "buy", opt: "CE", offset: 2, lots: 1 }, "strikes"), "2 strikes OTM CE");
  const bad = timingIssues({ entry: "16:00", lastEntry: "16:10", squareoff: "16:20" }, "09:15", "15:40");
  assert.equal(bad.filter((x) => x.includes("the market's hours are")).length, 1);
  assert.match(read("src/pages/OptionsPage.tsx"), /\$\{legWords\(l, s\.offsetUnit\)\}/);
});

test("LIVE9B-023, 024: dividends totals right-aligned with every row's payments; the journal's missing side said once, days grouped", () => {
  const ha = read("src/components/HoldingsActions.tsx");
  assert.match(ha, /noteHead="Payments" numeric rows=\{\[/);
  assert.match(ha, /v: inr\(data\.ahead_total\), n: `\$\{data\.ahead\.length\} payment/);
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /\$\{t\.hold_days\.toLocaleString\("en-IN"\)\} day/);
  assert.match(j, /data-testid="j-no-side"/);
});

test("LIVE9B-026: the upsell card quotes Basic's numbers in good grammar, and /alerts says what the Free change does to alerts", async () => {
  const H = await import("../src/lib/houseAds.ts");
  const plans = H.HOUSE.find((c) => c.id === "plans");
  assert.doesNotMatch(plans.text, /1 company deep dives/);
  assert.match(plans.text, /^Basic includes \d+ AI strategy builds and \d+ company deep dives? a month/);
  const a = read("src/pages/AlertsPage.tsx");
  assert.match(a, /data-testid="alerts-grace">From \{changeDay\(fc\.on\)\} your Free plan has \{row\.after\} alerts on at a time/);
});

test("LIVE9B-027: My space's net worth keeps its two decimals; the company header's actions are two rows of three on a phone", async () => {
  const { inrCompactSteady } = await import("../src/lib/format.ts");
  assert.equal(inrCompactSteady(-830000), "−₹8.30 lakh");
  assert.equal(inrCompactSteady(-829000), "−₹8.29 lakh");
  assert.equal(inrCompactSteady(800000), "₹8.00 lakh");
  assert.equal(inrCompactSteady(1850000), "₹18.5 lakh");
  assert.equal(inrCompactSteady(925), "₹925");
  assert.match(read("src/pages/MineHome.tsx"), /value=\{inrCompactSteady\(v\.totals\.net\)\}/);
  assert.match(read("src/styles-invest.css"), /\.inv-actions \{ display: grid; grid-template-columns: repeat\(3, minmax\(0, 1fr\)\); gap: var\(--s2\); \}/);
});

test("LIVE9B-028, 029: the plan named once on Account; a visitor's /tour shows how StratLab works; Feedback in its neighbours' colour", async () => {
  assert.doesNotMatch(read("src/pages/AccountPage.tsx"), /<div><dt>Plan<\/dt><dd>\{planName\}<\/dd><\/div>/);
  const { visitorView } = await import("../src/lib/deepLinks.ts");
  assert.deepEqual(visitorView("/tour"), { kind: "landing", section: "about", panel: undefined });
  assert.match(read("src/lib/title.ts"), /if \(p === "\/tour"\) return withBrand\("How StratLab works"\);/);
  assert.match(read("src/styles.css"), /\.legal-links \.legal-feedback \{ color: var\(--muted\); \}/);
});

test("LIVE9B-030, 031: a fold card's count is in its button's name, not hidden text; My space's gold line waits for India's price", () => {
  const f = read("src/components/kit/FoldCard.tsx");
  assert.match(f, /aria-label=\{said \? `\$\{title\}, \$\{said\}` : undefined\}/);
  assert.doesNotMatch(f, /<span className="sr-only">, \{said\}<\/span>/);
  const m = read("src/pages/MineHome.tsx");
  assert.match(m, /useState<IndiaGold \| null \| undefined>\(undefined\)/);
  assert.match(m, /series\.gold && gold !== undefined \? goldLineParts/);
});

test("LIVE9B-033: an industry's name inside a sentence keeps its acronyms", async () => {
  const { lowerKeepAcronyms } = await import("../src/lib/format.ts");
  assert.equal(lowerKeepAcronyms("IT services"), "IT services");
  assert.equal(lowerKeepAcronyms("Banks and NBFCs"), "banks and NBFCs");
  assert.equal(lowerKeepAcronyms("Auto Components"), "auto components");
  assert.match(read("src/pages/DeepDive.tsx"), /the \$\{lowerKeepAcronyms\(v\.industry_measures\.label\)\} measures/);
});
