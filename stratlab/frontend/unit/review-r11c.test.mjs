// Round 11 review of the core strategy product (9 Oct 2026): the app's side, each on the reviewer's example. Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
globalThis.window ??= { STRATLAB_CONFIG: { API_BASE: "", SUPABASE_URL: "", SUPABASE_ANON_KEY: "" } };
const mem = new Map();
globalThis.localStorage ??= { getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => mem.set(k, String(v)), removeItem: (k) => mem.delete(k) };

const R = await import("../src/lib/rules.ts");

test("R11C-001: a rule edit keeps the name the person gave the notebook", () => {
  assert.equal(R.isAutoNotebookName("R test TCS SMA 20/50", "TCS SMA Crossover"), false);
  assert.equal(R.isAutoNotebookName("TCS SMA Crossover", "TCS SMA Crossover"), true);
  assert.equal(R.isAutoNotebookName("TCS SMA Crossover 2", "TCS SMA Crossover"), true);
  assert.equal(R.isAutoNotebookName("TCS SMA Crossover (copy)", "TCS SMA Crossover"), true);
  assert.equal(R.isAutoNotebookName("", "x"), true);
  assert.equal(R.isAutoNotebookName("Untitled notebook", "x"), true);
  const page = read("src/pages/NotebookPage.tsx");
  assert.doesNotMatch(page, /patch\(\{ strategy: st, name: st\.name \}\)/);
  // the name goes with the rules only when the strategy's own name changed and the notebook's is one it was given
  assert.match(page, /st\.name !== s\.name && st\.name && isAutoNotebookName\(nb\.name, s\.name\)/);
});

test("R11C-004: the plain-words converter reads the reviewer's sentences as written", () => {
  const a = R.parseStrategyText("On 15 minute candles, buy when the price closes above the 20-period SMA and RSI 14 is above 55. Sell when RSI 14 drops below 45.");
  assert.deepEqual(a.entry, [{ l: { t: "price" }, op: "gt", r: { t: "sma", p: 20 } }, { l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 55 } }]);
  assert.deepEqual(a.exit, [{ l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 45 } }]);     // "closes above" is not a sell
  const b = R.parseStrategyText("Buy when RSI 14 falls below 30 and price is above the 200-day SMA. Sell when RSI 14 rises above 55 or after 15 bars. Stop loss 3%.");
  assert.equal(b.risk.maxBars, 15);
  assert.equal(b.risk.sl, 3);
  assert.equal(b.exit.length, 1);                                                                 // no "Price crosses below 0"
  const c = R.parseStrategyText("Buy when SMA20 crosses above SMA50. Sell when it crosses below. Use no stop loss.");
  assert.equal(c.side, "long");
  assert.deepEqual(c.exit, [{ l: { t: "sma", p: 20 }, op: "xb", r: { t: "sma", p: 50 } }]);
  assert.equal(c.risk.sl, 0);                                                                     // said: no stop
  assert.equal(R.parseStrategyText("Short when price crosses below 50 SMA, cover when it crosses above").side, "short");
});

test("R11C-004: rules that can't mean anything are left out, and a number the rules lost is said", async () => {
  const { kept, dropped } = R.meaningful([
    { l: { t: "price" }, op: "xb", r: { t: "num", v: 0 } },
    { l: { t: "price" }, op: "gt", r: { t: "rsi", p: 14 } },
    { l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 55 } },
  ]);
  assert.equal(kept.length, 1);
  assert.deepEqual(dropped, ["Price crosses below 0", "Price is above RSI 14"]);
  const s = { ...R.blankStrategy("x"), tf: "15m", entry: [{ l: { t: "price" }, op: "gt", r: { t: "sma", p: 20 } }], exit: [] };
  const idea = "On 15 minute candles, buy when the price closes above the 20-period SMA and RSI 14 is above 55";
  assert.deepEqual(R.unplacedNumbers(idea, s), [14, 55]);
  const full = { ...s, entry: [...s.entry, { l: { t: "rsi", p: 14 }, op: "gt", r: { t: "num", v: 55 } }] };
  assert.deepEqual(R.unplacedNumbers(idea, full), []);
  assert.deepEqual(R.unplacedNumbers("Buy NIFTY 50 when RSI 14 is below 30, 2% stop", { ...R.blankStrategy("x"),
    entry: [{ l: { t: "rsi", p: 14 }, op: "lt", r: { t: "num", v: 30 } }], exit: [] }, ["NIFTY 50"]), []);
  const w = R.ruleWarnings(idea, s, ["Price crosses below 0"]);
  assert.equal(w[0], '"Price crosses below 0" was left out: it can\'t mean anything as a rule.');
  assert.equal(w[1], "The numbers 14, 55 in your words aren't in the rules below. Check the rules before you run it.");
  // the warnings are shown where the rules are: on the questions card and after "Edit in words"
  assert.match(read("src/components/Gaps.tsx"), /\(gaps\.warnings \?\? \[\]\)\.map\(\(w\) => <Notice key=\{w\} tone="warn"/);
  assert.match(read("src/components/Rules.tsx"), /data-testid="rebuild-warnings"/);
  assert.match(read("src/components/IdeaComposer.tsx"), /const checked = \{ entry: meaningful\(out\.entry\)/);
});

test("R11C-005: what the words said is never asked again, and no default writes over it", () => {
  assert.deepEqual(R.statedIn("Buy when the 20 EMA crosses above the 50 EMA. No stop loss.").sort(), ["sl"]);
  assert.ok(R.statedIn("Buy when RSI is below 30. Sell when it rises above 55. Stop loss 3%.").includes("sl"));
  assert.ok(R.statedIn("Buy when RSI is below 30. Sell when it rises above 55.").includes("exit"));
  assert.deepEqual(R.statedIn(""), []);
  assert.match(read("src/components/Gaps.tsx"), /const m = new Set\(\[\.\.\.gaps\.mentioned, \.\.\.statedIn\(s\.text\)\]\)/);
  assert.match(read("src/components/IdeaComposer.tsx"), /const said = parseStrategyText\(idea\)\.risk;/);
});

test("R11C-006: beside another condition, 'price is above the 200-day SMA' defaults to a state, not a cross", () => {
  const gaps = read("src/components/Gaps.tsx");
  assert.match(gaps, /const together = s\.entry\.length > 1;/);
  assert.match(gaps, /\{ label: `Only when it first crosses \$\{w\}`, rec: !together,/);
  assert.match(gaps, /\{ label: `Any time it's \$\{w\}`, rec: together,/);
});

test("R11C-003: 'Every trade' says newest 200 of 250, and its rows plus one line make the total", async () => {
  const { tradeListFacts } = await import("../src/lib/tradeUi.ts");
  const trades = [...Array.from({ length: 200 }, (_, i) => ({ exit_t: `t${i}`, pnl: 1500 })), ...Array.from({ length: 10 }, () => ({ exit_t: null, pnl: 140.5 }))];
  const f = tradeListFacts({ trades, stats: { n: 250, pnl: 279150 } });
  assert.equal(f.caption, "Newest 200 of 250 closed + 10 still open");
  assert.equal(f.hidden, 50);
  assert.equal(f.hiddenPnl + trades.reduce((n, t) => n + t.pnl, 0), 279150);
  assert.equal(tradeListFacts({ trades: trades.slice(0, 15), stats: { n: 15, pnl: 22500 } }).caption, "15 closed");
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /data-testid="trades-caption">\{list\.caption\}/);
  assert.doesNotMatch(page, /\{closed\} closed\{open \?/);
});

test("R11C-014: a group's members show the position still open, so they add up", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /m\.open \? <span className="k-sub-line">\+ 1 still open<\/span>/);
  assert.match(page, /"Still open at the end, not in the rows above"/);
});

test("R11C-007: currency options at their own precision, and a banner without a bid or ask", async () => {
  const O = await import("../src/lib/options.ts");
  assert.equal(O.levelText(95.16234, 0.0025), "95.1625");
  assert.equal(O.levelText(97.1003, 0.0025), "97.1000");
  assert.equal(O.levelText(22289.4, 0.05), "22,289");
  assert.equal(O.staleQuoteLine(0, 4), "");
  assert.equal(O.staleQuoteLine(4, 4), "No live bid or ask: every leg is priced from its last traded price, which may be hours old. The numbers below can be far from what an order would fill at now.");
  assert.match(O.staleQuoteLine(1, 4), /^No live bid or ask for 1 of the 4 legs: it is priced from its last traded price/);
  const page = read("src/pages/OptionsPage.tsx");
  assert.match(page, /\{p\.impossible && <Notice tone="warn" role="status" className="opt-impossible">/);
  assert.match(page, /preview \? `\$\{expiryName\(preview\.expiry\)\} · `/);       // the expiry priced is the one named
});

test("R11C-011: an intraday trade's time is its candle, which it filled at the close of", async () => {
  const { candleSpan } = await import("../src/lib/format.ts");
  assert.equal(candleSpan("2026-10-08T09:30:00-04:00", "15m", "America/New_York", "16:00"), "8 Oct, 09:30–09:45");
  assert.equal(candleSpan("2026-10-09T15:15:00+05:30", "1h", "Asia/Kolkata", "15:30"), "9 Oct, 15:15–15:30");   // the session's last
  assert.equal(candleSpan("2026-10-09T00:00:00+05:30", "1d", "Asia/Kolkata"), "9 Oct 2026");
  assert.match(read("src/components/OrderList.tsx"), /`\$\{candleSpan\(t, tf, tz, close\)\} candle`/);
});

test("R11C-002: the stop dialog keeps its promise, and the stopped page says how the position is valued", async () => {
  const { STOP_DIALOG, stoppedOpenLine } = await import("../src/lib/paperText.ts");
  assert.match(STOP_DIALOG, /^Open paper positions stay open, valued at the last price before the stop\./);
  assert.equal(stoppedOpenLine("long", 29, "$335.35", "$335.88"),
    "Stopped with a position open: 29 bought at $335.35, valued at the last price before the stop, $335.88. Equity, return and the chart use that price.");
  for (const f of ["src/pages/PaperPage.tsx", "src/components/GroupSession.tsx"]) assert.doesNotMatch(read(f), /left as they are/);
});

test("R11C-009: verdict badges and help say facts, not claims", () => {
  const names = read("src/components/ui.tsx").match(/const VERDICT_NAME[^}]*\}/)[0];
  assert.doesNotMatch(names, /: "Likely a real edge"|: "Probably luck"|: "No edge here"/);
  assert.match(names, /edge: "Passed the checks"/);
  const help = read("src/lib/help.ts");
  assert.doesNotMatch(help, /lucky fit|real edge or luck|gained nothing over holding/);
  assert.match(help, /dividends are not added/);                                     // R11C-017: buy and hold is price only
});

test("R11C-013, R11C-017, R11C-018: export keeps the group; the stepper counts a group; long runs say so", async () => {
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /\.\.\.\(group \? \{ group \} : \{\}\)/);
  assert.match(page, /\{ done: !!inst \|\| !!group, text: "Pick what to test it on"/);
  assert.match(read("src/components/ImportStrategy.tsx"), /const group = out\.group \?\? /);
  const { runCopy, runTime } = await import("../src/lib/notebookText.ts");
  assert.equal(runCopy(0, false, 0), "Takes a few seconds.");
  assert.match(runCopy(50, false, 0), /^A group of 50: the first run reads every one's prices and can take a minute or two/);
  assert.match(runCopy(50, true, 45), /^Still running: reading the prices of 50 instruments/);
  assert.equal(runTime(125), "2 min 05 s");
});

test("R11C-015 and R11C-016: a dead link says so; the share page keeps its rules private", () => {
  const v = read("src/pages/PublicVerdict.tsx");
  assert.match(v, /\{gone \|\| "This link was turned off or never existed\."\}/);
  assert.match(v, /The strategy's rules are private to the person who shared it\./);
});
