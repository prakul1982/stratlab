import type { Cond, Op, Ref, RefType, Risk, Strategy, Tf } from "./types";

/** What a rule can compare, in the groups the rule editor shows (R5O-040): plain names, and `friendly` is the short
 * explanation shown under the list for the one picked. */
export type IndicatorGroup = "avg" | "momentum" | "trend" | "range" | "volume" | "candle" | "day" | "market" | "fo";
export const INDICATOR_GROUPS: [IndicatorGroup, string][] = [
  ["avg", "Price and averages"], ["momentum", "Momentum"], ["trend", "Trend"], ["range", "Swings and breakouts"],
  ["volume", "Volume"], ["candle", "The candle"], ["day", "The trading day"],
  ["market", "The market (India VIX; intraday candles see the previous close)"], ["fo", "F&O stock data (India, daily candles)"],
];
export const INDICATORS: { t: RefType; name: string; friendly: string; pro?: boolean; group: IndicatorGroup }[] = [
  { t: "price", name: "Price", friendly: "The closing price of each candle.", group: "avg" },
  { t: "sma", name: "Average (SMA)", friendly: "The plain average of the last N closing prices.", group: "avg" },
  { t: "ema", name: "Fast average (EMA)", friendly: "An average of the last N closes that leans on the newest ones, so it turns sooner.", group: "avg" },
  { t: "vwap", name: "Volume-weighted average (VWAP)", friendly: "The average price weighted by how much traded at each price.", pro: true, group: "avg" },
  { t: "bb_upper", name: "Upper band (Bollinger)", friendly: "The average plus a few standard deviations: a band above the price.", pro: true, group: "avg" },
  { t: "bb_mid", name: "Middle band (Bollinger)", friendly: "The average the Bollinger bands sit around.", pro: true, group: "avg" },
  { t: "bb_lower", name: "Lower band (Bollinger)", friendly: "The average minus a few standard deviations: a band below the price.", pro: true, group: "avg" },
  { t: "rsi", name: "RSI (0–100)", friendly: "Momentum from 0 to 100: high after a run of gains, low after a run of losses.", group: "momentum" },
  { t: "macd", name: "MACD line", friendly: "The gap between a fast and a slow average.", pro: true, group: "momentum" },
  { t: "macd_signal", name: "MACD signal line", friendly: "A smoothed MACD line; crossings of the two are the usual signal.", pro: true, group: "momentum" },
  { t: "macd_hist", name: "MACD histogram", friendly: "MACD line minus its signal line: above 0 when the line is above.", pro: true, group: "momentum" },
  { t: "stoch_k", name: "Stochastic (0–100)", friendly: "Where the close sits in the recent high-low range, from 0 (at the low) to 100 (at the high).", pro: true, group: "momentum" },
  { t: "supertrend", name: "Supertrend", friendly: "A trailing line below the price in an uptrend and above it in a downtrend.", pro: true, group: "trend" },
  { t: "stage", name: "Stage (1–4)", friendly: "Where the price is in its cycle, from the long average and its slope: 1 basing, 2 rising, 3 topping, 4 falling.", pro: true, group: "trend" },
  { t: "adx", name: "Trend strength (ADX)", friendly: "How strong the trend is, from 0 to 100, whichever way it runs.", pro: true, group: "trend" },
  { t: "atr_pct", name: "Volatility % (ATR)", friendly: "The average candle range as a % of the price.", pro: true, group: "range" },
  { t: "dc_upper", name: "Highest high of N candles", friendly: "The highest high of the previous N candles: crossing above it is a breakout.", pro: true, group: "range" },
  { t: "dc_lower", name: "Lowest low of N candles", friendly: "The lowest low of the previous N candles: crossing below it is a breakdown.", pro: true, group: "range" },
  { t: "volume", name: "Volume", friendly: "How much traded in the candle.", pro: true, group: "volume" },
  { t: "vol_sma", name: "Average volume", friendly: "The average volume of the last N candles.", pro: true, group: "volume" },
  { t: "atr", name: "ATR (points)", friendly: "average range", pro: true, group: "candle" },
  { t: "open", name: "Open", friendly: "the open", pro: true, group: "candle" },
  { t: "high", name: "High", friendly: "the high", pro: true, group: "candle" },
  { t: "low", name: "Low", friendly: "the low", pro: true, group: "candle" },
  { t: "body", name: "Candle body", friendly: "the candle body", pro: true, group: "candle" },
  { t: "upper_wick", name: "Upper wick", friendly: "the upper wick", pro: true, group: "candle" },
  { t: "lower_wick", name: "Lower wick", friendly: "the lower wick", pro: true, group: "candle" },
  { t: "range", name: "Candle range (high − low)", friendly: "the candle range", pro: true, group: "candle" },
  { t: "day_chg", name: "Day change %", friendly: "the day's change", pro: true, group: "day" },
  { t: "prev_close", name: "Previous day's close", friendly: "yesterday's close", pro: true, group: "day" },
  { t: "day_open", name: "Day open", friendly: "today's open", pro: true, group: "day" },
  { t: "day_high", name: "Day high (so far)", friendly: "today's high", pro: true, group: "day" },
  { t: "day_low", name: "Day low (so far)", friendly: "today's low", pro: true, group: "day" },
  { t: "india_vix", name: "India VIX (daily close)", friendly: "India VIX", pro: true, group: "market" },
  { t: "india_vix_chg", name: "India VIX change %", friendly: "India VIX's change", pro: true, group: "market" },
  // an Indian F&O stock's stored daily futures facts (the stock futures desk), on daily candles
  { t: "oi_change_pct", name: "Futures OI change %", friendly: "the change in futures open interest", pro: true, group: "fo" },
  { t: "rollover_pct", name: "Rollover % (OI in later expiries)", friendly: "the rollover", pro: true, group: "fo" },
  { t: "basis_pct", name: "Futures basis % (over the share)", friendly: "the futures' premium", pro: true, group: "fo" },
];
const PRO_TYPES = new Set(INDICATORS.filter((i) => i.pro).map((i) => i.t));
export const DEFAULTS: Partial<Record<RefType, [number, number?]>> = {
  sma: [20], ema: [20], rsi: [14], macd: [12, 26], macd_signal: [12, 26], macd_hist: [12, 26],
  bb_upper: [20, 2], bb_mid: [20, 2], bb_lower: [20, 2], vwap: [20], supertrend: [10, 3], stage: [150, 20],
  adx: [14], stoch_k: [14, 3], atr_pct: [14], dc_upper: [20], dc_lower: [20], vol_sma: [20], atr: [14],
};
export const OPS: { op: Op; say: string; short: string }[] = [
  { op: "xa", say: "crosses above", short: "crosses above" },
  { op: "xb", say: "crosses below", short: "crosses below" },
  { op: "gt", say: "is above", short: "is above" },
  { op: "lt", say: "is below", short: "is below" },
  { op: "eq", say: "is", short: "is" },
];
export const opSay = (op: Op) => OPS.find((o) => o.op === op)!.say;

export function mkRef(t: RefType): Ref {
  if (t === "price") return { t };
  if (t === "num") return { t, v: 50 };
  const d = DEFAULTS[t];
  if (!d) return { t };
  return d[1] != null ? { t, p: d[0], m: d[1] } : { t, p: d[0] };
}

const PLAIN: Partial<Record<RefType, string>> = {
  open: "Open", high: "High", low: "Low", body: "Candle body", upper_wick: "Upper wick", lower_wick: "Lower wick",
  range: "Candle range", prev_close: "Prev close", day_open: "Day open", day_high: "Day high", day_low: "Day low", day_chg: "Day change %",
  india_vix: "India VIX", india_vix_chg: "India VIX change %",
  oi_change_pct: "Futures OI change %", rollover_pct: "Rollover %", basis_pct: "Futures basis %",
};
const TF_WORD: Record<string, string> = { "15m": "15m", "1h": "1h", "1d": "daily" };

/** A rule value's name with its modifiers: "1.5 × Candle body", "EMA 7 (1h)", "Price 1 ago". */
export function refName(r: Ref): string {
  let name = baseName(r);
  if (r.tf) name += ` (${TF_WORD[r.tf]})`;
  if (r.ago) name += ` ${r.ago} candle${r.ago === 1 ? "" : "s"} ago`;
  if (r.k && r.t !== "num") name = `${r.k} × ${name}`;
  return name;
}

function baseName(r: Ref): string {
  if (PLAIN[r.t]) return PLAIN[r.t]!;
  if (r.t === "atr") return `ATR ${r.p ?? 14}`;
  const d = DEFAULTS[r.t] ?? [];
  const p = r.p ?? d[0], m = r.m ?? d[1];
  switch (r.t) {
    case "price": return "Price";
    case "num": return String(r.v ?? "");
    case "sma": case "ema": case "rsi": case "vwap": return `${r.t.toUpperCase()} ${p}`;
    case "macd": return `MACD ${p},${m}`;
    case "macd_signal": return `MACD signal ${p},${m}`;
    case "macd_hist": return `MACD hist ${p},${m}`;
    case "bb_upper": case "bb_mid": case "bb_lower": return `BB ${r.t.slice(3)} ${p},${m}`;
    case "adx": return `ADX ${p}`;
    case "stoch_k": return `Stochastic ${p}`;
    case "atr_pct": return `ATR% ${p}`;
    case "dc_upper": return `${p}-candle high`;
    case "dc_lower": return `${p}-candle low`;
    case "volume": return "Volume";
    case "vol_sma": return `Avg volume ${p}`;
    case "stage": return p === 150 && m === 20 ? "Stage" : `Stage (${p}-candle avg)`;
    default: return `Supertrend ${p},${m}`;
  }
}

const allConds = (s: Strategy) => [...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])];
export const usesPro = (s: Strategy) => allConds(s).some((c) => PRO_TYPES.has(c.l.t) || PRO_TYPES.has(c.r.t));

export const NO_SESSION = { start: "", end: "", squareoff: "", maxTradesDay: 0, cooldown: 0, dailyLossPct: 0 };
// no target unless the person asks for one (R5O-010): "Stop loss 2%" must not come back as "2% stop or a 6% target"
const DEFAULT_RISK: Risk = { capital: 500000, riskPct: 1, maxAlloc: 100, sl: 2, tgt: 0, brokerage: 20, slippage: 0.05 };

/** The sell rule a notebook starts with when its idea says when to buy but not when to sell: the entry condition
 * turning back ("Sell when EMA 20 drops below EMA 50"), or RSI back above 55 after an RSI dip. Empty when nothing
 * follows from the entry; the notebook then says plainly that no sell rule is set. */
export function defaultExit(s: Pick<Strategy, "entry">): Cond[] {
  const first = s.entry[0];
  if (!first) return [];
  if (first.r.t !== "num" && (first.op === "gt" || first.op === "xa")) return [{ l: { ...first.l }, op: "xb", r: { ...first.r } }];
  if (first.l.t === "rsi" && (first.op === "lt" || first.op === "xb")) return [{ l: { ...first.l }, op: "xa", r: { t: "num", v: 55 } }];
  return [];
}

/** A built strategy with the default sell rule filled in when the idea didn't give one, so what the question card
 * shows as the default is what runs. */
export function withDefaultExit<S extends Strategy>(s: S, mentioned: string[]): S {
  if (mentioned.includes("exit") || s.exit.length || (s.side ?? "long") !== "long") return s;
  return { ...s, exit: defaultExit(s) };
}

export function blankStrategy(name = "Untitled notebook"): Strategy {
  return { name, tf: "1d", text: "", entry: [], exit: [], entryJoin: "all", risk: { ...DEFAULT_RISK }, side: "long", shortEntry: [], shortExit: [],
    session: { ...NO_SESSION }, product: "auto", minScore: 0 };
}

/** Capital and brokerage that make sense in each currency. */
export function riskForCurrency(risk: Risk, currency?: string | null): Risk {
  if (currency === "INR" || !currency) return risk;
  const capital = risk.capital === DEFAULT_RISK.capital ? 10000 : risk.capital;
  const brokerage = risk.brokerage === DEFAULT_RISK.brokerage ? 0 : risk.brokerage;
  return { ...risk, capital, brokerage };
}

export const STARTERS = [
  { title: "Ride the trend", level: "Easiest", question: "Does buying when the price climbs above its 50-day average catch real trends?",
    why: "Buys when the price moves above its 50-day average; sells when it drops back below.",
    text: "Buy when price crosses above 50 SMA. Sell when price crosses below 50 SMA. Stop loss 4%, target 10%, risk 1% of capital." },
  { title: "Average crossover", level: "Easy", question: "Does the 20/50 moving-average crossover actually work?",
    why: "Buys when the short-term average overtakes the longer one, a classic sign momentum is turning up.",
    text: "Buy when 20 EMA crosses above 50 EMA. Sell when 20 EMA crosses below 50 EMA. Stop loss 2%, target 6%, risk 1% of capital." },
  { title: "Buy the dip", level: "Moderate", question: "Does buying sharp dips in an uptrend pay off?",
    why: "Buys after a sharp fall (low RSI) while the long-term trend is up, then sells on the bounce.",
    text: "Buy when RSI 14 is below 35 and price is above 200 SMA. Sell when RSI 14 goes above 60. Stop loss 3%, risk 1% of capital." },
];

/* ---------- plain-English parser (no AI): SMA, EMA, RSI and price rules ---------- */
function normInd(w: string): RefType { w = w.trim(); return w === "ema" ? "ema" : w === "rsi" ? "rsi" : "sma"; }
function parseRef(s: string): Ref | null {
  let m;
  if ((m = s.match(/(\d+)\s*[- ]?\s*(?:day|period|bar|candle)?s?\s*(ema|sma|rsi|moving average|ma\b)/))) return { t: normInd(m[2]), p: +m[1] };
  if ((m = s.match(/\b(ema|sma|rsi|ma)\s*\(?\s*(\d+)/))) return { t: normInd(m[1]), p: +m[2] };
  if (/\brsi\b/.test(s)) return { t: "rsi", p: 14 };
  if (/\b(price|close|ltp|it)\b/.test(s)) return { t: "price" };
  return null;
}
export function parseStrategyText(raw: string): { entry: Cond[]; exit: Cond[]; risk: Partial<Risk>; side: "long" | "short" } {
  let t = " " + raw.toLowerCase().replace(/\s+/g, " ") + " ";
  const short = /\b(sell short|short sell|go short|short(?:ing)?\b(?! ?-?term))/.test(t);
  const out: { entry: Cond[]; exit: Cond[]; risk: Partial<Risk>; side: "long" | "short" } = { entry: [], exit: [], risk: {}, side: short ? "short" : "long" };
  const N = "(\\d+(?:\\.\\d+)?)";
  let m;
  if ((m = t.match(new RegExp("trailing(?: stop)?(?: loss)?(?: of| at| =|:)? ?" + N + " ?%"))) || (m = t.match(new RegExp(N + " ?% trailing")))) {
    out.risk.trail = +m[1];
    t = t.replace(m[0], " ");
  }
  if ((m = t.match(/(?:exit|close|sell|cover|square off)(?: the trade)? after (\d+) (?:days?|candles?|bars?|sessions?)/))) {
    out.risk.maxBars = +m[1];
    t = t.replace(m[0], " ");
  } else {
    // "sell when RSI is above 55 or after 15 bars": a time exit in a sell sentence (R11C-004: the 15 was dropped)
    const sentence = t.split(/[.;\n]/).find((x) => /\b(sell|exit|close|cover|square off)\b/.test(x) && /\b(?:or )?after \d+ (?:days?|candles?|bars?|sessions?)\b/.test(x));
    const at = sentence?.match(/\b(?:or )?after (\d+) (?:days?|candles?|bars?|sessions?)\b/);
    if (at) { out.risk.maxBars = +at[1]; t = t.replace(at[0], " "); }
  }
  // "no stop loss" is a stop of 0, said, so it is never asked again or filled with the default 2% (R11C-005)
  if ((m = t.match(/\b(?:no|without(?: an?| any)?|don'?t use(?: an?)?|not? use(?: an?)?)\s+(?:stop[ -]?loss(?:es)?|stops?|sl)\b/))) {
    out.risk.sl = 0;
    t = t.replace(m[0], " ");
  }
  if ((m = t.match(/\b(?:no|without(?: an?| any)?)\s+(?:target|take[ -]?profit|profit target)s?\b/))) {
    out.risk.tgt = 0;
    t = t.replace(m[0], " ");
  }
  // "stop loss 5%" or "5% stop loss", either way round
  const STOP = "(?:stop[ -]?loss|\\bsl\\b|\\bstop\\b)", TARGET = "(?:target|take[ -]?profit|\\btp\\b)";
  if ((m = t.match(new RegExp(STOP + "(?: of| at| =|:)? ?" + N + " ?%"))) || (m = t.match(new RegExp(N + " ?% ?" + STOP)))) out.risk.sl = +m[1];
  if ((m = t.match(new RegExp(TARGET + "(?: of| at| =|:)? ?" + N + " ?%"))) || (m = t.match(new RegExp(N + " ?% ?" + TARGET)))) out.risk.tgt = +m[1];
  if ((m = t.match(new RegExp("\\brisk(?:ing)?(?: of| =|:)? ?" + N + " ?%")))) out.risk.riskPct = +m[1];
  if ((m = t.match(/(?:capital|₹|\$|\brs\.?|\binr|\busd)(?: of| =|:)? ?(\d[\d,]*(?:\.\d+)?) ?(lakhs?|lacs?|crores?|cr|k)?\b/))) {
    let v = +m[1].replace(/,/g, "");
    const u = m[2] || "";
    if (u === "k") v *= 1e3; else if (u.startsWith("la")) v *= 1e5; else if (u.startsWith("cr")) v *= 1e7;
    if (v > 0) out.risk.capital = v;
  }
  t = t.replace(new RegExp(`(?:with |and |, )?(?:an? )?${N} ?% ?(?:${STOP}|${TARGET})`, "g"), " ");
  t = t.replace(/(?:with |and |, )?(?:an? )?(?:stop[ -]?loss|\bsl\b|\bstop\b|target|take[ -]?profit|\btp\b|\brisk(?:ing)?|capital)[^.;,]*?\d[\d,.]*\s*%?(?:\s*(?:lakhs?|lacs?|crores?|cr|k)\b)?(?: of (?:my |the )?capital)?/g, " ");
  const clauses = t.split(/[.;\n]| then |,(?= ?(?:and )?(?:sell|exit|close|square|buy|enter|go long)\b)| and (?=(?:sell|exit|close|square off|buy|enter|go long)\b)/);
  const opRe = /(cross(?:es|ing)? (?:back )?(?:above|over)\b|crossover\b|cross(?:es|ing)? (?:back )?(?:below|under)\b|crossunder\b|\babove\b|greater than|more than|\bover\b|>|\bbelow\b|less than|\bunder\b|<)/;
  let side: "entry" | "exit" = "entry";
  let lastRef: Ref | null = null;
  let lastCross: Cond | null = null;
  // "close" as a way out ("close the trade"), never the price closing ("the price closes above the SMA", R11C-004: that
  // buy rule became a sell rule); the first of the two kinds of word in a clause decides which it is
  const EXIT = /\b(sell|exit|close\b(?! (?:is |was )?(?:above|below|over|under))|square off|book profit)/;
  const first = (cl: string, a: RegExp, b: RegExp): "a" | "b" | null => {
    const i = cl.search(a), j = cl.search(b);
    return i < 0 && j < 0 ? null : j < 0 || (i >= 0 && i <= j) ? "a" : "b";
  };
  for (const cl of clauses) {
    if (short) {
      // a short opens with a sell and closes with a buy
      const w = first(cl, /\b(cover|buy back|buy to cover|exit|close\b(?! (?:is |was )?(?:above|below|over|under))|square off|book profit)/, /\b(short|sell|enter)/);
      if (w === "a") side = "exit";
      else if (w === "b") side = "entry";
    } else {
      const w = first(cl, EXIT, /\b(buy|enter|go long)/);
      if (w === "a") side = "exit";
      else if (w === "b") side = "entry";
    }
    for (const p of cl.split(/ and | & /)) {
      const om = p.match(opRe);
      if (!om || om.index == null) continue;
      const leftText = p.slice(0, om.index);
      let L = parseRef(leftText);
      if (!L && lastRef && !/[a-z]{3,}/.test(leftText.replace(/\b(sell|exit|close|buy|when|if|and|then|it|is|goes|go|moves?|once|price)\b/g, ""))) L = lastRef;
      if (!L && /\b(buy|sell|exit|close|when|if)\b/.test(leftText)) L = { t: "price" };
      if (!L) continue;
      lastRef = L;
      const right = p.slice(om.index + om[0].length);
      const w = om[0];
      let R = parseRef(right);
      if (!R && /cross/.test(w) && lastCross && !/\d/.test(right)) {
        // "sell when it crosses back below": the same two lines as the last crossing, the other way
        L = lastCross.l; R = lastCross.r;
      }
      if (!R) {
        const nm = right.match(/-?\d+(?:\.\d+)?/);
        if (!nm) continue;
        R = { t: "num", v: +nm[0] };
      }
      const op: Op = /cross/.test(w) ? (/under|below/.test(w) ? "xb" : "xa") : /above|greater|more|over|>/.test(w) ? "gt" : "lt";
      out[side].push({ l: L, op, r: R });
      if (op === "xa" || op === "xb") lastCross = { l: L, op, r: R };
    }
  }
  return { ...out, entry: meaningful(out.entry).kept, exit: meaningful(out.exit).kept };
}

/* ---------- checks on built rules (R11C-004) ---------- */
const PRICE_SCALE = new Set<RefType>(["price", "open", "high", "low", "prev_close", "day_open", "day_high", "day_low", "sma", "ema", "vwap",
  "bb_upper", "bb_mid", "bb_lower", "supertrend", "dc_upper", "dc_lower"]);
const SCALE_100 = new Set<RefType>(["rsi", "stoch_k", "adx"]);
const sameRef = (a: Ref, b: Ref) => JSON.stringify(Object.entries(a).filter(([, v]) => v != null).sort()) === JSON.stringify(Object.entries(b).filter(([, v]) => v != null).sort());

/** Rules that can't mean anything, left out with a word for each: a price against 0 or less ("Price crosses below 0"),
 * a 0-100 value against a number outside 0-100, a 0-100 value against a price, a value against itself. */
export function meaningful(conds: Cond[]): { kept: Cond[]; dropped: string[] } {
  const kept: Cond[] = [], dropped: string[] = [];
  for (const c of conds) {
    const say = `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;
    const pairs: [Ref, Ref][] = [[c.l, c.r], [c.r, c.l]];
    const bad = sameRef(c.l, c.r)
      || pairs.some(([a, b]) => PRICE_SCALE.has(a.t) && b.t === "num" && (b.v == null || b.v <= 0))
      || pairs.some(([a, b]) => SCALE_100.has(a.t) && b.t === "num" && b.v != null && (b.v < 0 || b.v > 100))
      || pairs.some(([a, b]) => SCALE_100.has(a.t) && PRICE_SCALE.has(b.t));
    if (bad) dropped.push(say); else kept.push(c);
  }
  return { kept, dropped };
}

/** The numbers in a strategy's rules, risk and session, in every form a sentence may give them. */
function numbersIn(s: Strategy): number[] {
  const out: number[] = [];
  const ref = (r: Ref) => { for (const v of [r.p, r.m, r.v, r.ago, r.k]) if (v != null) out.push(+v); if (r.tf) out.push(+r.tf.replace(/\D/g, "")); };
  for (const c of [...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])]) { ref(c.l); ref(c.r); if (c.w != null) out.push(c.w); }
  // the money settings a sentence can give (a capital in lakh or k too); brokerage and slippage are the app's own
  const r = s.risk as unknown as Record<string, unknown>;
  for (const k of ["sl", "tgt", "trail", "maxBars", "riskPct", "capital", "perTrade", "leverage", "maxAlloc"]) {
    const v = r[k];
    if (typeof v === "number") out.push(v, v / 1e3, v / 1e5, v / 1e7);
  }
  for (const v of Object.values(s.session ?? {})) {
    if (typeof v === "number") out.push(v);
    else if (typeof v === "string" && /^\d{1,2}:\d{2}$/.test(v)) out.push(...v.split(":").map(Number));
  }
  if (s.minScore) out.push(s.minScore);
  out.push(...({ "5m": [5], "15m": [15], "1h": [1, 60], "1d": [1] } as Record<string, number[]>)[s.tf] ?? []);
  return out;
}

/** The numbers a sentence gives that the built rules don't hold (R11C-004: "RSI 14 is above 55" lost its 55 and became
 * "Price is above RSI 14", with nothing said). Numbers in the instrument's own name ("NIFTY 50"), in a candle size ("15
 * minute candles") or a time ("9:30") don't count. */
export function unplacedNumbers(text: string, s: Strategy, names: (string | null | undefined)[] = []): number[] {
  let t = ` ${text.toLowerCase()} `;
  for (const n of names) if (n) t = t.split(n.toLowerCase()).join(" ");
  t = t.replace(/\b(nifty|sensex|bank ?nifty|s&p|nasdaq|dow)\s*\d+/g, " ")
    .replace(/\d+\s*[- ]?\s*(?:min(?:ute)?s?|m|hours?|hr|h|day)\s+(?:candles?|bars?|charts?|timeframe)/g, " ")
    .replace(/\b\d{1,2}:\d{2}\b/g, " ").replace(/\b(?:1|one)[- ]?(?:hour|day)\b/g, " ");
  const have = numbersIn(s);
  const seen = new Set<number>();
  for (const m of t.matchAll(/\d+(?:,\d{3})*(?:\.\d+)?/g)) {
    const v = +m[0].replace(/,/g, "");
    if (!Number.isFinite(v) || seen.has(v)) continue;
    if (!have.some((h) => Math.abs(h - v) < 1e-9 * Math.max(1, Math.abs(v)))) seen.add(v);
  }
  return [...seen];
}

/** What a sentence itself says about the questions the notebook asks ("Stop loss 3%", "No stop loss", "daily candles", a
 * sell rule): a question it answered is never asked, and a default never overwrites it (R11C-005). */
export function statedIn(text: string | undefined | null): string[] {
  if (!text?.trim()) return [];
  const p = parseStrategyText(text);
  const out = Object.keys(p.risk);
  if (p.exit.length) out.push("exit");
  if (detectTf(text)) out.push("tf");
  return out;
}

/** Whether a notebook's name is one it was given rather than one the person typed: none, "Untitled notebook", or the
 * strategy's own name (numbered "… 2" or "… (copy)" as a new notebook or a copy gets it). Only such a name may follow
 * the strategy's (R11C-001: every rule edit put "TCS SMA Crossover" back over the person's own name). */
export function isAutoNotebookName(name: string | null | undefined, strategyName: string | null | undefined): boolean {
  const n = (name ?? "").trim(), s = (strategyName ?? "").trim();
  if (!n || n === "Untitled notebook") return true;
  if (!s) return false;
  return n === s || n === `${s} (copy)` || (n.startsWith(`${s} `) && /^\d+$/.test(n.slice(s.length + 1)));
}

export function detectTf(t: string): Tf | null {
  t = t.toLowerCase();
  if (/\b5\s*-?\s*min/.test(t)) return "5m";
  if (/\b15\s*-?\s*min/.test(t)) return "15m";
  if (/\b(1\s*-?\s*hour|hourly|60\s*-?\s*min|1h)\b/.test(t)) return "1h";
  if (/\b(daily|1\s*-?\s*day|day candles?|1d)\b/.test(t)) return "1d";
  return null;
}

export function detectInstrument(t: string): string | null {
  t = t.toLowerCase();
  if (/bank\s*nifty|nifty\s*bank/.test(t)) return "NIFTY BANK";
  if (/\bnifty(\s*50)?\b/.test(t)) return "NIFTY 50";
  if (/\bbitcoin|\bbtc\b/.test(t)) return "BTC-USD";
  if (/\bethereum|\beth\b/.test(t)) return "ETH-USD";
  if (/\bsolana|\bsol\b/.test(t)) return "SOL-USD";
  const m = t.match(/\b(?:buy|sell|trade)\s+([a-z&]{2,20}(?:\s+[a-z&]{2,20})?)\s+(?:when|if|on|at|once|after|whenever)\b/);
  const stop = ["when", "if", "the", "at", "on", "it", "and", "only", "above", "below", "once", "after", "whenever", "stock", "shares"];
  if (m && !stop.includes(m[1].split(" ")[0])) return m[1].toUpperCase();
  return null;
}

/** A question for the notebook title, from the idea text. */
export function questionFrom(text: string, instrument?: string | null): string {
  const clean = text.trim().replace(/\s+/g, " ").replace(/[.!]+$/, "");
  const first = clean.split(/(?<=[.!?])\s/)[0];
  const short = first.length > 110 ? first.slice(0, 107).trimEnd() + "…" : first;
  const lead = short;                 // in the person's own words and casing (R6O-010: "R test" came back as "r test")
  const named = !instrument || lead.toLowerCase().includes(instrument.toLowerCase().split(/[\s/-]/)[0]);
  return `Does "${lead}" work${named ? "" : ` on ${instrument}`}?`;
}

const OP_SHORT: Record<Op, string> = { xa: "over", xb: "under", gt: "above", lt: "below", eq: "is" };

/** A short notebook name from its first buy rule: "EMA 20 over EMA 50 · NIFTY 50". */
export function nameFor(s: Strategy, instrument?: string | null): string {
  const c = s.entry[0];
  const rule = c ? `${refName(c.l)} ${OP_SHORT[c.op]} ${refName(c.r)}` : "New idea";
  return (instrument ? `${rule} · ${instrument}` : rule).slice(0, 80);
}

/** Does the sentence say when to trade (a buy or short word and a condition word)? If it does, a build that finds no
 * rule is the builder's fault, not the wording's. */
export function looksLikeRule(idea: string): boolean {
  const t = idea.toLowerCase();
  return /\b(buy|short|sell|enter|go long|long)\b/.test(t)
    && /\b(when|if|once|crosses?|crossing|above|below|over|under|rsi|ema|sma|macd|average|breaks?|breakout|falls?|rises?|drops?|supertrend|stage|bollinger|high|low)\b|[<>]/.test(t);
}

/** The words for a build that found no entry rule: ours when the sentence plainly holds one, else what to add. */
export function noRuleNote(idea: string, notes: string[] = []): { note: string; system: boolean } {
  if (looksLikeRule(idea)) {
    return { system: true, note: "That one is on our side: the builder couldn't turn your sentence into rules just now, and your wording looks fine. Try again, start from a classic idea, or build the rules by hand." };
  }
  return { system: false, note: "We couldn't find an entry rule. Say when to buy (or to short), e.g. \"Buy when the price is above the 50-day average\"." + (notes.length ? " " + notes.join(" ") : "") };
}

/** What the person should see about rules that didn't come out as written: a rule left out, a number from the sentence
 * that isn't in the rules (R11C-004). Empty when every number found its place. */
export function ruleWarnings(idea: string, s: Strategy, dropped: string[], names: (string | null | undefined)[] = []): string[] {
  const out = dropped.map((d) => `"${d}" was left out: it can't mean anything as a rule.`);
  const lost = unplacedNumbers(idea, s, names);
  if (lost.length) {
    const list = lost.map((n) => n.toLocaleString("en-IN")).join(", ");
    out.push(`${lost.length === 1 ? "The number" : "The numbers"} ${list} in your words ${lost.length === 1 ? "isn't" : "aren't"} in the rules below. Check the rules before you run it.`);
  }
  return out;
}
