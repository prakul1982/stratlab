/* The maths behind the chart's drawings, with no canvas and no imports so Node can test it directly: distances for
 * picking a line, where a ray leaves the plot, Fibonacci levels, parallel channels, the numbers on a long or short
 * position (risk and reward, quantity from a risk amount), the numbers on a measure (bars, time, % and price change),
 * magnet snapping to a candle's open, high, low or close, and moving a drawing's handle. Arithmetic on what the
 * person drew: no signals, no advice. */

export interface Pt { t: number; p: number }
export interface XY { x: number; y: number }

export type DrawingKind = "trend" | "ray" | "hline" | "hray" | "vline" | "rect" | "channel" | "fib" | "long" | "short"
  | "measure" | "prange" | "drange" | "text" | "arrow" | "brush";
export type DashStyle = "solid" | "dashed" | "dotted";
export type ColorKey = "ink" | "blue" | "orange" | "green" | "magenta" | "grey";
export const COLOR_KEYS: ColorKey[] = ["ink", "blue", "orange", "green", "magenta", "grey"];
export const DASH_KEYS: DashStyle[] = ["solid", "dashed", "dotted"];

export interface Drawing {
  id: string; kind: DrawingKind; points: Pt[];
  text?: string; color?: ColorKey; dash?: DashStyle; locked?: boolean; hidden?: boolean;
  /** The newest candle's time when it was drawn: chart replay shows it only once the replay reaches that candle. */
  born?: number;
  /** A position's risk amount (₹ or $), for the quantity. */
  risk?: number;
}

/** How many points each kind is made of. A brush has as many as its stroke. */
export const POINT_COUNT: Record<Exclude<DrawingKind, "brush">, number> = {
  trend: 2, ray: 2, hline: 1, hray: 1, vline: 1, rect: 2, channel: 3, fib: 2, long: 3, short: 3,
  measure: 2, prange: 2, drange: 2, text: 1, arrow: 2,
};
/** How many clicks or taps place it: a position takes two (entry, then target; the stop is set from them). */
export const CLICKS: Record<DrawingKind, number> = {
  trend: 2, ray: 2, hline: 1, hray: 1, vline: 1, rect: 2, channel: 3, fib: 2, long: 2, short: 2,
  measure: 2, prange: 2, drange: 2, text: 1, arrow: 2, brush: 1,
};

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1];

// ---------- distances and lines ----------
export function distToSegment(px: number, py: number, ax: number, ay: number, bx: number, by: number): number {
  const dx = bx - ax, dy = by - ay;
  const len = dx * dx + dy * dy;
  const t = len ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len)) : 0;
  return Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
}

/** Where a ray from a through b leaves the plot, on the right if it points right, else on the left. */
export function rayEnd(a: XY, b: XY, width: number): XY {
  if (Math.abs(b.x - a.x) < 1e-6) return { x: b.x, y: b.y };
  const k = (b.y - a.y) / (b.x - a.x);
  const x = b.x >= a.x ? width : 0;
  return { x, y: a.y + k * (x - a.x) };
}

/** How far the second line of a parallel channel sits from the first, in pixels straight down: the line through a
 *  and b, and the parallel one through c. */
export function channelShift(a: XY, b: XY, c: XY): number {
  if (Math.abs(b.x - a.x) < 1e-6) return 0;
  const k = (b.y - a.y) / (b.x - a.x);
  return c.y - (a.y + k * (c.x - a.x));
}

/** The Fibonacci price at a level: 0 at the second point and 1 at the first, as charting apps draw it. */
export function fibPrice(first: number, second: number, level: number): number {
  return second + (first - second) * level;
}

/** A level as the label shows it: 0, 0.236, 0.5, 1. */
export function levelText(level: number): string {
  return String(Number(level.toFixed(3)));
}

// ---------- a long or short position ----------
export interface PositionStats {
  side: "long" | "short";
  entry: number; stop: number; target: number;
  /** Price change from entry to the stop and to the target (signed). */
  stopMove: number; targetMove: number;
  /** The same as % of the entry (signed). */
  stopPct: number; targetPct: number;
  /** Money at risk and to gain per unit (positive when the stop and target are on their usual sides). */
  riskPerUnit: number; rewardPerUnit: number;
  /** Reward divided by risk, or null when there is no risk distance. */
  ratio: number | null;
  /** Whole units for the risk amount, or null when there is no amount or no risk distance. */
  qty: number | null;
  /** Money at risk and to gain for that quantity. */
  riskTotal: number | null; rewardTotal: number | null;
  /** The stop is on the side of the entry a stop usually goes, and so is the target. */
  stopSideOk: boolean; targetSideOk: boolean;
}

export function positionStats(side: "long" | "short", entry: number, stop: number, target: number, riskAmount?: number | null): PositionStats {
  const dir = side === "long" ? 1 : -1;
  const riskPerUnit = (entry - stop) * dir;
  const rewardPerUnit = (target - entry) * dir;
  const ratio = riskPerUnit > 0 ? rewardPerUnit / riskPerUnit : null;
  const qty = riskAmount != null && riskAmount > 0 && riskPerUnit > 0 ? Math.floor(riskAmount / riskPerUnit + 1e-9) : null;
  return {
    side, entry, stop, target,
    stopMove: stop - entry, targetMove: target - entry,
    stopPct: entry ? ((stop - entry) / entry) * 100 : 0, targetPct: entry ? ((target - entry) / entry) * 100 : 0,
    riskPerUnit, rewardPerUnit, ratio, qty,
    riskTotal: qty == null ? null : qty * riskPerUnit, rewardTotal: qty == null ? null : qty * rewardPerUnit,
    stopSideOk: riskPerUnit > 0, targetSideOk: rewardPerUnit > 0,
  };
}

/** The three points of a position from the entry and the target: the stop starts half as far on the other side
 *  (a starting size to drag from, not a suggestion). The target and stop share the right edge's time. */
export function buildPosition(entry: Pt, target: Pt): Pt[] {
  const stop = entry.p - (target.p - entry.p) / 2;
  return [{ t: entry.t, p: entry.p }, { t: target.t, p: target.p }, { t: target.t, p: stop }];
}

/** The numbers of a long or short drawing from its points. */
export function statsOf(d: Drawing): PositionStats | null {
  if ((d.kind !== "long" && d.kind !== "short") || d.points.length < 3) return null;
  return positionStats(d.kind, d.points[0].p, d.points[2].p, d.points[1].p, d.risk);
}

// ---------- measuring ----------
export interface MeasureStats {
  /** Price change from the first point to the second, and as % of the first. */
  move: number; pct: number;
  /** Candles from the first point to the second (negative when the second is earlier), and the time between in ms. */
  bars: number; ms: number;
}

export function measureStats(a: Pt, b: Pt, bars: number): MeasureStats {
  return { move: b.p - a.p, pct: a.p ? ((b.p - a.p) / a.p) * 100 : 0, bars, ms: b.t - a.t };
}

/** A time span as 3d 4h, 5h 30m, 12m. Days are exchange days, hours and minutes are clock time. */
export function durationText(ms: number): string {
  const total = Math.abs(Math.round(ms / 60_000));
  const d = Math.floor(total / 1440), h = Math.floor((total % 1440) / 60), m = total % 60;
  const sign = ms < 0 ? "−" : "";
  if (d) return `${sign}${d}d${h ? ` ${h}h` : ""}`;
  if (h) return `${sign}${h}h${m ? ` ${m}m` : ""}`;
  return `${sign}${m}m`;
}

/** The (fractional) candle number at time t: a whole number at a candle's own time, in between inside the data, and
 *  spaced like the nearest candles beyond either end. Matches how the chart places a time on its axis. */
export function fracIndex(times: number[], t: number): number {
  const n = times.length;
  if (!n) return 0;
  if (n === 1) return (t - times[0]) / 86_400_000;
  if (t <= times[0]) return (t - times[0]) / (times[1] - times[0]);
  if (t >= times[n - 1]) return n - 1 + (t - times[n - 1]) / (times[n - 1] - times[n - 2]);
  let lo = 0, hi = n - 1;
  while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (times[mid] <= t) lo = mid; else hi = mid; }
  return lo + (t - times[lo]) / (times[lo + 1] - times[lo]);
}

/** Candles between two times, rounded to whole candles. */
export function barsBetween(times: number[], t0: number, t1: number): number {
  return Math.round(fracIndex(times, t1) - fracIndex(times, t0));
}

// ---------- magnet ----------
export interface Ohlc { o: number; h: number; l: number; c: number }

/** The candle's open, high, low or close nearest to the pointer's height, when it is within `tol` pixels; else null. */
export function snapOhlc(bar: Ohlc, y: number, yOf: (p: number) => number, tol: number): number | null {
  let best: number | null = null, gap = tol;
  for (const p of [bar.o, bar.h, bar.l, bar.c]) {
    const d = Math.abs(yOf(p) - y);
    if (d <= gap) { gap = d; best = p; }
  }
  return best;
}

// ---------- editing ----------
/** A copy of the drawing with one handle moved to `now`. A position's entry moves freely; its target moves in time
 *  and price (the stop follows its time); its stop moves in price only. A level moves in price (and a vertical line
 *  in time) wherever it is grabbed. */
export function moveHandle(d: Drawing, handle: number, now: Pt): Drawing {
  const pts = d.points.map((p) => ({ ...p }));
  if (d.kind === "long" || d.kind === "short") {
    if (handle === 0) pts[0] = { ...now };
    else if (handle === 1) { pts[1] = { ...now }; pts[2] = { t: now.t, p: pts[2].p }; }
    else pts[2] = { t: pts[1].t, p: now.p };
  } else if (pts[handle]) pts[handle] = { ...now };
  return { ...d, points: pts };
}

/** A copy with every point shifted: in time by `dt` and in price by the way `price(p)` maps each point. */
export function shiftDrawing(d: Drawing, dt: number, price: (p: number) => number): Drawing {
  return { ...d, points: d.points.map((p) => ({ t: p.t + dt, p: price(p.p) })) };
}

/** Thin a stroke to at most `max` points, keeping the first and last. */
export function thinStroke(points: Pt[], max: number): Pt[] {
  if (points.length <= max) return points;
  const out: Pt[] = [];
  for (let i = 0; i < max; i++) out.push(points[Math.round((i * (points.length - 1)) / (max - 1))]);
  return out;
}

// ---------- undo and redo ----------
/** A list of states with undo and redo. `push` records the new state and forgets any redo. */
export class History<T> {
  private past: T[] = [];
  private future: T[] = [];
  private limit: number;
  constructor(limit = 100) { this.limit = limit; }
  push(prev: T): void { this.past.push(prev); if (this.past.length > this.limit) this.past.shift(); this.future = []; }
  /** The state to go back to, given the current one (which becomes the redo), or null. */
  undo(current: T): T | null {
    const back = this.past.pop();
    if (back === undefined) return null;
    this.future.push(current);
    return back;
  }
  redo(current: T): T | null {
    const next = this.future.pop();
    if (next === undefined) return null;
    this.past.push(current);
    return next;
  }
  get canUndo(): boolean { return this.past.length > 0; }
  get canRedo(): boolean { return this.future.length > 0; }
  clear(): void { this.past = []; this.future = []; }
}

// ---------- reading saved drawings ----------
const KINDS = new Set<string>([...Object.keys(POINT_COUNT), "brush"]);
const finite = (x: unknown): x is number => typeof x === "number" && Number.isFinite(x) && Math.abs(x) < 1e15;

/** Saved drawings from the account or this browser, with anything unreadable left out. */
export function cleanDrawings(v: unknown): Drawing[] {
  if (!Array.isArray(v)) return [];
  const out: Drawing[] = [];
  for (const raw of v) {
    if (!raw || typeof raw !== "object") continue;
    const r = raw as Record<string, unknown>;
    const kind = r.kind as string;
    if (typeof r.id !== "string" || !/^[A-Za-z0-9_-]{1,40}$/.test(r.id) || !KINDS.has(kind)) continue;
    const pts = (Array.isArray(r.points) ? r.points : []).filter((p): p is Pt => !!p && finite((p as Pt).t) && finite((p as Pt).p))
      .map((p) => ({ t: p.t, p: p.p }));
    const want = kind === "brush" ? 0 : POINT_COUNT[kind as keyof typeof POINT_COUNT];
    if (kind === "brush" ? pts.length < 2 : pts.length !== want) continue;
    const d: Drawing = { id: r.id, kind: kind as DrawingKind, points: pts.slice(0, 400) };
    if (typeof r.text === "string" && r.text) d.text = r.text.slice(0, 200);
    if (COLOR_KEYS.includes(r.color as ColorKey)) d.color = r.color as ColorKey;
    if (DASH_KEYS.includes(r.dash as DashStyle)) d.dash = r.dash as DashStyle;
    if (r.locked === true) d.locked = true;
    if (r.hidden === true) d.hidden = true;
    if (finite(r.born)) d.born = r.born;
    if (finite(r.risk) && r.risk >= 0) d.risk = r.risk;
    out.push(d);
    if (out.length >= 300) break;
  }
  return out;
}

/** The market code and symbol the server keeps drawings under, from a chart's storage key ("IN:RELIANCE",
 *  "CRYPTO:BTC-USD", "REPLAY-abc"). A key with no colon goes under "OTHER", or "REPLAY" for a replay's. */
export function splitKey(key: string): { region: string; symbol: string } {
  const i = key.indexOf(":");
  if (i > 0 && /^[A-Za-z][A-Za-z0-9]{1,11}$/.test(key.slice(0, i)) && key.slice(i + 1)) return { region: key.slice(0, i).toUpperCase(), symbol: key.slice(i + 1).toUpperCase() };
  if (key.startsWith("REPLAY-") && key.length > 7) return { region: "REPLAY", symbol: key.slice(7).toUpperCase() };
  return { region: "OTHER", symbol: key.toUpperCase().replace(/[^A-Z0-9:^&._=-]/g, "_").slice(0, 40) || "X" };
}
