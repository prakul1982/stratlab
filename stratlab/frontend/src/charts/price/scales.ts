/* Scales for canvas charts: a time scale over bar indices (no gaps for nights and weekends, like a trading chart)
 * and a value scale with normal, log and percent modes. Plain classes with no drawing in them, so other charts
 * (option Greeks, payoffs) can reuse them. */

export type ScaleMode = "normal" | "log" | "percent";

/** Bar index <-> x. `right` is the (fractional) bar index at the right edge of the plot; `spacing` is px per bar. */
export class TimeScale {
  width = 0;
  spacing = 8;
  right = 0;
  minSpacing = 0.25;
  maxSpacing = 64;

  x(i: number): number {
    return this.width - (this.right - i) * this.spacing;
  }

  index(x: number): number {
    return this.right - (this.width - x) / this.spacing;
  }

  /** The first and last bar indices on screen (may be outside the data). */
  visible(): [number, number] {
    return [Math.floor(this.index(0)), Math.ceil(this.right)];
  }

  /** Zoom by `factor` (>1 zooms in) keeping the bar under `anchorX` where it is. */
  zoom(factor: number, anchorX: number): void {
    const at = this.index(anchorX);
    this.spacing = Math.min(this.maxSpacing, Math.max(this.minSpacing, this.spacing * factor));
    this.right = at + (this.width - anchorX) / this.spacing;
  }

  pan(dx: number): void {
    this.right -= dx / this.spacing;
  }

  /** Show bars `from`..`to` (indices) across the width, with `pad` empty bars on the right. */
  fit(from: number, to: number, pad = 0): void {
    const n = Math.max(1, to - from + 1 + pad);
    this.spacing = Math.min(this.maxSpacing, Math.max(this.minSpacing, this.width / n));
    this.right = to + pad + 0.5;
  }
}

/** Value <-> y inside a pane. In log mode prices are spaced by ratio; in percent mode by change from `base`. */
export class ValueScale {
  mode: ScaleMode = "normal";
  base = 1;                 // percent mode: the value that reads 0%
  top = 0;
  height = 100;
  lo = 0;                   // the visible range, in transformed units
  hi = 1;

  tf(v: number): number {
    if (this.mode === "log") return Math.log(Math.max(v, 1e-12));
    if (this.mode === "percent") return (v / this.base - 1) * 100;
    return v;
  }

  untf(u: number): number {
    if (this.mode === "log") return Math.exp(u);
    if (this.mode === "percent") return this.base * (1 + u / 100);
    return u;
  }

  y(v: number): number {
    return this.top + (1 - (this.tf(v) - this.lo) / (this.hi - this.lo || 1)) * this.height;
  }

  value(y: number): number {
    return this.untf(this.lo + (1 - (y - this.top) / this.height) * (this.hi - this.lo));
  }

  /** Fit real values lo..hi, leaving `marginTop` and `marginBottom` (fractions of the height) empty. */
  fit(lo: number, hi: number, marginTop = 0.08, marginBottom = 0.08): void {
    let a = this.tf(lo), b = this.tf(hi);
    if (!Number.isFinite(a) || !Number.isFinite(b)) { a = 0; b = 1; }
    if (b - a < 1e-9) { const pad = Math.abs(a) * 0.01 || 1; a -= pad; b += pad; }
    const span = (b - a) / Math.max(0.1, 1 - marginTop - marginBottom);
    this.lo = a - span * marginBottom;
    this.hi = this.lo + span;
  }

  /** Zoom the value range around its middle (factor > 1 zooms in). */
  zoom(factor: number): void {
    const mid = (this.lo + this.hi) / 2, half = (this.hi - this.lo) / 2 / factor;
    this.lo = mid - half; this.hi = mid + half;
  }

  /** Move the value range by `dy` pixels. */
  pan(dy: number): void {
    const d = (dy / this.height) * (this.hi - this.lo);
    this.lo += d; this.hi += d;
  }

  /** Round values for gridlines and labels, about one per `gap` pixels. */
  ticks(gap = 44): number[] {
    const count = Math.max(2, Math.floor(this.height / gap));
    if (this.mode === "log") {
      const lo = this.untf(this.lo), hi = this.untf(this.hi);
      // nice steps in price, thinned so neighbours stay `gap` apart on screen
      const out: number[] = [];
      let lastY = Infinity;
      for (const v of niceTicks(lo, hi, count * 3)) {
        const y = this.y(v);
        if (lastY - y >= gap * 0.8) { out.push(v); lastY = y; }
      }
      return out;
    }
    return niceTicks(this.lo, this.hi, count).map((u) => this.untf(u));
  }
}

/** About `count` round numbers (1, 2, 2.5, 5 x 10^k steps) between lo and hi. */
export function niceTicks(lo: number, hi: number, count: number): number[] {
  if (!(hi > lo) || !Number.isFinite(lo) || !Number.isFinite(hi)) return [];
  const raw = (hi - lo) / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? 10 * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.abs(v) < step * 1e-9 ? 0 : v);
  return out;
}

/** Decimal places that tell neighbouring ticks `step` apart. */
export function stepDecimals(step: number): number {
  if (!(step > 0)) return 2;
  return Math.max(0, Math.min(8, Math.ceil(-Math.log10(step) - 1e-9)));
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Time-axis labels: at the bars where a year, month, day or hour starts, the biggest boundaries first, kept
 *  `gap` px apart. `walls` are the bars' wall-clock times (ms, read as UTC). */
export function timeTicks(walls: number[], from: number, to: number, x: (i: number) => number, gap = 84): { i: number; label: string; major: boolean }[] {
  const a = Math.max(1, from), b = Math.min(walls.length - 1, to);
  if (b < a) return [];
  const step = Math.max(1, Math.floor((b - a) / 4000));       // very long views: look at every k-th bar only
  const marks: { i: number; w: number; label: string }[] = [];
  for (let i = a; i <= b; i += step) {
    const p = new Date(walls[i - step >= 0 ? i - step : 0]), d = new Date(walls[i]);
    let w = 0, label = "";
    if (d.getUTCFullYear() !== p.getUTCFullYear()) { w = 5; label = String(d.getUTCFullYear()); }
    else if (d.getUTCMonth() !== p.getUTCMonth()) { w = 4; label = MONTHS[d.getUTCMonth()]; }
    else if (d.getUTCDate() !== p.getUTCDate()) { w = 3; label = String(d.getUTCDate()); }
    else if (d.getUTCHours() !== p.getUTCHours()) { w = 2; label = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`; }
    else if (d.getUTCMinutes() % 30 === 0 && d.getUTCMinutes() !== p.getUTCMinutes()) { w = 1; label = `${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`; }
    if (w) marks.push({ i, w, label });
  }
  const taken: number[] = [];
  const out: { i: number; label: string; major: boolean }[] = [];
  for (const w of [5, 4, 3, 2, 1]) {
    for (const m of marks) {
      if (m.w !== w) continue;
      const px = x(m.i);
      if (taken.some((t) => Math.abs(t - px) < gap)) continue;
      taken.push(px);
      out.push({ i: m.i, label: m.label, major: w >= 4 });
    }
  }
  return out.sort((p, q) => p.i - q.i);
}

/** A bar's wall-clock time in words for the crosshair label: "Tue 5 Mar '24" or "5 Mar '24 09:15". */
export function timeLabel(wall: number, intraday: boolean): string {
  const d = new Date(wall);
  const date = `${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(2)}`;
  if (!intraday) return `${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getUTCDay()]} ${date}`;
  return `${date} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}`;
}
