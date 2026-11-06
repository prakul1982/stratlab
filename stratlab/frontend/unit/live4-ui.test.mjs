// LIVE4 (final live review, 6 Nov 2026): the presentation fixes (lane r13-ui). Each test names its finding.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// a source file's own imports name no extension ("./api"): try ".ts" (as unit/live1.test.mjs does)
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const css = read("src/styles.css");
const invCss = read("src/styles-invest.css");

test("LIVE4-010: DataTable's compact phone rows: two short lines, brief figures at the right, columns left off, lone dashes dropped", () => {
  const t = read("src/components/kit/DataTable.tsx");
  assert.match(t, /brief\?: boolean;/);
  assert.match(t, /phone\?: false;/);
  assert.match(t, /compact\?: boolean;/);
  assert.match(t, /\$\{stack && compact \? " compact" : ""\}/);
  assert.match(t, /c\.brief && "k-brief", c\.phone === false && "k-phone-off"/);
  // a lone dash is "no figure": left off a compact phone row, but a cell still loading (no text of its own) is kept
  assert.match(t, /export const dashOnly = \(text: string\): boolean => \/\^\\s\*\[–—-\]\\s\*\$\/\.test\(text\);/);
  assert.match(t, /\(cardsNow && !!compact && !c\.rowHeader && dashOnly\(cellText\(v\)\)\)/);
  const dashOnly = (text) => /^\s*[–—-]\s*$/.test(text);
  assert.equal(dashOnly("–"), true);
  assert.equal(dashOnly(" - "), true);
  assert.equal(dashOnly(""), false);
  assert.equal(dashOnly("−1.2%"), false);
  // the CSS: a flex row with a zero-height break after the name and the brief figures; no card boxes
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table tr \{ display: flex; flex-wrap: wrap;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table tr::before \{ content: ""; order: -1; flex-basis: 100%; height: 0; \}/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table th\[scope="row"\] \{ order: -3;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table td\.k-brief \{ order: -2;/);
  assert.match(css, /\.k-tbl-wrap\.stack\.compact \.k-table td\.k-phone-off \{ display: none; \}/);
  // the brief figures carry no label: their rule comes after the one that shows labels
  assert.ok(css.indexOf("td.k-brief::before { display: none; }") > css.indexOf(".k-tbl-wrap.stack.compact .k-table td[data-label]::before"));
});

test("LIVE4-010: a link in a table cell never shrinks under its own words (COROMANDEL ran under its F&O tag)", () => {
  assert.match(css, /\.k-table td a, \.k-table th a \{ min-width: 32px; flex-shrink: 0; \}/);
});

test("LIVE4-010: the results calendar is compact on a phone and its headers fit one line on a desktop", () => {
  const page = read("src/pages/ResultsPage.tsx");
  assert.match(page, /columns=\{columns\} stack compact phonePage=\{10\}/);
  assert.match(page, /key: "px", header: "Price", numeric: true, brief: true/);
  assert.match(page, /key: "day", header: "Day", numeric: true, brief: true/);
  for (const k of ["cap", "rev", "pat"]) assert.match(page, new RegExp(`key: "${k}", [^\\n]*phone: false`), k);
  assert.match(invCss, /\.inv-day \.k-table thead th \{ white-space: nowrap; \}/);
  assert.match(invCss, /\.k-tbl-wrap\.compact \.res-moves, \.k-tbl-wrap\.compact \.res-plain, \.k-tbl-wrap\.compact \.res-name \{ display: none; \}/);
  // the day's CSV button shares the day's heading line; on a phone it says "CSV"
  assert.match(invCss, /\.inv-day > \.k-eyebrow \+ \.k-tbl-tools \{ grid-column: 2;/);
  assert.match(read("src/components/kit/DataTable.tsx"), /<span className="k-csv-verb">Download <\/span>CSV/);
  assert.match(css, /@media \(max-width: 640px\) \{ \.k-csv-verb \{ display: none; \} \}/);
});

test("LIVE4-014: ICICI Direct and Motilal Oswal follow their own help pages; HDFC and Other say what to look for", async () => {
  const G = await import("../src/lib/brokerGuide.ts");
  const icici = G.guideFor("icici");
  assert.equal(icici.file.help, "https://www.icicidirect.com/faqs/stocks/how-can-i-download-a-summary-of-my-portfolio-on-website");
  assert.match(icici.file.steps.join(" "), /open Stocks\. Open Portfolio\. Press the Download icon and choose the file format/);
  const mo = G.guideFor("motilal");
  assert.equal(mo.file.read, "pdf");
  assert.match(mo.file.steps[0], /Portfolio tab downloads your holdings statement as a PDF, which can't be read here/);
  assert.match(mo.file.help, /^https:\/\/www\.motilaloswal\.com\//);
  for (const id of ["hdfc", "other"]) {
    assert.match(G.guideFor(id).file.steps[0], /look for Holdings \(or Portfolio\), then Download \/ Export\./, id);
    assert.equal(G.guideFor(id).file.help, undefined, id);          // no page of the broker's own to link
  }
  // no broker is left with the old generic "Open your holdings (or portfolio)" steps
  for (const b of G.GUIDE_BROKERS) assert.doesNotMatch(b.file.steps.join(" "), /Open your holdings \(or portfolio\)/, b.id);
});

test("LIVE4-015: the upload step says where the button is; Angel One's row says it has no live connection; notes match the rows", async () => {
  const G = await import("../src/lib/brokerGuide.ts");
  for (const b of G.GUIDE_BROKERS) assert.doesNotMatch(b.file.steps.join(" "), /upload the file here/i, b.id);
  assert.equal(G.uploadStep(G.guideFor("zerodha"), "holdings"), "Press Upload holdings file and pick the file.");
  assert.equal(G.uploadStep(G.guideFor("zerodha"), "settings"), "Press Upload in My Holdings and pick the file there.");
  assert.equal(G.uploadStep(G.guideFor("paytm"), "settings"), null);
  assert.equal(G.guideFor("angelone").connect, "none");
  assert.deepEqual(G.waysFor(G.guideFor("angelone")), ["connect", "file", "email"]);
  assert.match(G.EMAIL_STEPS[0], /each month you trade, every six months otherwise/);
  const guide = read("src/components/BrokerGuide.tsx");
  assert.match(guide, /No live connection yet: upload the holdings file or email the statement\./);
  assert.match(guide, /\[\.\.\.b\.file\.steps, uploadStep\(b, where\)\]/);
  assert.match(guide, /where === "settings" \? "Set up your private address with Set up my inbox/);
  // the Brokers note counts only rows marked "Not open yet", not the ones not set up on the site
  assert.match(read("src/components/ConnectedAccounts.tsx"), /const closed = rows\.filter\(\(b\) => b\.configured !== false && !b\.available\);/);
});

test("LIVE4-006: a group phrase is not a company in the headlines table; the main story moves under its headlines when few carry it", async () => {
  const P = await import("../src/lib/pulseMood.ts");
  assert.equal(P.groupPhrase("Indian IT stocks"), true);
  assert.equal(P.groupPhrase("PSU banks"), true);
  assert.equal(P.groupPhrase("Metal shares"), true);
  assert.equal(P.groupPhrase("Infosys"), false);
  assert.equal(P.groupPhrase("HDFC Bank"), false);
  assert.equal(P.groupPhrase("Bajaj Finance"), false);
  assert.deepEqual(P.companyRows([{ name: "Indian IT stocks", ticker: "INFY" }, { name: "Infosys", ticker: "INFY" }]).map((r) => r.name), ["Infosys"]);
  const mood = read("src/pages/PulseMood.tsx");
  assert.match(mood, /rows=\{companyRows\(ai\.hot\)\}/);
  assert.match(mood, /const under = !!story && sparseNotes\(marked, sorted\.length\);/);
  assert.match(mood, /\.\.\.\(story && !under \? \[\{ key: "s", header: "Main story"/);
  assert.match(read("src/pages/Research.tsx"), /<FlowsTable f=\{mood\.flows\} source=\{ai\?\.flows_source\} \/>/);
});

test("LIVE4-005 / 007: the live count's time in its header; the read time with its zone; a closed session's columns are its day", async () => {
  const P = await import("../src/lib/pulseMood.ts");
  assert.equal(P.sessionHeader(null, (d) => d), "Today");
  assert.equal(P.sessionHeader("2026-11-05", () => "5 Nov"), "5 Nov");
  const mood = read("src/pages/PulseMood.tsx");
  assert.match(mood, /header: b\.live \? \(b\.at \? `Today, \$\{b\.at\}` : "Today"\) : day\(b\.day\)/);
  assert.match(mood, /Read \{fmtTime\(m\.read_at, \{ tz: marketTz\(region\), zone: true \}\)\}/);
  assert.doesNotMatch(mood, /toLocaleTimeString\(region/);
  assert.match(mood, /key: "d", header: sessionHeader\(closedDay, day\)/);
  assert.match(mood, /header: closedDay \? `Move on \$\{day\(closedDay\)\}` : "Move today"/);
  assert.match(mood, /title=\{ai \? "No newer headlines yet" : "No headlines yet today"\}/);
});

test("LIVE4-008: the breadth card is a table of two days, each column headed with its day; no figure under another day's header", async () => {
  const { cardTable } = await import("../src/lib/breadth.ts");
  const fig = (value, prev) => ({ value, prev, change: null });
  const today = { day: "2026-11-05", prev_day: "2026-11-04", adv: fig(359, 300), dec: fig(138, 200), pct50: fig(46.4, 44.0), highs: fig(24, 20), lows: fig(3, 5) };
  const live = { state: "live", day: "2026-11-06", as_of: "12:30", latest: { adv: 123, dec: 376, pct50: 41.0 } };
  const t = cardTable({ today, live });
  assert.equal(t.nowHead, "Today, 6 Nov");
  assert.equal(t.beforeHead, "Close of 5 Nov");
  assert.deepEqual(t.rows.map((r) => [r.id, r.now, r.before]), [["adv", "123 / 376", "359 / 138"], ["pct50", "41.0%", "46.4%"], ["hl", null, "24 / 3"]]);
  // after the close, before the live count: the last close against the one before it
  const shut = cardTable({ today, live: null });
  assert.equal(shut.nowHead, "Close of 5 Nov");
  assert.equal(shut.beforeHead, "Close of 4 Nov");
  assert.deepEqual(shut.rows.map((r) => r.before), ["300 / 200", "44.0%", "20 / 5"]);
  const card = read("src/components/BreadthCard.tsx");
  assert.match(card, /r\.now \?\? <span className="k-muted">At the close<\/span>/);
  assert.doesNotMatch(card, /FactTable/);
  // Invest home's results: the day's whole count, no "and N more" tail, the whole day linked in the header
  const homes = read("src/pages/SpaceHomes.tsx");
  assert.doesNotMatch(homes, /more on the calendar/);
  assert.match(homes, /\{more \? `All \$\{rows!\.total\.toLocaleString\("en-IN"\)\} →` : "Calendar →"\}/);
  assert.match(homes, /setRows\(\{ today, total: Math\.max\(counted, today\.length\), next \}\)/);
  // the consent question is a slim bar along the foot of the page column in the app too, and the page's foot clears it
  assert.match(css, /body:has\(\.shell\) \.consent \{ left: calc\(248px \+ 16px\); right: 16px; width: auto; flex-direction: row;/);
  assert.match(css, /\.shell \{ padding-bottom: var\(--consent-h, 0px\); \}\n\}/);
});

test("LIVE4-009: Market Watch says when its prices are from, and draws no arrow on 0.00%", async () => {
  const W = await import("../src/lib/watch.ts");
  assert.equal(W.changeArrow(0.004), "");
  assert.equal(W.changeArrow(-0.004), "");
  assert.equal(W.changeArrow(0.05), "▲ ");
  assert.equal(W.changeArrow(-1.2), "▼ ");
  assert.equal(W.changeArrow(null), "");
  assert.equal(W.asOfLine([]), null);
  assert.equal(W.asOfLine([null, "2026-11-06T07:25:04Z", Date.parse("2026-11-06T07:25:09Z")]), "Prices as of 12:55:09 IST");
  for (const f of ["src/components/watch/WatchRow.tsx", "src/components/watch/PublicBoard.tsx", "src/components/watch/WatchPanel.tsx"]) {
    assert.match(read(f), /changeArrow\(/, f);
    assert.doesNotMatch(read(f), /> 0 \? "▲ "/, f);
  }
  assert.match(read("src/components/watch/WatchPanel.tsx"), /\{list && asOf && <span data-testid="mw-as-of"> · \{asOf\}<\/span>\}/);
});

test("LIVE4-011: sector rotation says once that an index has no stocks list, and its names are left-aligned", () => {
  const s = read("src/pages/ResearchScans.tsx");
  assert.doesNotMatch(s, />No stocks list</);
  assert.match(s, /data-testid="rot-no-stocks"/);
  assert.match(css, /\.rot-name button\.link \{ text-align: left; \}/);
  // where it was a trail ago is under its quadrant, not a column of its own
  assert.doesNotMatch(s, /ago → now`/);
  assert.match(s, /data-testid="rot-was">\{r\.moved === r\.quadrant \? `Same as \$\{ago\}` : <>From /);
});

test("LIVE4-012: a page's (i) ends its lede when there is no as-of badge, never in front of its buttons; Net worth has one Add an entry", () => {
  assert.match(read("src/components/kit/PageHeader.tsx"), /const inline = !!info && !!lede && !when && !asOfPending;/);
  const nw = read("src/pages/money/NetWorthPage.tsx");
  assert.match(nw, /<EmptyState title="Nothing added yet">/);
  assert.equal((nw.match(/Add an entry<\/button>/g) ?? []).length, 1);
});

test("LIVE4-013: the usual-range note says which spans are the industry's; an India bank gets the bank spans", () => {
  const r = read("src/components/Research.tsx");
  assert.doesNotMatch(r, /adjusted for the company's industry where it differs/);
  assert.match(r, /it is the same span for every industry/);
  assert.match(read("src/pages/Research.tsx"), /industry=\{c\.industry \?\? \(c\.bank \? "bank" : null\)\}/);
  assert.doesNotMatch(read("src/lib/help.ts"), /adjusted for the company's industry;/);
});

test("LIVE4-017: the audit's findings are counted by kind; the holidays table fits its card", async () => {
  const A = await import("../src/lib/auditKinds.ts");
  assert.equal(A.kindOf("Filed no investor presentation in the last two years, though 12 of its filings are about calls"), "Filed no investor presentation in the last two years, though N of its filings are about calls");
  assert.equal(A.kindOf("No annual or quarterly report filed in the last two years: the company has stopped filing with the SEC"), "No annual or quarterly report filed in the last two years");
  const rows = [
    { symbol: "HAL", issues: [{ level: "fact", area: "Documents", detail: "No call transcript filed, though 3 of its filings: none" }, { level: "gap", area: "Checklist", detail: "x" }] },
    { symbol: "ITC", issues: [{ level: "fact", area: "Documents", detail: "No call transcript filed, though 5 of its filings: none" }] },
    { symbol: "TCS", issues: [{ level: "fact", area: "Prices", detail: "Untraded for 4 days" }] },
  ];
  assert.deepEqual(A.kindsOf(rows, "fact"), [
    { area: "Documents", kind: "No call transcript filed, though N of its filings", companies: 2 },
    { area: "Prices", kind: "Untraded for N days", companies: 1 },
  ]);
  assert.match(read("src/pages/admin/AuditPanel.tsx"), /const kinds = kindsOf\(all, show\)/);
  const h = read("src/pages/admin/HolidaysPanel.tsx");
  assert.doesNotMatch(h, /header: "Source"/);
  assert.match(h, /<span className="k-sub-line">\{r\.days_left\} days ahead<\/span>/);
});

test("LIVE4-020: one source for the plan cards (landing and Plans page alike); the full lists folded; a shorter landing on a phone", async () => {
  const P = await import("../src/lib/plans.ts");
  for (const p of ["free", "basic", "pro"]) assert.equal(P.KEY[p].length, 5, p);
  assert.match(read("src/lib/planKeys.ts"), /export \{ KEY \} from "\.\/plans";/);
  const login = read("src/pages/Login.tsx");
  assert.match(login, /\{KEY\[p\]\.map\(\(f\) => <li key=\{f\}><span aria-hidden="true">✓<\/span>\{f\}<\/li>\)\}/);
  assert.match(login, /<summary>Every feature, plan by plan<\/summary>/);
  // the full lists load when the fold opens, in their own file (the landing page's JavaScript budget)
  assert.match(login, /void import\("\.\.\/lib\/planFeatures"\)\.then\(\(m\) => setAll\(m\.FEATURES\)\)/);
  assert.doesNotMatch(read("src/lib/plans.ts"), /export const FEATURES/);
  const F = await import("../src/lib/planFeatures.ts");
  for (const p of ["free", "basic", "pro"]) assert.ok(F.FEATURES[p].length >= 6, p);
  assert.match(css, /\.lp-examples > \.lp-example:nth-child\(n\+2\), \.lp-examples-skel > \.lp-skel-card:nth-child\(n\+2\) \{ display: none; \}/);
  // /features for a visitor is the landing page at its Trade section, kept out of search: noindex from the server and no canonical address
  const vercel = JSON.parse(read("vercel.json"));
  const noindex = vercel.headers.find((h) => h.headers.some((x) => x.key === "X-Robots-Tag" && /noindex/.test(x.value)) && new RegExp(`^${h.source.replace(/\(\?:/g, "(?:")}$`).test("/features"));
  assert.ok(noindex, "/features carries the noindex header");
});

test("LIVE4-021: an ESOP trust's row says what it is, and the insiders' line says its trades are left out", () => {
  const d = read("src/components/Deals.tsx");
  assert.match(d, /d\.trust \? <span className="k-sub-line" data-testid="deal-trust">Employee stock option trust: buys for staff options<\/span>/);
  assert.match(d, /\{rep\.trust_note && <span className="k-muted" data-testid="deals-trust-note"> \{rep\.trust_note\}<\/span>\}/);
});
