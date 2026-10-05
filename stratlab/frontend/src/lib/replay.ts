/* Chart replay practice: the page's running simulation of practice orders, the same rules as the server's
 * (backend/app/replay.py), which fills them again when a session finishes and is what the journal keeps.
 * unit/replay.test.mjs checks this file against the server's answers (unit/fixtures/replay.json).
 * Free of imports so Node can run the unit tests on it directly.
 *
 * - an order placed on candle i (the last one showing) fills at that candle's close;
 * - a stop or target placed on candle i works from candle i+1, at its price or a gap's open; the stop first when
 *   one candle reaches both;
 * - one position, long or short: adding averages, the other way reduces, and bigger flips (stops and targets cleared);
 * - each run from flat to flat is one trade, charged at the published rates (intraday rates for Indian shares
 *   opened and closed on one day);
 * - what's open at the end closes at the last candle shown ("End of replay"). */

export interface RBar { t: string; o: number; h: number; l: number; c: number; v?: number }
export type Action = "long" | "short" | "flat" | "stop" | "target" | "cancel_stop" | "cancel_target";
export interface ROrder { i: number; action: Action; qty?: number; price?: number }
export type Rates = Record<string, { buy: number; sell: number; flat: number }>;
export interface Fill { i: number; t: string; side: "buy" | "sell"; qty: number; px: number; why: string }
export interface RTrade {
  side: "long" | "short"; qty: number; entry: number; exit: number; entry_i: number; exit_i: number; entry_t: string; exit_t: string;
  gross: number; charges: number; net: number; why: string; fills: number;
}
export interface RPosition { side: "long" | "short"; qty: number; avg: number; mark: number; unrealised: number; stop: number | null; target: number | null }
export interface Result { trades: RTrade[]; fills: Fill[]; position: RPosition | null; skipped: (ROrder & { why: string })[] }

const EPS = 1e-9;

export function floorTo(q: number, step: number): number {
  if (!Number.isFinite(q) || q <= 0) return 0;
  const n = Math.floor(q / step + 1e-9);
  return Math.round(n * step * 1e10) / 1e10;
}

function charges(kind: string, rates: Rates, fills: Fill[], intraday: boolean): number {
  const k = kind === "in_eq" && intraday ? "in_eq_mis" : kind;
  const r = rates[k];
  if (k === "flat" || !r) return 0;
  return fills.reduce((n, f) => n + r.flat + r[f.side] * f.qty * f.px, 0);
}

interface Episode { sign: number; entries: Fill[]; exits: Fill[] }

function trade(ep: Episode, kind: string, rates: Rates): RTrade {
  const ins = ep.entries, outs = ep.exits;
  const qty = ins.reduce((n, f) => n + f.qty, 0);
  const entry = ins.reduce((n, f) => n + f.px * f.qty, 0) / qty;
  const outQ = outs.reduce((n, f) => n + f.qty, 0);
  const exit = outs.reduce((n, f) => n + f.px * f.qty, 0) / Math.max(outQ, EPS);
  const first = String(ins[0].t), last = String(outs[outs.length - 1].t);
  const gross = ep.sign * (exit - entry) * qty;
  const ch = charges(kind, rates, [...ins, ...outs], first.slice(0, 10) === last.slice(0, 10));
  return { side: ep.sign > 0 ? "long" : "short", qty, entry, exit, entry_i: ins[0].i, exit_i: outs[outs.length - 1].i, entry_t: first, exit_t: last,
    gross, charges: ch, net: gross - ch, why: outs[outs.length - 1].why, fills: ins.length + outs.length };
}

/** Run the orders over candles first-1 .. cursor (the backend's replay.simulate). */
export function simulate(bars: RBar[], orders: ROrder[], first: number, cursor: number, kind: string, rates: Rates, step = 1, closeAtEnd = true): Result {
  let pos = 0, avg = 0;
  let stop: { price: number; from: number } | null = null, target: { price: number; from: number } | null = null;
  let ep: Episode | null = null;
  const trades: RTrade[] = [], fills: Fill[] = [], skipped: (ROrder & { why: string })[] = [];
  const byBar = new Map<number, ROrder[]>();
  for (const o of orders) { const l = byBar.get(o.i) ?? []; l.push(o); byBar.set(o.i, l); }

  const fill = (j: number, side: "buy" | "sell", q: number, px: number, why: string) => {
    const sign = side === "buy" ? 1 : -1;
    const f: Fill = { i: j, t: bars[j].t, side, qty: q, px, why };
    fills.push(f);
    let left = q;
    if (pos * sign < 0 && ep) {
      const c = Math.min(left, Math.abs(pos));
      ep.exits.push({ ...f, qty: c });
      pos += sign * c;
      left -= c;
      if (Math.abs(pos) <= EPS) {
        pos = 0;
        trades.push(trade(ep, kind, rates));
        ep = null; stop = null; target = null;
      }
    }
    if (left > EPS) {
      if (!ep) { ep = { sign, entries: [], exits: [] }; avg = 0; }
      ep.entries.push({ ...f, qty: left });
      avg = (avg * Math.abs(pos) + px * left) / (Math.abs(pos) + left);
      pos += sign * left;
    }
  };

  for (let j = first - 1; j <= cursor; j++) {
    const b = bars[j];
    if (pos && j >= first) {
      const long = pos > 0;
      let px: number | null = null, why = "";
      if (stop && stop.from <= j && (long ? b.l <= stop.price : b.h >= stop.price)) {
        px = long ? Math.min(b.o, stop.price) : Math.max(b.o, stop.price); why = "Stop";
      } else if (target && target.from <= j && (long ? b.h >= target.price : b.l <= target.price)) {
        px = long ? Math.max(b.o, target.price) : Math.min(b.o, target.price); why = "Target";
      }
      if (px != null) fill(j, long ? "sell" : "buy", Math.abs(pos), px, why);
    }
    for (const o of byBar.get(j) ?? []) {
      const close = b.c;
      if (o.action === "long" || o.action === "short") {
        const q = floorTo(o.qty ?? 0, step);
        if (q <= 0) { skipped.push({ ...o, why: "Under one lot" }); continue; }
        fill(j, o.action === "long" ? "buy" : "sell", q, close, o.action === "long" ? "Long" : "Short");
      } else if (o.action === "flat") {
        if (pos) fill(j, pos > 0 ? "sell" : "buy", Math.abs(pos), close, "Flat");
      } else if (o.action === "stop" || o.action === "target") {
        const p = o.price ?? 0;
        const wrong = !pos || (o.action === "stop" && (pos > 0 ? p >= close : p <= close)) || (o.action === "target" && (pos > 0 ? p <= close : p >= close));
        if (wrong) { skipped.push({ ...o, why: !pos ? "No position" : "On the wrong side of the price" }); continue; }
        const level = { price: p, from: j + 1 };
        if (o.action === "stop") stop = level; else target = level;
      } else if (o.action === "cancel_stop") stop = null;
      else if (o.action === "cancel_target") target = null;
    }
  }
  let position: RPosition | null = null;
  if (pos && closeAtEnd) fill(cursor, pos > 0 ? "sell" : "buy", Math.abs(pos), bars[cursor].c, "End of replay");
  else if (pos) {
    const last = bars[cursor].c;
    const st = stop as { price: number } | null, tg = target as { price: number } | null;
    position = { side: pos > 0 ? "long" : "short", qty: Math.abs(pos), avg, mark: last, unrealised: (last - avg) * pos, stop: st ? st.price : null, target: tg ? tg.price : null };
  }
  return { trades, fills, position, skipped };
}
