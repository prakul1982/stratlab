// fix12 (17 Nov 2026): what fix11 left of LIVE10A / LIVE10B / CX2. Each test reads the source (or imports a pure module).
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

// extensionless relative imports inside src resolve to their .ts file
register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");

test("LIVE10A-010: the headlines card asks again while the read shown is the session's earlier one, and says so", async () => {
  const { pulseAskAgain, PULSE_AI_TRIES } = await import("../src/lib/pulseMood.ts");
  assert.equal(pulseAskAgain(0, { updating: true }), true);
  assert.equal(pulseAskAgain(0, { updating: false }), false);
  assert.equal(pulseAskAgain(0, null, "The read is being written now. It fills in here in a moment."), true);
  assert.equal(pulseAskAgain(PULSE_AI_TRIES, { updating: true }), false);
  const page = read("src/pages/Research.tsx");
  assert.match(page, /if \(!pulseAskAgain\(again\.current, ai\)\) return;\n    const t = window\.setTimeout\(\(\) => \{ again\.current \+= 1; void loadAI\(\); \}, PULSE_AI_RETRY_MS\);/);
  assert.match(page, /\{ai\.updating && <p className="k-note" data-testid="pulse-ai-updating">\{PULSE_UPDATING_NOTE\}<\/p>\}/);
});

test("LIVE10A-027: a chart's range chips are one scrolling line on a phone, '+ Custom' beside them, not 'All' alone on a second line", () => {
  const bar = read("src/components/kit/ChipBar.tsx");
  assert.match(bar, /const wrapRow = !oneLine && \(wrap \|\| all\.length <= 12\);/);
  assert.match(read("src/components/kit/RangeChips.tsx"), /<ChipBar label=\{label\} options=\{options\} value=\{value\} onChange=\{onChange\} oneLine/);
  assert.match(read("src/pages/BreadthPage.tsx"), /<ChipBar label="History charts' range" oneLine/);
});

test("LIVE10A-027: Breadth on a phone folds its later measures, the sectors and the last 20 days under their headings (nothing removed)", () => {
  const page = read("src/pages/BreadthPage.tsx");
  assert.match(page, /const phone = usePhone\(\);/);
  assert.match(page, /<PhoneFold phone=\{phone\} title="More breadth measures" meta="6 charts" testId="breadth-more">/);
  assert.match(page, /<FoldCard title=\{SECTORS_TITLE\} info=\{help\.sectors\} meta=\{`\$\{data\.sectors\.rows\.length\} sectors`\}/);
  assert.match(page, /<FoldCard title=\{RECENT_TITLE\} info=\{RECENT_INFO\}/);
  // every chart is still drawn: six inside the fold, four above it
  const more = page.slice(page.indexOf('title="More breadth measures"'), page.indexOf("</PhoneFold>"));
  assert.equal((more.match(/<Box title=/g) || []).length, 6);
  assert.equal((page.slice(0, page.indexOf('title="More breadth measures"')).match(/<Box title=/g) || []).length, 4);
});

test("CX2: a filing the exchange listed more than once is one row on the company page that says so", () => {
  assert.match(read("src/components/Filings.tsx"), /\(i\.copies \?\? 1\) > 1 && <span className="k-note" data-testid="filing-copies"> · listed \{i\.copies\} times by the exchange<\/span>/);
});

test("CX2 #7 (jargon): a strategy's trading terms and the library's columns are explained in plain words", async () => {
  const { termMeanings, LIBRARY_COLUMNS } = await import("../src/lib/termMeanings.ts");
  const st = termMeanings("Supertrend (10, 3) · NIFTY 50 stocks");
  assert.equal(st.length, 1);
  assert.match(st[0], /^Supertrend \(N, M\): a line that trails the price/);
  assert.equal(termMeanings("Golden cross (50/200-day averages)").length, 2);     // the cross and the moving average
  assert.deepEqual(termMeanings("Buy the dip"), []);
  for (const say of [...Object.values(LIBRARY_COLUMNS), ...termMeanings("Stage 2 + RSI + MACD + Bollinger + ADX + ATR + VWAP + EMA + breakout")]) {
    assert.doesNotMatch(say, /\b(should|buy now|sell now|recommend|target price|outperform)\b/i, say);   // facts, no advice
  }
  const lib = read("src/components/LibraryBits.tsx");
  assert.match(lib, /header: "Vs buy and hold", numeric: true, sortable: true, info: LIBRARY_COLUMNS\.gap/);
  assert.doesNotMatch(lib, /vs hold \(pts\)/);
  assert.match(lib, /termMeanings\(strategyName\(e\)\)\.length > 0 && <> <Info label=\{`What \$\{strategyName\(e\)\} means`\}>/);
  for (const k of ["ret", "bh", "mdd", "unseen", "checks"]) assert.match(lib, new RegExp(`key: "${k}", header: "[^"]+", (?:numeric|wrap): true, sortable: true, info: LIBRARY_COLUMNS\\.${k},`));
});

test("LIVE10B-026: holdings say each source once with its own one date, and the age note stays for the old part", async () => {
  const { importedLine, oldPart } = await import("../src/lib/holdingsEdit.ts");
  const day = (iso) => ({ "2026-10-28T20:57:00Z": "29 Oct", "2026-11-17T06:00:00Z": "17 Nov" })[iso];
  const words = (s) => `your ${s} file`;
  const age = (iso) => ({ "2026-10-28T20:57:00Z": 19, "2026-11-17T06:00:00Z": 0 })[iso] ?? null;
  const recent = (iso) => (age(iso) < 7 ? "just now" : null);
  // one source: one date, no second date in brackets
  assert.equal(importedLine([{ source: "Zerodha Kite", at: "2026-10-28T20:57:00Z", count: 6 }], { source: null, at: null }, day, words, recent),
    " · imported from your Zerodha Kite file on 29 Oct");
  // two sources: each with its count and day
  const two = [{ source: "Zerodha Kite", at: "2026-10-28T20:57:00Z", count: 4 }, { source: "ICICI Direct", at: "2026-11-17T06:00:00Z", count: 2 }];
  assert.equal(importedLine(two, { source: "ICICI Direct", at: "2026-11-17T06:00:00Z" }, day, words, recent),
    " · 4 imported from your Zerodha Kite file on 29 Oct · 2 from your ICICI Direct file on 17 Nov (just now)");
  assert.deepEqual(oldPart(two, null, 6, age, 7), { days: 19, words: "4 of these 6 holdings are" });
  assert.deepEqual(oldPart(two.slice(0, 1), null, 4, age, 7), { days: 19, words: "These holdings are" });
  assert.equal(oldPart(two.slice(1), null, 2, age, 7), null);
  // a list saved before sources were kept: the list's own source and day
  assert.equal(importedLine([], { source: "Groww", at: "2026-10-28T20:57:00Z" }, day, words, recent), " · imported from your Groww file on 29 Oct");
  const page = read("src/pages/HoldingsPage.tsx");
  assert.doesNotMatch(page, /\(\$\{ago\(view\.updated_at\)\}\)/);
  assert.match(page, /oldPart\(view\.sources, view\.updated_at, t\.count/);
});

test("LIVE10B-034: the tax report's sources line names the fund sales it counts from the CAS, beside the files", () => {
  const page = read("src/pages/TaxReportPage.tsx");
  assert.match(page, /return mf\?\.allowed && mf\.count > 0 \? ` · and \$\{mf\.count\.toLocaleString\("en-IN"\)\} mutual fund sale\$\{mf\.count === 1 \? "" : "s"\} from your CAS on Mutual funds` : "";/);
  assert.match(page, /\{fundSalesLine\(rep\.mf\)\}/);
});
