/* Indicator maths for the price chart: a port of the backend engine (app/engine/indicators.py), so a line drawn
 * on the chart is the same line a strategy's rule tests. Missing values are NaN. Checked against fixtures the
 * engine writes (unit/indicators.test.mjs). Kept free of imports so Node can run the tests on this file directly. */

export interface OHLCV { o: number; h: number; l: number; c: number; v: number; day?: number }

/** pandas rolling(n).mean(): blank until n values. */
export function sma(xs: number[], n: number): number[] {
  const out = new Array<number>(xs.length).fill(NaN);
  let sum = 0, bad = 0;
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i];
    if (Number.isFinite(x)) sum += x; else bad++;
    if (i >= n) { const y = xs[i - n]; if (Number.isFinite(y)) sum -= y; else bad--; }
    if (i >= n - 1 && bad === 0) out[i] = sum / n;
  }
  return out;
}

/** pandas rolling(n).sum(). */
function rollingSum(xs: number[], n: number): number[] {
  return sma(xs, n).map((m) => m * n);
}

/** pandas ewm(alpha, adjust=False, min_periods): seeded with the first value; blank while fewer than
 *  `minPeriods` values have been seen. Leading blanks are skipped. */
export function ewm(xs: number[], alpha: number, minPeriods: number): number[] {
  const out = new Array<number>(xs.length).fill(NaN);
  let y = NaN, seen = 0;
  for (let i = 0; i < xs.length; i++) {
    const x = xs[i];
    if (Number.isFinite(x)) {
      y = Number.isFinite(y) ? (1 - alpha) * y + alpha * x : x;
      seen++;
    }
    if (seen >= minPeriods && Number.isFinite(y)) out[i] = y;
  }
  return out;
}

export function ema(xs: number[], n: number): number[] {
  return ewm(xs, 2 / (n + 1), n);
}

function wilder(xs: number[], n: number): number[] {
  return ewm(xs, 1 / n, n);
}

export function rsi(c: number[], n: number): number[] {
  const up: number[] = [], dn: number[] = [];
  for (let i = 0; i < c.length; i++) {
    const d = i === 0 ? NaN : c[i] - c[i - 1];
    up.push(Number.isFinite(d) ? Math.max(d, 0) : NaN);
    dn.push(Number.isFinite(d) ? Math.max(-d, 0) : NaN);
  }
  const u = wilder(up, n), w = wilder(dn, n);
  return u.map((a, i) => {
    const b = w[i];
    if (b === 0 && Number.isFinite(a)) return 100;
    if (!Number.isFinite(a) || !Number.isFinite(b) || b === 0) return NaN;
    return 100 - 100 / (1 + a / b);
  });
}

export function macd(c: number[], fast: number, slow: number, signal = 9): { line: number[]; signal: number[]; hist: number[] } {
  const f = ema(c, fast), s = ema(c, slow);
  const line = f.map((x, i) => x - s[i]);
  const sig = ewm(line, 2 / (signal + 1), signal);
  return { line, signal: sig, hist: line.map((x, i) => x - sig[i]) };
}

/** Bollinger bands: the n-candle average and k population standard deviations either side. */
export function bollinger(c: number[], n: number, k: number): { upper: number[]; mid: number[]; lower: number[] } {
  const mid = sma(c, n);
  const sd = new Array<number>(c.length).fill(NaN);
  for (let i = n - 1; i < c.length; i++) {
    const m = mid[i];
    if (!Number.isFinite(m)) continue;
    let ss = 0;
    for (let j = i - n + 1; j <= i; j++) ss += (c[j] - m) ** 2;
    sd[i] = Math.sqrt(ss / n);
  }
  return { upper: mid.map((m, i) => m + k * sd[i]), mid, lower: mid.map((m, i) => m - k * sd[i]) };
}

/** VWAP: within each trading day on intraday candles (bars need `day`), else over the last n candles. Candles
 *  with no volume (indices) count with equal weight. */
export function vwap(bars: OHLCV[], n: number, intraday: boolean): number[] {
  const tp = bars.map((b) => (b.h + b.l + b.c) / 3);
  const vol = bars.map((b) => (b.v > 0 ? b.v : 1));
  if (intraday) {
    const out: number[] = [];
    let day: number | undefined, pv = 0, vv = 0;
    bars.forEach((b, i) => {
      if (b.day !== day) { day = b.day; pv = 0; vv = 0; }
      pv += tp[i] * vol[i]; vv += vol[i];
      out.push(pv / vv);
    });
    return out;
  }
  const pv = rollingSum(tp.map((x, i) => x * vol[i]), n), vv = rollingSum(vol, n);
  return pv.map((x, i) => x / vv[i]);
}

export function trueRange(bars: OHLCV[]): number[] {
  return bars.map((b, i) => {
    const pc = i === 0 ? b.c : bars[i - 1].c;
    return Math.max(b.h - b.l, Math.abs(b.h - pc), Math.abs(b.l - pc));
  });
}

/** Supertrend: the trailing band (n-candle ATR times mult around the candle's middle) price is on the right side of. */
export function supertrend(bars: OHLCV[], n: number, mult: number): number[] {
  const size = bars.length;
  const atr = wilder(trueRange(bars), n);
  const fu = new Array<number>(size).fill(NaN), fl = new Array<number>(size).fill(NaN), st = new Array<number>(size).fill(NaN);
  for (let i = 0; i < size; i++) {
    if (!Number.isFinite(atr[i])) continue;
    const { h, l, c } = bars[i];
    const hl2 = (h + l) / 2, ub = hl2 + mult * atr[i], lb = hl2 - mult * atr[i];
    if (i === 0 || !Number.isFinite(fu[i - 1])) {
      fu[i] = ub; fl[i] = lb;
      st[i] = c >= hl2 ? lb : ub;
      continue;
    }
    const pc = bars[i - 1].c;
    fu[i] = ub < fu[i - 1] || pc > fu[i - 1] ? ub : fu[i - 1];
    fl[i] = lb > fl[i - 1] || pc < fl[i - 1] ? lb : fl[i - 1];
    if (st[i - 1] === fu[i - 1]) st[i] = c <= fu[i] ? fu[i] : fl[i];
    else st[i] = c >= fl[i] ? fl[i] : fu[i];
  }
  return st;
}

const FLAT = 0.01;

/** Weinstein's market stage, 1 to 4, from the n-candle average and its slope over `look` candles (see the engine). */
export function stage(c: number[], n = 150, look = 20): number[] {
  const avg = sma(c, n);
  const out = new Array<number>(c.length).fill(NaN);
  let last = NaN;
  for (let i = 0; i < c.length; i++) {
    const prev = i >= look ? avg[i - look] : NaN;
    const a = avg[i], s = (a - prev) / prev;
    if (!Number.isFinite(s) || !Number.isFinite(a)) continue;
    let st: number;
    if (s > FLAT) st = c[i] > a ? 2 : 3;
    else if (s < -FLAT) st = c[i] < a ? 4 : 1;
    else if (last === 2 || last === 3) st = 3;
    else if (last === 4 || last === 1) st = 1;
    else st = c[i] >= a ? 1 : 3;
    out[i] = last = st;
  }
  return out;
}

/** The highest high and lowest low over the trailing window ending at each candle (52 weeks on daily candles). */
export function rangeHighLow(bars: OHLCV[], times: number[], spanMs: number): { high: number[]; low: number[] } {
  const high: number[] = [], low: number[] = [];
  // monotonic queues keep this linear however long the window is
  const qh: number[] = [], ql: number[] = [];
  let start = 0;
  for (let i = 0; i < bars.length; i++) {
    while (times[i] - times[start] > spanMs) start++;
    while (qh.length && bars[qh[qh.length - 1]].h <= bars[i].h) qh.pop();
    while (ql.length && bars[ql[ql.length - 1]].l >= bars[i].l) ql.pop();
    qh.push(i); ql.push(i);
    while (qh[0] < start) qh.shift();
    while (ql[0] < start) ql.shift();
    high.push(bars[qh[0]].h); low.push(bars[ql[0]].l);
  }
  return { high, low };
}
