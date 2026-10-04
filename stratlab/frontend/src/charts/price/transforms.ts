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
