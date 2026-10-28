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
