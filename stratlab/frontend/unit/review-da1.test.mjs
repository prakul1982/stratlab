// 24 Oct 2026, the deep audit of turning an idea into rules and running it (DA-001 .. DA-028): the simple converter, the
// questions about an idea, the rules card, running without a market, the custom period box and the verdict page's words.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const R = await import("../src/lib/rules.ts");
const { HELP } = await import("../src/lib/help.ts");
const say = (cs) => cs.map((c) => `${R.refName(c.l)} ${c.op} ${c.r.t === "num" ? c.r.v : R.refName(c.r)}`);

test("DA-002: the simple converter carries the subject to \"it\" and reads \"drops below\" as a move across", () => {
  const a = R.parseStrategyText("Buy when RSI drops below 30, sell when it goes back above 55");
  assert.deepEqual(say(a.entry), ["RSI 14 xb 30"]);                   // not "RSI 14 is below 30", a level
  assert.deepEqual(say(a.exit), ["RSI 14 xa 55"]);                    // not "Price is above 55": RSI is what "it" is
  assert.deepEqual(a.unread, []);
  const b = R.parseStrategyText("Buy when RSI crosses above 60 and sell when it falls below 50");
  assert.deepEqual([say(b.entry), say(b.exit)], [["RSI 14 xa 60"], ["RSI 14 xb 50"]]);
  // "it" with nothing before it is the price
  assert.deepEqual(say(R.parseStrategyText("Buy when it goes above the 200 SMA").entry), ["Price xa SMA 200"]);
  // "is above" stays a level
  assert.deepEqual(say(R.parseStrategyText("Buy when RSI is below 30").entry), ["RSI 14 lt 30"]);
});

test("DA-002: a clause the converter cannot read is named, never turned into a rule about the price", () => {
  const p = R.parseStrategyText("Buy when MACD crosses above its signal line and price is above the 50 SMA");
  assert.deepEqual(say(p.entry), ["Price gt SMA 50"]);
  assert.equal(p.unread.length, 1);
  assert.match(p.unread[0], /macd/);
  const v = R.parseStrategyText("Buy when price crosses above VWAP");
  assert.deepEqual(v.entry, []);
  assert.match(v.unread[0], /vwap/);
  const st = R.parseStrategyText("Buy when it's in Stage 2 and RSI crosses above 50");
  assert.deepEqual(say(st.entry), ["RSI 14 xa 50"]);
  assert.match(st.unread[0], /stage 2/);
  // what it reads without a word of complaint
  assert.deepEqual(R.parseStrategyText("Buy when 20 EMA crosses above 50 EMA, sell when it crosses back below. Stop loss 2%").unread, []);
  // a 200-day average is the 200 SMA, not the number 200; a lowest low of N days is a level of its own
  assert.deepEqual(say(R.parseStrategyText("Buy when price is above the 200-day average").entry), ["Price gt SMA 200"]);
  assert.deepEqual(say(R.parseStrategyText("Short when the price falls below the lowest low of the last 20 days, with a 5% trailing stop").entry), ["Price xb 20-candle low"]);
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /The simple converter couldn't read/);
  assert.match(src, /\.\.\.\(unreadNote \? \[unreadNote\] : \[\]\)/);          // it is a warning on the questions card
});

test("DA-001/DA-009: an options idea is refused with the way on, and a builder's note that repeats the refusal is not added", () => {
  const src = read("src/components/IdeaComposer.tsx");
  assert.match(src, /err\.code === "options_idea"\) return \{ built: null, usedAI: false, system: false, options: true, note: err\.message \}/);
  assert.match(src, /to="\/options">Open the Options builder/);
  assert.match(read("src/components/Rules.tsx"), /to="\/options">Open the Options builder/);
  const n = R.noRuleNote("Make me money", ["No entry rule was found.", "Intraday ideas need a candle size."]);
  assert.equal(n.system, false);
  assert.doesNotMatch(n.note, /No entry rule was found/);
  assert.match(n.note, /Intraday ideas need a candle size\.$/);
  assert.equal(R.noRuleNote("Make me money", ["No entry rule was found."]).note, 'We couldn\'t find an entry rule. Say when to buy (or to short), e.g. "Buy when the price is above the 50-day average".');
});

test("DA-007: a time the rules hold is not a number that went missing", () => {
  const s = { ...R.blankStrategy("x"), tf: "15m", session: { ...R.NO_SESSION, squareoff: "15:15" },
    entry: [{ l: { t: "price" }, op: "gt", r: { t: "sma", p: 20 } }], exit: [] };
  assert.deepEqual(R.unplacedNumbers("On 15 minute candles buy above the 20 SMA and square off at 3:15pm", s), []);
  assert.deepEqual(R.unplacedNumbers("On 15 minute candles buy above the 20 SMA and square off at 3:30pm", s), [3, 30]);       // a time not in the rules still counts
  assert.deepEqual(R.unplacedNumbers("buy above the 20 SMA, square off at 15:15", s), []);
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /Every open trade closes at \$\{sess\.squareoff\}, the square-off time/);        // the Exit box says what ends the day
  assert.match(rules, /trades per day:{" "}/);
  assert.doesNotMatch(rules, /any number of|any amount/);
  assert.match(rules, /missing="no limit"/);
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /square-off`\]|\$\{s\.session\.squareoff\} square-off/);
});

test("DA-008: a trailing stop is in the main rules, and a default stop is said", () => {
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /data-testid="trail-line"/);
  assert.match(rules, /data-testid="default-stop-note"/);
  const compose = read("src/components/IdeaComposer.tsx");
  assert.match(compose, /\(strategy\.risk\.trail \?\? 0\) > 0 && !mentioned\.includes\("sl"\)/);
  assert.match(compose, /strategy\.risk = \{ \.\.\.strategy\.risk, sl: 0 \}/);
  assert.match(read("src/pages/NotebookPage.tsx"), /defaultStop=\{!!gaps && experiments\.length === 0/);
});

test("DA-010: the sizing note names the field by its label, and says how risk is sized after losses and gains", () => {
  assert.match(R.NO_STOP_SIZE_NOTE, /"Max capital per trade \(%\)"/);
  assert.doesNotMatch(R.NO_STOP_SIZE_NOTE, /Most in one trade/);
  assert.match(read("src/components/Rules.tsx"), /label="Max capital per trade \(%\)"/);
  assert.match(HELP.risk, /after losses/);
  assert.match(HELP.risk, /after a profit the size stays/);
});

test("DA-005: VWAP says what it is on the candles the rules use", () => {
  const v = R.INDICATORS.find((i) => i.t === "vwap");
  assert.match(v.friendly, /restarts every trading day/);
  assert.match(v.friendly, /not the day's VWAP/);
  assert.match(read("src/components/Rules.tsx"), /data-testid="vwap-note"/);
});

test("DA-006: a short idea's questions say sell, and the default sell card is worded as its rule", () => {
  const g = read("src/components/Gaps.tsx");
  assert.match(g, /const act = sell \? "Sell short" : "Buy"/);
  assert.match(g, /\$\{sell \? "Sells short" : "Buys"\} once, on the candle where it moves across/);
  assert.match(g, /\$\{sell \? "Buy back" : "Sell"\} when \$\{plain\(d\.l\)\} \$\{opSay\(d\.op\)\}/);
  assert.doesNotMatch(g, /drops below \$\{plain\(d\.r\)\}/);
  assert.match(read("src/pages/NotebookPage.tsx"), /op: s\.side === "short" \? "lt" : "gt", r: \{ t: "sma", p: 200 \}/);
});

test("DA-003: Run waits for a market, and the questions are saved in the pick's own queue", () => {
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /if \(!inst && !group\) \{ notify\("Choose what to test it on first[^"]*", \{ label: "Choose market"/);
  assert.match(page, /data-testid="run-needs-market"/);
  assert.ok(page.indexOf("if (!inst && !group) { notify") < page.indexOf('api<{ experiment: Experiment; defaulted'), "refused before the run is sent");
  // gaps go through patch (the saver), not a PUT of their own that could land after the pick and write it over
  assert.match(page, /if \(p\.gaps !== undefined\) \{ if \(p\.gaps\) body\.gaps = fitGaps\(p\.gaps\); else body\.clearGaps = true; \}/);
  assert.doesNotMatch(page, /method: "PUT", body: \{ gaps/);
});

test("DA-004: the offline notice and the questions give the time the top banner gives", async () => {
  const D = await import("../src/lib/dataBack.ts");
  const note = { closed: "weekend", back_at: "2026-10-25T08:00:00+05:30" };
  assert.equal(D.reconnectAt(note, "Asia/Kolkata"), "Sun 25 Oct, 08:00 IST");
  assert.equal(D.reconnectAt(note, "UTC"), "Sun 25 Oct, 08:00 IST (Sun 25 Oct, 02:30 your time)");
  assert.equal(D.reconnectAt({ closed: null, back_at: null }), null);
  assert.equal(D.offlineLine("India", note, "Asia/Kolkata"), "Market data for India is offline right now. It reconnects on Sun 25 Oct, 08:00 IST.");
  assert.equal(D.offlineLine("India", null), "Market data for India is offline right now. It reconnects with the next daily data login.");
  const market = read("src/pages/MarketPage.tsx");
  assert.match(market, /INDIA_FEED\.has\(market\.id\) \? offlineLine\(market\.name, me\?\.data_note\)/);
  assert.doesNotMatch(market, /try again in a few minutes/);
  assert.match(read("src/main.tsx"), /const back = reconnectAt\(note\)/);
  const g = read("src/components/Gaps.tsx");
  assert.match(g, /is an Indian listing, and Indian price data is offline right now/);
  assert.match(read("src/components/IdeaComposer.tsx"), /instMarket: out\.market \?\?/);
});

test("DA-011: the question card is for before the first run", () => {
  const page = read("src/pages/NotebookPage.tsx");
  assert.match(page, /\{gaps && experiments\.length === 0 && \(\s*<GapsCard/);
  assert.match(read("src/components/Gaps.tsx"), /Question \{Object\.keys\(answered\)\.length \+ 1\} of/);
});

test("DA-013: a custom period takes four digits and refuses a minus sign in words; the position-size select fits its words", async () => {
  const chip = read("src/components/kit/ChipBar.tsx");
  assert.match(chip, /count <= 9999/);
  assert.match(chip, /\.slice\(0, 4\)/);
  assert.match(chip, /A minus sign isn't allowed/);
  assert.doesNotMatch(chip, /replace\(\/\\D\/g, ""\)/);
  const { spanDays, spanCheck } = await import("../src/lib/intervals.ts");
  assert.equal(spanDays("1000 days"), 1000);
  assert.deepEqual(spanCheck(3650, 5)(1000, "days"), { value: "1000 days" });
  assert.ok("error" in spanCheck(3650, 5)(4000, "days"));
  const rules = read("src/components/Rules.tsx");
  assert.match(rules, /<Field label="Position size" wide>/);
  assert.match(rules, /label: "By risk \(% of capital\)"/);
});

test("DA-020/DA-028: the verdict headline is one sentence with the checks under it, and the summary is short lines", async () => {
  const { splitHeadline, summaryLines } = await import("../src/lib/tradeUi.ts");
  assert.deepEqual(splitHeadline("44.5 points ahead of buy and hold after costs; 4 of 4 checks run · 2 passed."),
    { main: "44.5 points ahead of buy and hold after costs.", checks: "4 of 4 checks run · 2 passed." });
  assert.deepEqual(splitHeadline("Within a point of buy and hold after costs; lost money on the unseen part of the period."),
    { main: "Within a point of buy and hold after costs.", checks: "Lost money on the unseen part of the period." });
  assert.deepEqual(splitHeadline("Mixed check results."), { main: "Mixed check results.", checks: "" });
  assert.deepEqual(summaryLines("It made money after costs, but some checks pass and some don't. The strategy returned +4.1% after costs, less than buying and holding over the same period (+66.6%). A year at a time, that is about +0.8% (buying and holding: +10.7%)."),
    ["It made money after costs, but some checks pass and some don't.",
      "The strategy returned +4.1% after costs, less than buying and holding over the same period (+66.6%).",
      "A year at a time, that is about +0.8% (buying and holding: +10.7%)."]);
  assert.deepEqual(summaryLines("Only 3 trades in this period. 62.5 points behind."), ["Only 3 trades in this period.", "62.5 points behind."]);
  assert.deepEqual(summaryLines(""), []);
  const page = read("src/pages/ExperimentPage.tsx");
  assert.match(page, /\{head\.main\}<\/h2>/);
  assert.match(page, /data-testid="verdict-checks"/);
});

test("DA-023/DA-024/DA-025: one count of nearby settings, the built and unseen periods named, and an open trade explained", () => {
  const page = read("src/pages/ExperimentPage.tsx");
  assert.doesNotMatch(page, /nearby settings made money\. Yours is outlined/);
  assert.match(page, /<p className="k-small k-muted">Yours is outlined\.<\/p>/);
  assert.doesNotMatch(page, /Spans the split|before the split and closed after it|tuned on these years/);
  assert.match(page, /opened in the built period and closed in the unseen one/);
  assert.match(page, /Closed in the unseen period: counts as built/);
  assert.match(page, /built part: \$\{pct\(unseen\.built_ret\)\}/);
  assert.match(page, /valued at the last close in the return/);
  assert.match(page, /Average trade, win rate and profit factor count closed trades only/);
});

test("DA-003: questions sent with a pick are cut to what the server keeps, so one long note cannot refuse the pick's save", async () => {
  const { fitGaps } = await import("../src/lib/notebookSave.ts");
  const g = fitGaps({ mentioned: ["exit"], notes: ["n".repeat(500), "b"], instName: "RELIANCE", instMarket: "IN", usedAI: true, fallback: "f".repeat(450),
    answered: { exit: "x".repeat(200) }, warnings: ["w".repeat(301)] });
  assert.equal(g.notes[0].length, 300);
  assert.equal(g.fallback.length, 400);
  assert.equal(g.answered.exit.length, 120);
  assert.equal(g.warnings[0].length, 300);
  assert.deepEqual([g.notes[1], g.instName, g.instMarket, g.usedAI], ["b", "RELIANCE", "IN", true]);
  assert.equal(fitGaps({ mentioned: [], notes: Array(14).fill("a"), instName: null, fallback: "" }).notes.length, 10);
});
