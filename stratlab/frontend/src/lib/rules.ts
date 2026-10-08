import type { Cond, Op, Ref, RefType, Risk, Strategy, Tf } from "./types";

export const INDICATORS: { t: RefType; name: string; friendly: string; pro?: boolean; group?: "candle" | "day" | "market" | "fo" }[] = [
  { t: "price", name: "Price", friendly: "the price" },
  { t: "sma", name: "SMA", friendly: "average price" },
  { t: "ema", name: "EMA", friendly: "fast average" },
  { t: "rsi", name: "RSI", friendly: "momentum (RSI)" },
  { t: "macd", name: "MACD", friendly: "MACD line", pro: true },
  { t: "macd_signal", name: "MACD signal", friendly: "MACD signal", pro: true },
  { t: "macd_hist", name: "MACD histogram", friendly: "MACD histogram", pro: true },
  { t: "bb_upper", name: "Bollinger upper", friendly: "upper Bollinger band", pro: true },
  { t: "bb_mid", name: "Bollinger mid", friendly: "middle Bollinger band", pro: true },
  { t: "bb_lower", name: "Bollinger lower", friendly: "lower Bollinger band", pro: true },
  { t: "vwap", name: "VWAP", friendly: "VWAP", pro: true },
  { t: "supertrend", name: "Supertrend", friendly: "Supertrend", pro: true },
  { t: "stage", name: "Stage (1–4, Weinstein)", friendly: "the market stage", pro: true },
  { t: "adx", name: "ADX (trend strength)", friendly: "trend strength", pro: true },
  { t: "stoch_k", name: "Stochastic %K", friendly: "stochastic", pro: true },
  { t: "atr_pct", name: "ATR % (volatility)", friendly: "volatility", pro: true },
  { t: "dc_upper", name: "Donchian high (breakout)", friendly: "recent high", pro: true },
  { t: "dc_lower", name: "Donchian low (breakdown)", friendly: "recent low", pro: true },
  { t: "volume", name: "Volume", friendly: "volume", pro: true },
  { t: "vol_sma", name: "Volume average", friendly: "average volume", pro: true },
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
const DEFAULT_RISK: Risk = { capital: 500000, riskPct: 1, maxAlloc: 100, sl: 2, tgt: 6, brokerage: 20, slippage: 0.05 };

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
  for (const cl of clauses) {
    if (short) {
      // a short opens with a sell and closes with a buy
      if (/\b(cover|buy back|buy to cover|exit|close|square off|book profit)/.test(cl)) side = "exit";
      else if (/\b(short|sell|enter)/.test(cl)) side = "entry";
    } else if (/\b(sell|exit|close|square off|book profit)/.test(cl)) side = "exit";
    else if (/\b(buy|enter|go long)/.test(cl)) side = "entry";
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
  return out;
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
  const lead = short.charAt(0).toLowerCase() + short.slice(1);
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
