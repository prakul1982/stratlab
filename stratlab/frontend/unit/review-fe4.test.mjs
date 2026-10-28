// Frontend review (watchlist, races, provider names, uploads, zones, formatting slips). Run: npm run test:unit
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";
import { inrCompact, qty, signed, signedInrCompact } from "../src/lib/format.ts";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));
const { linkLabel, missingLine, missingWhat } = await import("../src/lib/researchFormat.ts");

const read = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");

test("a gain or loss that rounds to zero prints no sign", () => {
  assert.equal(signedInrCompact(0.4), "₹0");
  assert.equal(signedInrCompact(-0.4), "₹0");
  assert.equal(signedInrCompact(0), "₹0");
  assert.equal(inrCompact(-0.4), "₹0");
  assert.equal(signedInrCompact(2960000000), "+₹296 cr");
  assert.equal(signedInrCompact(-180000000), "−₹18 cr");
  assert.equal(signedInrCompact(1), "+₹1");
  assert.equal(signed(0.4), "0");
  assert.equal(signed(-0.4), "0");
  assert.equal(signed(5), "+5");
  assert.equal(signed(-1234, 0, "US"), "−1,234");
});

test("the journal's signed money has no '+' on a zero that rounds off", () => {
  const src = read("src/pages/trade/JournalPage.tsx");
  assert.match(src, /const s = m\(v\); return v > 0 && \/\[1-9\]\/\.test\(s\) \? `\+\$\{s\}` : s;/);
});

test("fractional quantities are grouped like whole ones", () => {
  assert.equal(qty(1234.5), "1,234.5");
  assert.equal(qty(1234567.25, undefined, "US"), "1,234,567.25");
  assert.equal(qty(1234567.25), "12,34,567.25");
  assert.equal(qty(0.5), "0.5");
  assert.equal(qty(0.00000001), "0.00000001");
  assert.equal(qty(208772), "2,08,772");
});

test("the company page names what is missing, never the source or its error", () => {
  const one = [{ source: "Market data", ok: false, error: "Yahoo is busy (our rate limit).", what: ["prices"] }];
  assert.equal(missingLine(one), "Some data is missing: prices.");
  const many = [{ source: "Company data", ok: false, error: "Finnhub 429", what: ["prices", "financials", "news"] }, { source: "Company profile", ok: false, error: "x", what: ["the company profile"] },
    { source: "Fundamentals", ok: true, error: null }];
  assert.equal(missingLine(many), "Some data is missing: prices, financials, news and the company profile.");
  assert.deepEqual(missingWhat([{ source: "News", ok: false }, { source: "News", ok: false, what: ["news"] }]), ["news"]);
  assert.equal(missingLine([{ source: "Fundamentals", ok: false }]), "Some data is missing: financials.");
  // an unknown label names nothing rather than "some data" twice (review 4d)
  assert.equal(missingLine([{ source: "Whatever", ok: false }]), "Some data is missing.");
  assert.doesNotMatch(missingLine(many), /Yahoo|Finnhub|Screener|429/);
  const src = read("src/components/Research.tsx");
  assert.match(src, /\{missingLine\(sources\)\}/);
  assert.doesNotMatch(src, /\$\{s\.source\} \(\$\{s\.error\}\)/);
});

test("company page links are labelled by the kind of page, with no provider's name", () => {
  assert.equal(linkLabel({ label: "Yahoo Finance", kind: "quote" }), "Quote page");
  assert.equal(linkLabel({ label: "Screener.in", kind: "financials" }), "Financials");
  assert.equal(linkLabel({ label: "Profile page", kind: "profile" }), "Profile");
  assert.equal(linkLabel({ label: "BSE", kind: "exchange" }), "BSE");
  assert.match(read("src/pages/Research.tsx"), /label: `\$\{linkLabel\(l\)\} ↗`/);
});

test("the watchlist is never saved over a list that was not read", () => {
  const src = read("src/lib/research.ts");
  // a save reads the saved list first (or refuses), and a toggle works from that list, never from a null one
  assert.match(src, /try \{ cur = await loadWatch\(\); \} catch \{ throw new Error\(WATCH_UNREAD\); \}/);
  assert.match(src, /const toggle = async \(item: WatchItem, want: boolean\): Promise<boolean> => \{\s*let changed = false;\s*await save\(\(cur\) =>/);
  assert.doesNotMatch(src, /\(items \?\? \[\]\)/);
  assert.match(src, /return \{ items, has, toggle, save, failed: failed && items === null, retry:/);
  for (const f of ["src/pages/Research.tsx", "src/pages/MineHome.tsx", "src/pages/SpaceHomes.tsx"]) {
    const page = read(f);
    assert.match(page, /useWatchlist\(\);/);
    assert.match(page, /Try again/, `${f} offers Try again when the watchlist can't be opened`);
    assert.match(page, /onClick: retry|onClick=\{retry\}/);
  }
});

test("Pulse and Themes ignore a late answer for the market or theme that was left", () => {
  const src = read("src/pages/Research.tsx");
  assert.match(src, /const mine = \+\+seq\.current;\s*\n\s*setBusy\(true\); setError\(null\)/);
  assert.match(src, /if \(mine === seq\.current\) setR\(out\)/);
  assert.match(src, /finally \{ if \(mine === seq\.current\) setBusy\(false\); \}/);
  assert.match(src, /try \{ const out = await researchApi\.pulseAI\(region, "", refresh\); if \(mine === seq\.current\) setAi\(out\); \}/);
  // R24-001: the levels load through usePulse, which still drops an answer for a market that was left
  assert.match(src, /researchApi\.pulse\(region\)\.then\(\(d\) => \{\s*if \(!live\) return;/);
});

test("the closing auction keeps its data on a failed poll, says so, and keeps polling", () => {
  const src = read("src/pages/trade/ClosingAuctionPage.tsx");
  assert.match(src, /if \(have\) \{ setStale\(true\); timer = window\.setTimeout\(load, REFRESH_MS\); \}/);
  assert.match(src, /setError\(null\); setStale\(false\);/);
  assert.match(src, /\{stale && <p className="k-note" role="status" data-testid="cas-stale">/);
});

test("a later file that fails doesn't hide the files stored before it", () => {
  const tax = read("src/pages/TaxReportPage.tsx");
  assert.match(tax, /catch \(e\) \{ if \(!refused\(e\)\) fail\(e\); \} finally \{\s*\/\/[^\n]*\n\s*if \(got\) \{ setResult\(got\); setRep\(got\.report\)/);
  const journal = read("src/pages/trade/JournalPage.tsx");
  assert.match(journal, /catch \(e\) \{ if \(!refused\(e\)\) fail\(e\); \} finally \{\s*\/\/[^\n]*\n\s*if \(last\) \{ setResult\(\{ \.\.\.last, added, duplicates: dup \}\); adopt\(last\.journal\)/);
});

test("the money calendar shows only the answer to the last window asked", () => {
  const src = read("src/pages/money/MoneyCalendarPage.tsx");
  assert.match(src, /const n = \+\+seq\.current;\s*\n\s*setError\(null\);/);
  assert.match(src, /if \(n === seq\.current\) \{ setView\(v\)/);
  assert.match(src, /if \(n !== seq\.current\) return; setError/);
});

test("Results and Corporate actions drop the search text and the list when the market or the set changes", () => {
  for (const f of ["src/pages/ResultsPage.tsx", "src/pages/CorpActionsPage.tsx"]) {
    const src = read(f);
    // (the results page also closes the day it had opened in full, DE-026)
    assert.match(src, /if \(shownFor !== `\$\{region\}\|\$\{scope\}`\) \{ setShownFor\(`\$\{region\}\|\$\{scope\}`\); setQ\(""\); setData\(null\);( setOpenDay\(""\);)? \}/, f);
    assert.match(src, /<Field key=\{region\} label="Find a company">/, f);
  }
});

test("a deep-dive read or check that finishes for another company is ignored", () => {
  const src = read("src/pages/DeepDive.tsx");
  assert.equal((src.match(/if \(mine !== here\.current\) return;/g) ?? []).length, 2);
  assert.match(src, /here\.current = `\$\{region\}:\$\{sym\}`;/);
  assert.match(src, /finally \{ if \(mine === here\.current\) setReading\(false\); \}/);
  assert.match(src, /finally \{ if \(mine === here\.current\) setCarding\(false\); \}/);
});

test("Screens clears the result on a market change and scans drop a late answer", () => {
  const screens = read("src/pages/Screens.tsx");
  assert.match(screens, /seq\.current\+\+; setOut\(null\); setRows\(\[\]\);\s*\n\s*setMeta\(null\);/);
  const scans = read("src/pages/ResearchScans.tsx");
  assert.match(scans, /const n = \+\+seq\.current;\s*\n\s*setBusy\(true\);/);
  assert.match(scans, /if \(n === seq\.current\) setOut\(r\);/);
  assert.match(scans, /finally \{ if \(n === seq\.current\) setBusy\(false\); \}/);
});

test("the Account page says what Download gives, not that there is no download", () => {
  const src = read("src/pages/AccountPage.tsx");
  assert.doesNotMatch(src, /doesn't have a download of everything/);
  assert.doesNotMatch(src, /There is no single export/);
  assert.match(src, /Download everything StratLab keeps for you as one file \(tokens and passwords are left out\)/);
});

test("the ITR year select stays enabled while a year loads; the old view is dimmed and busy", () => {
  const src = read("src/pages/money/ItrExportPage.tsx");
  assert.match(src, /setLoadingFy\(fy\); setError\(null\);/);
  assert.doesNotMatch(src, /setV\(null\); setError\(null\);\s*\n\s*setMovedFrom/);
  assert.match(src, /value=\{loadingFy \?\? v\?\.fy \?\? ""\} disabled=\{!v\}/);
  assert.match(src, /aria-busy=\{loadingFy != null\}/);
});

test("Admin: users search drops a late answer; first-load failures offer Try again; prices take commas; invoices use money()", () => {
  const A = "src/pages/admin/";
  assert.match(read(A + "UsersSection.tsx"), /if \(n === seq\.current\) \{ setUsers\(r\)/);
  assert.match(read(A + "RulesPanel.tsx"), /ErrorState title="The rates and rules couldn't be read" action=\{\{ label: "Try again"/);
  assert.match(read(A + "OverviewSection.tsx"), /ErrorState title="The server's status couldn't be read" action=\{\{ label: "Try again"/);
  assert.match(read(A + "PricesPanel.tsx"), /ErrorState title="The prices couldn't be read" action=\{\{ label: "Try again"/);
  assert.match(read(A + "PricesPanel.tsx"), /parsePrice\(v\)/);   // commas are taken by parsePrice (review-5d)
  const inv = read(A + "InvoiceAdminPanel.tsx");
  assert.match(inv, /money\(r\.total, r\.currency, 2\)/);
  assert.match(inv, /money\(r\.tax, r\.currency, 2\)/);
  assert.doesNotMatch(inv, /toFixed\(2\)/);
});

test("the journal's hour breakdown names the market's zone, and 'today' follows the market's day", () => {
  const j = read("src/pages/trade/JournalPage.tsx");
  assert.match(j, /by the hour they were entered \(\{tzLabel\(marketTz\(market\.toUpperCase\(\)\)\)\}\)/);
  assert.match(j, /<Breakdowns b=\{j\.breakdowns\} r=\{j\.r\} market=\{j\.market\} \/>/);
  assert.match(j, /const today = \[istToday\(\), local\]\.sort\(\)\[0\];/);      // India's day, never ahead of the reader's (DB-044)
  assert.doesNotMatch(j, /toISOString\(\)\.slice\(0, 10\)/);
  assert.match(read("src/pages/money/NetWorthPage.tsx"), /const today = \(\) => istToday\(\);/);
  assert.match(read("src/pages/money/UsTaxPage.tsx"), /const today = \(\) => dayIn\(new Date\(\), ET\) \?\? "";/);
  assert.doesNotMatch(read("src/pages/money/NetWorthPage.tsx"), /toISOString\(\)\.slice\(0, 10\)/);
});

test("a symbol in the margin-funding link is encoded; the invoice date and the mover price are formatted", () => {
  assert.match(read("src/pages/MarginFundingPage.tsx"), /href=\{`\?s=\$\{encodeURIComponent\(r\.symbol\)\}`\}/);
  assert.match(read("src/components/InvoicesCard.tsx"), /\{fmtDate\(r\.date\)\} · \{r\.supply\}/);
  assert.match(read("src/pages/MineHome.tsx"), /\{price\(m\.q\.price, m\.region === "US" \? "USD" : "INR"\)\}/);
});

test("answering a holdings notice puts focus on the next thing, not the top of the page", () => {
  const src = read("src/components/HoldingsActions.tsx");
  assert.match(src, /notify\(done\);\s*\n\s*requestAnimationFrame\(\(\) => focusAfterAnswer\(\)\);/);
  assert.match(src, /className="ha-notice"/);
  assert.match(src, /className="k-note ha-undo"/);
  assert.match(src, /<Card id="holdings-dividends">/);
});

test("lot tables key each row by its place too, so equal lots don't share a key", () => {
  assert.equal((read("src/pages/money/TaxToolsPage.tsx").match(/rowKey=\{\(r, i\) => `\$\{r\.key\}\$\{r\.bought\}\$\{r\.qty\}-\$\{i\}`\}/g) ?? []).length, 3);
  assert.match(read("src/pages/money/UsTaxPage.tsx"), /rowKey=\{\(l, i\) => `\$\{l\.symbol\}\$\{l\.bought\}\$\{l\.qty\}-\$\{i\}`\}/);
  assert.match(read("src/components/kit/DataTable.tsx"), /key=\{rowKey\(r, ri\)\}/);
});
