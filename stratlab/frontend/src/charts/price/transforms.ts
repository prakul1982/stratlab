/* Candle transforms for the price chart: reading the API's candles, Heikin-Ashi, and weekly or monthly candles
 * built from daily ones. Free of imports so Node can run the unit tests on this file directly. */

/** One candle. `t` is the moment it starts (ms since 1970, UTC); `w` is the same moment on the exchange's wall
 *  clock, stored as if it were UTC, so dates and times read with getUTC* are the exchange's own. */
export interface Bar { t: number; w: number; o: number; h: number; l: number; c: number; v: number; day: number }

export interface RawCandle { t: string; o?: number | null; h?: number | null; l?: number | null; c: number; v?: number | null }

const ISO = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?)?(Z|[+-]\d{2}:?\d{2})?$/;

/** [moment, wall clock] for an ISO time. A time with no offset is read as UTC. */
export function parseTime(s: string): [number, number] | null {
  const m = ISO.exec(s.trim());
  if (!m) return null;
  const wall = Date.UTC(+m[1], +m[2] - 1, +m[3], +(m[4] ?? 0), +(m[5] ?? 0), +(m[6] ?? 0));
  let off = 0;
  if (m[7] && m[7] !== "Z") {
    const sign = m[7][0] === "-" ? -1 : 1;
    const digits = m[7].slice(1).replace(":", "");
    off = sign * (+digits.slice(0, 2) * 60 + +digits.slice(2)) * 60_000;
  }
  return [wall - off, wall];
}

/** The day number (days since 1970) of a wall-clock time: candles of one trading day share it. */
export function dayOf(wall: number): number {
  return Math.floor(wall / 86_400_000);
}

/** The API's candles as chart bars: unreadable or empty ones dropped, sorted, one per time, a missing
 *  open/high/low taken from the close. */
export function toBars(raw: RawCandle[]): Bar[] {
  const out: Bar[] = [];
  for (const r of raw) {
    const tw = typeof r?.t === "string" ? parseTime(r.t) : null;
    const c = r?.c == null ? NaN : Number(r.c);
    if (!tw || !Number.isFinite(c)) continue;
    const o = Number.isFinite(Number(r.o)) && r.o != null ? Number(r.o) : c;
    const h0 = Number.isFinite(Number(r.h)) && r.h != null ? Number(r.h) : Math.max(o, c);
    const l0 = Number.isFinite(Number(r.l)) && r.l != null ? Number(r.l) : Math.min(o, c);
    const v = Number(r.v);
    out.push({ t: tw[0], w: tw[1], o, h: Math.max(h0, o, c), l: Math.min(l0, o, c), c, v: Number.isFinite(v) && v > 0 ? v : 0, day: dayOf(tw[1]) });
  }
  out.sort((a, b) => a.t - b.t);
  return out.filter((b, i) => i === out.length - 1 || out[i + 1].t !== b.t);
}

/** Heikin-Ashi candles: each close is the candle's average price and each open the middle of the previous
 *  Heikin-Ashi candle, which smooths the run of colours. */
export function heikinAshi(bars: Bar[]): Bar[] {
  const out: Bar[] = [];
  let po = NaN, pc = NaN;
  for (const b of bars) {
    const c = (b.o + b.h + b.l + b.c) / 4;
    const o = Number.isFinite(po) ? (po + pc) / 2 : (b.o + b.c) / 2;
    out.push({ ...b, o, c, h: Math.max(b.h, o, c), l: Math.min(b.l, o, c) });
    po = o; pc = c;
  }
  return out;
}

/** The start of a wall-clock time's week (Monday) or month, as a wall-clock time. */
export function periodStart(wall: number, unit: "week" | "month"): number {
  const d = new Date(wall);
  if (unit === "month") return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1);
  const day = Math.floor(wall / 86_400_000) * 86_400_000;
  return day - ((d.getUTCDay() + 6) % 7) * 86_400_000;
}

/** Weekly or monthly candles from daily ones: first open, highest high, lowest low, last close, total volume.
 *  Each is stamped with its first daily candle's time. */
export function aggregate(bars: Bar[], unit: "week" | "month"): Bar[] {
  const out: Bar[] = [];
  let key = NaN;
  for (const b of bars) {
    const k = periodStart(b.w, unit);
    const last = out[out.length - 1];
    if (k === key && last) {
      last.h = Math.max(last.h, b.h); last.l = Math.min(last.l, b.l); last.c = b.c; last.v += b.v;
    } else {
      out.push({ ...b });
      key = k;
    }
  }
  return out;
}

/** How far a single candle must stand from both its neighbours to be read as bad data, not a move (DD-043). */
export const SPIKE_X = 3;

/** Monthly (or weekly) candles with a lone bad print taken out, conservatively (DD-043: RELIANCE's 2005 month with a
 *  high of ₹218 among months of ₹40–60, the source's own error). A high more than SPIKE_X times the candle's open, its
 *  close and both neighbours' closes comes down to the top of the candle's body, and a low under a SPIKE_X-th of them
 *  up to its bottom. A candle whose close alone is SPIKE_X times off both neighbours, which agree within 30%, is left
 *  out. A real month is never this: a high three times its own body and both neighbours, or a close that triples and
 *  comes straight back. */
export function dropSpikes(bars: Bar[]): Bar[] {
  if (bars.length < 3) return bars;
  const out: Bar[] = [];
  for (let i = 0; i < bars.length; i++) {
    const b = bars[i], p = bars[i - 1], n = bars[i + 1];
    if (!p || !n) { out.push(b); continue; }
    const near = Math.max(p.c, n.c) / Math.min(p.c, n.c) <= 1.3;
    if (near && (b.c > SPIKE_X * Math.max(p.c, n.c) || b.c * SPIKE_X < Math.min(p.c, n.c))) continue;
    const top = Math.max(b.o, b.c), bottom = Math.min(b.o, b.c);
    const hi = b.h > SPIKE_X * Math.max(top, p.c, n.c) ? top : b.h;
    const lo = b.l * SPIKE_X < Math.min(bottom, p.c, n.c) ? bottom : b.l;
    out.push(hi === b.h && lo === b.l ? b : { ...b, h: hi, l: lo });
  }
  return out;
}

/** Merge newer bars into a series, by time: a bar with a time already there replaces it (the live candle
 *  growing), later ones are appended. Returns how the series changed, so a chart can patch rather than redraw. */
export function merge(bars: Bar[], next: Bar[]): { bars: Bar[]; kind: "same" | "patch" | "append" | "reset" } {
  if (!bars.length || !next.length || next[0].t < bars[0].t) return { bars: next, kind: next.length || bars.length ? "reset" : "same" };
  const out = bars.slice();
  let kind: "same" | "patch" | "append" | "reset" = "same";
  for (const b of next) {
    const last = out[out.length - 1];
    if (b.t > last.t) { out.push(b); kind = "append"; continue; }
    if (b.t === last.t) {
      if (b.o !== last.o || b.h !== last.h || b.l !== last.l || b.c !== last.c || b.v !== last.v) {
        out[out.length - 1] = b;
        if (kind === "same") kind = "patch";
      }
      continue;
    }
    // an older bar that differs means history changed: start over
    const i = binarySearch(out, b.t);
    if (i < 0 || out[i].c !== b.c || out[i].o !== b.o || out[i].h !== b.h || out[i].l !== b.l) return { bars: next, kind: "reset" };
  }
  return { bars: out, kind };
}

/** The index of the bar starting exactly at `t`, or -1. */
export function binarySearch(bars: { t: number }[], t: number): number {
  let lo = 0, hi = bars.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].t === t) return mid;
    if (bars[mid].t < t) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}

/** The index of the last bar starting at or before `t` (-1 when `t` is before every bar). */
export function indexAtOrBefore(bars: { t: number }[], t: number): number {
  let lo = 0, hi = bars.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].t <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

/** The bars [from, to] (indices) to show when `count` of them are in view around bar `center` of `n`: the window sits inside the
 * data, so near either end the bar is off the middle rather than the view running past the data (a timeframe change keeps
 * the moment it was looking at: MWR1-004). */
export function windowAround(n: number, center: number, count: number): [number, number] {
  const want = Math.max(2, Math.min(n, Math.round(count)));
  const c = Math.max(0, Math.min(n - 1, center));
  const from = Math.max(0, Math.min(n - want, Math.round(c - want / 2)));
  return [from, from + want - 1];
}

/** The values the legend, tooltip, change and last-price tag read: always the real bars. Heikin-Ashi changes only how the
 * candle bodies are drawn, so its synthetic opens and closes never reach a number (the replay fills at the real close). */
export function readoutAt(bars: Bar[], i: number): { bar: Bar; prev: Bar | null } | null {
  const bar = bars[i];
  return bar ? { bar, prev: bars[i - 1] ?? null } : null;
}
/** The last real close and whether it is up on the one before (the tag's value and colour). */
export function lastTag(bars: Bar[]): { close: number; up: boolean } | null {
  const last = bars[bars.length - 1];
  if (!last) return null;
  const prev = bars[bars.length - 2];
  return { close: last.c, up: !prev || last.c >= prev.c };
}
