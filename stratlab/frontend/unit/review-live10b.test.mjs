// LIVE10B (17 Nov 2026): the live end-to-end review of Release 60. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10B-024: a holdings file naming stocks already held is asked about, and the chosen way is said before reading", () => {
  const page = read("src/pages/HoldingsPage.tsx");
  assert.match(page, /overlap_ok: overlapOk/);                                         // sent only once the user says so
  assert.match(page, /data-testid="holdings-overlap"/);
  assert.match(page, />Add these shares too</);
  assert.match(page, /setReplacing\(f\); \}\}>Start again with this file</);            // the replace path keeps its confirm
  assert.match(page, /data-testid="holdings-mode-note"/);
  assert.match(page, /you're asked before anything is added/);
});

test("LIVE10B-001: the rupee note names StratLab's US prices and says only rupee prices are charged in rupees", async () => {
  const { usdNote } = await import("../src/lib/usdAbout.ts");
  const note = usdNote(93.56, false, { basic: 8, pro: 20 });
  assert.match(note, /^Prices in ₹ are charged in rupees\./);
  assert.doesNotMatch(note, /Every price is charged in rupees/);
  assert.match(note, /at ₹93\.56 to the dollar \(today's rate\): StratLab's US prices are Basic \$8 and Pro \$20 a month/);
  assert.doesNotMatch(usdNote(93.56), /US prices/);                                   // no US prices read: not named
  for (const p of ["src/pages/PlansPage.tsx", "src/pages/Login.tsx"]) assert.match(read(p), /usdNote\(rate, pricing\?\.usd_inr\?\.fallback, usd\)/);
});

test("LIVE10B-002: the dollar view's yearly small print is in dollars", () => {
  assert.match(read("src/pages/Login.tsx"), /const yearly = \(p: "basic" \| "pro"\) => \(cur === "USD" && usd \? dollarText\(usd\[`\$\{p\}_year`\]\) : rupees\(p, true\)\);/);
});

test("LIVE10B-013: the paper chart's forming candle takes the server's open, high and low", () => {
  const page = read("src/pages/PaperPage.tsx");
  assert.match(page, /forming\.current = \{ t: f\.t, o: f\.o \?\? f\.c, h: f\.h \?\? f\.c, l: f\.l \?\? f\.c \}/);
  assert.match(page, /if \(f\.o != null\) forming\.current\.o = f\.o;/);
});

test("LIVE10B-028: the options stop dialog says the open legs are squared off", async () => {
  const { OPTIONS_STOP_DIALOG } = await import("../src/lib/paperText.ts");
  assert.match(OPTIONS_STOP_DIALOG, /^Open paper legs are squared off at the last price before the stop, and the trade is booked\./);
  const page = read("src/pages/OptionsSession.tsx");
  assert.match(page, /\{OPTIONS_STOP_DIALOG\}<\/ConfirmDialog>/);
  assert.doesNotMatch(page, /Any open paper position is left as it is/);
});

test("LIVE10B-016/030: under a day to expiry theta is said per hour, in the summary and the Greeks table", () => {
  const src = read("src/components/OptionModel.tsx");
  assert.match(src, /const hourly = maxDays - days < 1;/);
  assert.match(src, /<Stat label="Net theta" value=\{inr\(hourly \? sc\.theta \/ 24 : sc\.theta\)\} note=\{hourly \? "an hour: under a day to expiry" : "a day"\} \/>/);
  assert.match(src, /header: hourly \? "Theta \/ hour" : "Theta \/ day"/);
  assert.match(src, /hourly=\{hourly\} \/>/);
});

test("LIVE10B-011: the journal offers the tax report's newer trades only while bringing them in would add some", () => {
  const page = read("src/pages/trade/JournalPage.tsx");
  assert.match(page, /taxLast\.slice\(0, 10\) > newestReal && \(j\.tax_new \?\? 1\) > 0 && \(/);
  assert.match(page, /tax_new\?: number;/);
});

test("LIVE10B-039: a delivery trade whose file's charges leave STT out is marked, with a note under the trades", () => {
  const page = read("src/pages/trade/JournalPage.tsx");
  assert.match(page, /\{t\.no_stt && <sup aria-label="leaves STT out">\*<\/sup>\}/);
  assert.match(page, /data-testid="j-no-stt"/);
  assert.match(page, /the file leaves STT out, so/);
});

test("LIVE10B-040: a business-update figure the newest filing doesn't hold says its month is an earlier filing's", () => {
  const src = read("src/components/BizUpdates.tsx");
  assert.match(src, /\{periodName\(m\.latest\.period, m\.span\)\}\{m\.older \? ", an earlier filing" : ""\}/);
});

test("LIVE10B-005: the notebook's test-period chips take the card's width, not a lone field's 420px", () => {
  assert.match(read("src/pages/NotebookPage.tsx"), /<div className="k-field wide">\s*<div className="k-label-row"><span className="k-lbl">Test period<\/span>/);
  assert.match(read("src/styles.css"), /\.k-card > \.k-field\.wide \{ max-width: none; \}/);
});

test("LIVE10B-009/012: zero or missing journal figures are neutral; deleting a trade says it can't be undone", () => {
  const page = read("src/pages/trade/JournalPage.tsx");
  assert.match(page, /label="Average loss" value=\{m\(s\.avg_loss\)\} tone=\{s\.avg_loss \? "down" : undefined\}/);
  assert.match(page, /value=\{m\(-s\.max_dd\)\} tone=\{s\.max_dd \? "down" : undefined\}/);
  assert.match(page, /\{own \? "Its journal entry goes with it\. This can't be undone\." :/);
});

test("LIVE10B-014/033/045/003: paper start says it starts flat; one minus and grouped days; a tiny yield; Sign up on /signup", () => {
  assert.match(read("src/pages/NotebookPage.tsx"), /It starts with no position: the first trade comes at the next signal\./);
  const tax = read("src/pages/TaxReportPage.tsx");
  assert.match(tax, /r\.loss_pct\.toFixed\(1\)\.replace\("-", "\\u2212"\)/);
  assert.match(tax, /\$\{r\.days\.toLocaleString\("en-IN"\)\} day\$\{r\.days === 1 \? "" : "s"\}/);
  assert.match(read("src/pages/CorpActionsPage.tsx"), /y > 0 && y < 0\.005 \? "<0\.01%" : pctPlain\(y, 2\)/);
  const login = read("src/pages/Login.tsx");
  assert.match(login, /const signup = login && location\.pathname === "\/signup";/);
  assert.match(login, /\$\{signup \? "Sign up" : "Sign in"\} with your Google account or your email address/);
  assert.match(read("src/components/EmailSignIn.tsx"), /\{signup \? "Sign up" : "Sign in"\} with email<\/label>/);
});

test("LIVE10B-007: a chart's window keeps its last point on a time axis (relative slack, not 1e-9 on milliseconds)", () => {
  const src = read("src/components/chart/XYChart.tsx");
  assert.match(src, /const eps = 1e-9 \* Math\.max\(1, Math\.abs\(a\), Math\.abs\(b\)\);/);
  assert.match(src, /in1 = Math\.max\(0, lowerBound\(X, b \+ eps\) - 1\);/);
  // the arithmetic the fix rests on
  const ms = Date.parse("2026-11-13T00:00:00Z");
  assert.equal(ms + 1e-9, ms);
  assert.ok(ms + 1e-9 * ms > ms);
});

test("LIVE10B-008: the hand-trade dialog says a day ahead, or an entry after the exit, under its box", () => {
  const page = read("src/pages/trade/JournalPage.tsx");
  assert.match(page, /entry_date: f\.entry_date > today \? "This day hasn't come yet\." : f\.entry_date > f\.exit_date \? "The entry is after the exit\." : undefined,/);
  assert.match(page, /<DateField label="Entry date" value=\{f\.entry_date\} max=\{today\} error=\{bad\.entry_date\}/);
});

test("LIVE10B-032: replacing the tax report's trades with a file is asked first, naming how many go", () => {
  const page = read("src/pages/TaxReportPage.tsx");
  assert.match(page, /if \(mode === "replace" && \(rep\?\.trades \?\? 0\) > 0\) \{ reset\(\); setReplacing\(list\); return; \}/);
  assert.match(page, /<ConfirmDialog title="Start again with this file\?" confirmLabel="Replace my trades"/);
  assert.match(page, /This replaces your \{\(rep\?\.trades \?\? 0\)\.toLocaleString\("en-IN"\)\} trade/);
});

test("LIVE10B-021: deleting a kept scan is asked first, as a screen's is", () => {
  const page = read("src/pages/ResearchScans.tsx");
  assert.match(page, /onClick=\{\(\) => setDropping\(m\)\}>Delete<\/button>/);
  assert.match(page, /<ConfirmDialog title=\{`Delete "\$\{dropping\.name\}"\?`\} confirmLabel="Delete scan"/);
});
