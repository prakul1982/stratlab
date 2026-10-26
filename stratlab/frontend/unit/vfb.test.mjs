import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import test from "node:test";

// the app's sources import each other without an extension: the loader adds .ts
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");
const invest = read("src/styles-invest.css");

// VFB: the visual review's findings VR1-100 .. VR1-181 (Find stocks, Market view, Company news, Alerts, Money, Account and Plans,
// the signed-out pages and the Library)

test("VR1-147: the US tax tables are phone cards, with a sale's gain right under its name", () => {
  const p = read("src/pages/money/UsTaxPage.tsx");
  for (const l of ["US trades", "US sales in rupees", "US dividends and credit", "Open US lots", "Schedule FA"]) assert.match(p, new RegExp(`<DataTable stack (phonePage=\\{10\\} )?label="${l}"`));
  assert.match(p, /key: "gain", header: "Gain \(₹\)", numeric: true, up: true/);
  assert.match(p, /cardLabel: "Rate used at purchase"/);
  assert.match(read("src/components/kit/DataTable.tsx"), /c\.up && "k-first"/);
  assert.match(css, /\.k-tbl-wrap\.stack\.has-up \.k-table td\.k-first \{ order: -1; \}/);
});

test("VR1-111: eight tiles in five columns are 4 + 4, six in four are 3 + 3, and the old splits are unchanged", async () => {
  const { fillCols } = await import("../src/lib/noOrphan.ts");
  assert.equal(fillCols(8, 5), 4);
  assert.equal(fillCols(6, 4), 3);
  assert.equal(fillCols(8, 3), 3);          // 3 + 3 + 2 is fine
  assert.equal(fillCols(5, 4), 3);          // 4 + 1 becomes 3 + 2, as before
  assert.equal(fillCols(7, 5), 5);          // no even split: left as it is
  assert.equal(fillCols(8, 4), 4);
});

test("VR1-100: a filing's body that opens with its subject keeps only what it adds", async () => {
  const { bodyAfter } = await import("../src/lib/filingText.ts");
  assert.equal(bodyAfter("Disclosure of creation of pledge by promoter", "Disclosure of creation of pledge by promoter. Disclosure under Regulation 31 of creation of pledge."), "Disclosure under Regulation 31 of creation of pledge.");
  assert.equal(bodyAfter("QIP opened", "QIP opened"), "");
  assert.equal(bodyAfter("Qualified Institutions Placement", "QIP opened"), "QIP opened");
  assert.equal(bodyAfter("", "Anything"), "Anything");
  const f = read("src/components/Filings.tsx");
  assert.match(f, /rowsHaveFundRaise/);
  assert.match(read("src/pages/ResearchScans.tsx"), /rowsHaveFundRaise=\{/);
});

test("VR1-101, VR1-103, VR1-104: the scan page says things once; the screener's name column and Save card", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(s, /<p className="k-small k-muted">Pick a scan and a group/);
  assert.doesNotMatch(s, /: "A match says the rule held on the date shown/);
  assert.match(read("src/pages/Screens.tsx"), /className="k-stack screens-main"/);
  assert.match(css, /\.screens-main > \.screens-save \{ order: -1; \}/);
  assert.match(css, /\.screens-table th\[scope="row"\] \{ min-width: 240px; \}/);
  assert.match(invest, /\.inv-bounds \{[^}]*minmax\(0, 1fr\) auto;/);
});

test("VR1-102: the space's main button keeps its place on the page it points to", () => {
  assert.match(read("src/components/Shell.tsx"), /<span className="side-new-gap" aria-hidden="true" \/>/);
  assert.match(css, /\.side-new-gap \{ display: block; height: 34px; \}/);
});

test("VR1-105: a company's past corporate actions sit two across under a short 'Coming up'", () => {
  const c = read("src/components/CorpActions.tsx");
  assert.match(c, /inv-rows\$\{wide \? " inv-rows-cols" : ""\}/);
  assert.match(c, /const wide = past\.length >= 3 && data\.ahead\.length <= 1;/);
  assert.match(invest, /\.inv-rows\.inv-rows-cols \{ display: grid;/);
});

test("VR1-110, VR1-112, VR1-113: a chart's Table button stays beside a long title; the alert and the rotation controls are one row", () => {
  assert.match(read("src/components/kit/ChartFrame.tsx"), /className=\{rangeBar \|\| actions \? undefined : "k-chart-plain"\}/);
  assert.match(css, /\.k-chart-plain > \.k-card-head \{ flex-wrap: nowrap;/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<FormGrid label="New breadth alert" onSubmit=\{add\} inline>/);
  assert.match(read("src/pages/ResearchScans.tsx"), /<FormGrid label="What to show" inline>/);
  assert.match(read("src/components/kit/Form.tsx"), /k-form-inline/);
  assert.match(css, /\.k-form\.k-form-inline \{ display: flex; flex-wrap: wrap; align-items: flex-end;/);
});

test("VR1-114: a right-aligned header's (i) has its gap on the side facing the words", () => {
  assert.match(css, /\.k-table th\.k-num > \.info \{ margin-left: 0; margin-right: 6px; \}/);
});

test("VR1-115, VR1-116: no caption under a dash; page intros are one line with the rest behind the (i)", () => {
  assert.match(read("src/pages/StockLendingPage.tsx"), /r\.summaries\[0\]\.ann_low != null \?/);
  const etf = read("src/pages/EtfGapsPage.tsx");
  assert.match(etf, /lede="How far each ETF's close is from what one unit holds: that day's published NAV, as a percent above or below\. Facts with their dates, not a view on any fund\."/);
  assert.match(etf, /Each row shows two prices: the last trade, and the official close the gap uses/);
  assert.match(read("src/pages/MarginFundingPage.tsx"), /lede="How much of the market is bought with money brokers lend under the margin trading facility \(MTF\), and what your own position costs\."/);
  assert.match(read("src/pages/IposPage.tsx"), /lede="India's and the US's public offerings in their stages, from the exchanges' and regulators' own pages\. Facts, not advice\."/);
});

test("VR1-120: an unchecked box has an edge in the muted text colour", () => {
  assert.match(css, /\.k-check input\[type="checkbox"\]:not\(:checked\), \.k-tap input\[type="checkbox"\]:not\(:checked\) \{[^}]*border: 1\.5px solid var\(--muted\);/);
});

test("VR1-121, VR1-122, VR1-123, VR1-124, VR1-125: IPO badge, fold width, the issue's columns, one full stop, the two weeks side by side", async () => {
  const ipo = await import("../src/lib/ipoText.ts");
  assert.equal(ipo.badgeOf({ stage: "social" }).word, "Fund raise");
  assert.match(css, /\.k-disclosure-body:has\(> \.k-tbl-wrap\) \{ padding-left: 0; \}/);
  const p = read("src/pages/IpoPage.tsx");
  assert.match(p, /className="ipo-terms"/);
  assert.doesNotMatch(p, /Offer for sale \(shares existing holders offer\)/);
  assert.match(p, /r\.hours\.replace\(\/\\\.\+\$\/, ""\)/);
  assert.match(read("src/pages/ipo.css"), /\.ipo-terms \.k-stats, \.ipo-terms \.ipo-facts, \.ipo-terms \.ipo-dates \{ grid-template-columns: repeat\(auto-fill/);
  assert.match(read("src/pages/ResultsPage.tsx"), /<div className="k-cols">\{data\.weeks\.map/);
});

test("VR1-130: the alerts summary is one sentence row with the settings link in it", () => {
  const a = read("src/pages/AlertsPage.tsx");
  assert.match(a, /data-testid="alerts-summary"/);
  assert.match(a, /: "This page only"\}/);
  assert.equal((a.match(/Where alerts go and what to send/g) ?? []).length, 1);
});

test("VR1-140, VR1-149, VR1-150, VR1-151: Money home's figures and tiles, label baselines, a disabled main button, the rates table", () => {
  assert.match(read("src/pages/SpaceHomes.tsx"), /grid2 space-panels money-panels/);
  assert.match(css, /\.money-panels \.k-stats \{ grid-template-columns: repeat\(auto-fit, minmax\(112px, 1fr\)\);/);
  assert.match(css, /\.explore-grid\.money-cards \{ grid-template-columns: repeat\(auto-fit, minmax\(min\(100%, 215px\), 1fr\)\); \}/);
  assert.match(css, /\.k-stat-k \.info \{ margin-block: -4px; \}/);
  assert.match(css, /\.btn:disabled:not\(\.quiet\):not\(\.blue\):not\(\.outline\) \{ opacity: 1; background: transparent; border: 1px dashed var\(--dash\);/);
  assert.match(read("src/pages/money/RatesPage.tsx"), /className="k-page rates-page"/);
  assert.match(css, /\.rates-page \.k-table th\.k-wrap\[scope="row"\] \{ min-width: 260px; \}/);
});

test("VR1-141, VR1-142, VR1-143: Net worth has one quick-add strip, a plain History fold and one 'as of' for the assets", () => {
  const n = read("src/pages/money/NetWorthPage.tsx");
  assert.match(n, /<Card compact label="Add to your net worth">/);
  assert.doesNotMatch(n, /<CardHead title="Add to your net worth" \/>/);
  assert.match(n, /History: \{hist\.length\} snapshot/);
  assert.doesNotMatch(n, /<summary className="k-small">The history's snapshots/);
  assert.match(n, /aria-label=\{`Remove the snapshot of \$\{dateOnly\(h\.d\)\}`\}/);
  assert.match(n, /!oneDay && <span className="k-sub-line">as of/);
  assert.match(n, /All as of \{day\(view\.assets\[0\]\.as_of\)\}/);
});

test("VR1-144, VR1-145, VR1-146, VR1-148: tax report, dividends and US tax controls", () => {
  const t = read("src/pages/TaxReportPage.tsx");
  assert.doesNotMatch(t, /<b className="k-big" aria-label="Estimated total tax">/);
  assert.match(css, /\.k-card\.compact > \.k-card-head:has\(> \.k-card-actions\) \{ flex: 1 1 100%; \}/);
  const d = read("src/pages/money/TaxToolsPage.tsx");
  assert.match(d, /\{!y && \(\s*<Card compact=/);
  assert.match(d, /info=\{DIVIDEND_INFO\} infoLabel="About your dividends" actions=\{<>[\s\S]*\{uploadBtn\}/);
  const u = read("src/pages/money/UsTaxPage.tsx");
  assert.doesNotMatch(u, /<FormGrid label="Choose the year">/);
  assert.match(u, /<CardHead title="Financial year" actions=\{<Select small label="Financial year"/);
  assert.match(u, /btn quiet sm k-btn-end" onClick=\{\(\) => setAsking\(true\)\}><Trash size=\{16\} \/>Delete all US trades/);
});

test("VR1-160, VR1-161, VR1-162, VR1-163: Account, Settings and Plans", () => {
  assert.match(css, /\.k-page-head:not\(:has\(> \.k-eyebrow\)\) \{ padding-top: 26px; \}/);
  assert.match(css, /\.k-rows\.two \{ display: grid; grid-template-columns: repeat\(2, minmax\(0, 1fr\)\);/);
  assert.match(read("src/pages/AccountPage.tsx"), /k-rows\$\{usage\.length > 6 \? " two" : ""\}/);
  assert.match(css, /\.lp-amount-row \{ display: flex; flex-direction: column; align-items: flex-start;/);
  const c = read("src/components/PlanCompare.tsx");
  assert.match(c, /const valueOf = /);
  assert.match(c, /cell: \(r\) => nameOf\(r\.label\)/);
});

test("VR1-170: /help starts at the questions, with the page's one h1 on its own heading", () => {
  const l = read("src/pages/Login.tsx");
  assert.match(l, /const helpOnly = !plansOnly && slim === "faq" && heading === "Help";/);
  assert.match(l, /\{!helpOnly && <section id="top" className="lp-hero ruled">/);
  assert.match(l, /<Head eyebrow="Questions and contact" title="Help" h1>/);
});

test("VR1-171, VR1-173, VR1-180, VR1-181: the library's width, count line, level titles and wrapped market chips; one admin row height", () => {
  assert.match(css, /\.pub:has\(\.lib-cards\) \.pub-main \{ max-width: 1144px; \}/);
  const p = read("src/pages/PublicLibrary.tsx");
  assert.match(p, /shown\.length !== rows\.length &&/);
  assert.match(p, /<ChipBar label="Market" options=\{markets\} value=\{market\} onChange=\{setMarket\} wrap \/>/);
  assert.match(read("src/pages/LibraryPage.tsx"), /<ChipBar label="Market" options=\{choices\} value=\{market\} onChange=\{setMarket\} wrap \/>/);
  assert.match(read("src/pages/trade/trade.css"), /\.lib-card \.lib-head > \.k-card-head \{ margin-top: auto; \}/);
  assert.match(read("src/pages/admin/admin.css"), /\.adm-plan \{ align-items: flex-start; gap: 2px; min-height: 48px; \}/);
});
