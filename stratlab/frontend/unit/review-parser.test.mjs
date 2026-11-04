// 57.1 (Instinct deep QA, 1 Nov): the AI idea reader must never be silently wrong. Every built idea shows "We read this as …"
// with each line marked by how sure it is (stated / the AI's reading / assumed / asked below) and "We assumed: …"; with no
// instrument named none is picked and "Which stock or index?" asks, with a search right there.
// Run: npm run test:unit
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { register } from "node:module";

register("data:text/javascript," + encodeURIComponent(`export async function resolve(s, c, next) {
  try { return await next(s, c); } catch (e) { if (/^\\.\\.?\\//.test(s) && !/\\.\\w+$/.test(s)) return next(s + ".ts", c); throw e; } }`));

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
const R = await import("../src/lib/rules.ts");
const { fitGaps } = await import("../src/lib/notebookSave.ts");

const ema = (p) => ({ t: "ema", p });
const cross = (op) => ({ l: ema(20), op, r: ema(50) });
const idea = (over = {}) => ({ ...R.blankStrategy("x"), entry: [cross("xa")], exit: [cross("xb")], risk: { ...R.blankStrategy("x").risk, sl: 3 }, ...over });
const marks = (r) => Object.fromEntries(r.lines.map((l) => [l.text, l.mark ?? "stated"]));

test("57.1: rules read from the words are shown plain; the AI's own reading is marked as that", () => {
  const sure = R.readAs(idea(), { mentioned: ["exit", "sl", "tf"], usedAI: true, confirmed: ["entry", "exit"] }, true);
  assert.deepEqual(marks(sure), { "Buy when EMA 20 crosses above EMA 50": "stated", "Sell when EMA 20 crosses below EMA 50": "stated",
    "Daily candles": "stated", "Stop loss 3%": "stated" });
  assert.deepEqual(sure.assumed, []);
  const ai = R.readAs(idea(), { mentioned: ["exit", "sl", "tf"], usedAI: true, confirmed: [] }, true);
  assert.equal(marks(ai)["Buy when EMA 20 crosses above EMA 50"], "ai");
  assert.equal(marks(ai)["Sell when EMA 20 crosses below EMA 50"], "ai");
  assert.equal(R.READ_MARK.ai, "AI's reading");
});

test("57.1: what the words don't say is marked Assumed and said under We assumed; no instrument is Asked below", () => {
  const r = R.readAs(idea({ risk: { ...R.blankStrategy("x").risk } }), { mentioned: [], usedAI: true, confirmed: ["entry"],
    assumed: ["RSI is read over 14 candles, its usual length: your words give none."] }, false);
  const m = marks(r);
  assert.equal(m["Which stock or index: your words name none"], "asked");
  assert.equal(m["Sell when EMA 20 crosses below EMA 50"], "assumed");            // the default sell rule, not the words'
  assert.equal(m["Daily candles"], "assumed");
  assert.equal(m["Stop loss 2%"], "assumed");
  assert.equal(m["Buy when EMA 20 crosses above EMA 50"], "stated");
  assert.equal(r.assumed[0], "RSI is read over 14 candles, its usual length: your words give none.");   // the reading's own first
  assert.ok(r.assumed.includes("Daily candles: your words give no candle length."));
  assert.ok(r.assumed.includes("A 2% stop loss: your words set none."));
  assert.ok(r.assumed.some((a) => a.startsWith("The sell rule: your words say when to buy, not when to sell")));
  assert.deepEqual([R.READ_MARK.assumed, R.READ_MARK.asked], ["Assumed", "Asked below"]);
});

test("57.1: an answer given is no longer an assumption, and a picked instrument no longer asked", () => {
  const r = R.readAs(idea({ exit: [] }), { mentioned: [], usedAI: true, answered: { tf: "1 day", sl: "2% (middle)", inst: "RELIANCE" } }, false);
  const m = marks(r);
  assert.equal(m["Daily candles"], "stated");
  assert.equal(m["Stop loss 3%"], "stated");
  assert.equal(m["Sell: your words give no rule"], "asked");
  assert.ok(!Object.keys(m).some((k) => k.startsWith("Which stock")));
  // the stop is the way out ("exit if it falls 8%"): no sell rule, and nothing asked about one
  const stop = R.readAs(idea({ exit: [] }), { mentioned: ["exit", "sl"], usedAI: true, confirmed: ["entry", "exit"] }, true);
  assert.ok(!Object.keys(marks(stop)).some((k) => k.startsWith("Sell")));
});

test("57.1: the questions card shows We read this as, asks Which stock or index? with a search, and keeps what the server read", () => {
  const g = read("src/components/Gaps.tsx");
  assert.ok(g.includes('data-testid="read-as"') && g.includes("We read this as") && g.includes("We assumed:"));
  assert.ok(g.includes('title: "Which stock or index?"') && g.includes("<InstrumentSearch"));
  assert.ok(g.includes("none was picked for you"));
  const c = read("src/components/IdeaComposer.tsx");
  assert.ok(c.includes("confirmed: usedAI ? out.confirmed ?? [] : []") && c.includes("assumed: usedAI ? out.assumed ?? [] : []"));
  const kept = fitGaps({ mentioned: [], notes: [], instName: null, fallback: "", confirmed: ["entry", "bogus"], assumed: ["x".repeat(400)] });
  assert.deepEqual(kept.confirmed, ["entry"]);
  assert.equal(kept.assumed[0].length, 300);
});

test("57.1: the simple converter reads a DMA as the day average, not a price of 200", () => {
  const p = R.parseStrategyText("buy when price closes above the 200 DMA, sell when it closes back under it");
  assert.deepEqual(p.entry, [{ l: { t: "price" }, op: "gt", r: { t: "sma", p: 200 } }]);
  assert.deepEqual(p.exit, [{ l: { t: "price" }, op: "lt", r: { t: "sma", p: 200 } }]);
  // and the exact matrix it already read right stays right
  const e = R.parseStrategyText("Buy when the 20 EMA crosses above the 50 EMA, sell when it crosses back below, 3% stop loss.");
  assert.deepEqual(e.entry, [cross("xa")]);
  assert.deepEqual(e.exit, [cross("xb")]);
  assert.equal(e.risk.sl, 3);
});
