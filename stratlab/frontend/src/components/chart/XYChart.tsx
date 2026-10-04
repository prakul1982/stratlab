import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as RPointerEvent, type ReactNode } from "react";
import { isIntraday, niceDomain, niceTicks, plainTick, RANGE_PRESETS, timeTicks, tipTime, toMs } from "../../lib/chartFormat";
import { linePath, linear, lowerBound, nearest, plotHeight, textWidth, useSync, useTween, useWidth } from "./core";
import { ChartEmpty, ChartTip, LegendToggles, TipRow } from "./parts";

/* The one chart behind every line, area and column chart in the app. Series share one x (a time per point, or a number
 * such as an underlying price) and one y scale. What every chart gets:
 *  - a crosshair that snaps to the nearest point and a tooltip with every series at that x (mouse, keyboard, or a tap and
 *    drag on a touch screen);
 *  - zoom: drag across the plot (desktop), pinch (touch), Ctrl/⌘ + wheel; Shift-drag, a sideways swipe or a trackpad
 *    scroll pans; double-click, Escape or the Reset button go back to everything;
 *  - range buttons (1M … All) when there are dates and more than a couple of months of them;
 *  - a legend whose items switch series on and off (for two or more series), with direct labels at the line ends when
 *    there's room; an "Index to 100" view when two series of different size sit together;
 *  - charts with the same `sync` name share their crosshair and window (by date), so stacked charts read together;
 *  - smooth moves when the window or series change (none when the reader asked for reduced motion), and live data that
 *    grows at the right edge keeps the window following it instead of jumping;
 *  - thousands of points thinned to what the screen can show, peaks kept;
 *  - a table view of the points in the window.
 * Extra curves, horizontal reference lines, vertical markers and point marks are plain props, so a chart such as the
 * options payoff can grow without touching this file. */

export interface Series {
  id?: string;                      // stable key; the label when missing
  label: string;
  values: (number | null)[];
  color: string;                    // a CSS colour, usually a token: var(--series-1)
  width?: number;                   // line width (2 by default)
  dash?: string;                    // stroke-dasharray for a comparison or projection line
  kind?: "line" | "bar";
  /** A wash under the line down to `base` (0 by default): one colour, or `pos`/`neg` colours either side of the base. */
  area?: { base?: number; color?: string; pos?: string; neg?: string };
  format?: (v: number) => string;   // this series' tooltip number (the chart's `format` otherwise)
  hidden?: boolean;                 // starts switched off
  inTooltip?: boolean;              // false keeps it out of the tooltip
  inLegend?: boolean;               // false keeps it out of the legend and direct labels
}
/** A horizontal line at a y value: zero for P&L, a threshold, a level. */
export interface RefLine { v: number; label?: string; color?: string; dash?: boolean; strong?: boolean }
/** A vertical line at an x value (the chart's x units): the spot price, a breakeven, an event. */
export interface XMarker { x: number; label?: string; color?: string; dash?: boolean; strong?: boolean }
/** A mark on a series at a point: buy/sell triangles, a dot. */
export interface PointMark { i: number; series?: number; kind: "buy" | "sell" | "dot"; color?: string }

export interface XYChartProps {
  series: Series[];
  /** x of each point when it's a number (an underlying price); points are evenly spaced (one per index) otherwise. */
  x?: number[];
  /** A time per point (ISO or ms): a date axis, range buttons, linked charts. */
  times?: (string | number)[];
  tz?: string;
  labels?: string[];                // tooltip heading per point (from the times or x otherwise)
  axisLabels?: string[];            // x-axis text per point, when there are neither times nor x
  xFormat?: (x: number) => string;  // a numeric x in the tooltip and on the axis
  format: (v: number) => string;    // a value in the tooltip
  axisFormat?: (v: number) => string;
  height?: number;
  refs?: RefLine[];
  xMarkers?: XMarker[];
  points?: PointMark[];
  split?: number | null;            // index where "unseen data" starts: shaded from there on
  splitNotes?: [string, string];
  ariaLabel: string;
  sync?: string;                    // charts with the same name share crosshair and window
  ranges?: boolean;                 // range buttons (default: with times spanning over ~6 weeks)
  zoom?: boolean;                   // default: on from 8 points
  compare?: boolean;                // offer "Index to 100"
  legend?: boolean;                 // default: with two or more series
  table?: boolean;                  // offer a table of the points in view (default on)
  includeZero?: boolean;
  tableX?: string;                  // the table's first column heading
  onHover?: (i: number | null) => void;
  tipExtra?: (i: number) => ReactNode;
  testId?: string;
}

type View = [number, number];
const DAY = 86_400_000;
const PAD = { r: 10, t: 10, b: 24 };

export function XYChart(p: XYChartProps) {
  const { series, format, height = 240, refs = [], xMarkers = [], points = [], ariaLabel } = p;
  const uid = useId();
  const [wrap, W] = useWidth<HTMLDivElement>();
  const H = plotHeight(height, W);
  const n = series.reduce((m, s) => Math.max(m, s.values.length), 0);

  const T = useMemo(() => (p.times && p.times.length === n ? p.times.map(toMs) : null), [p.times, n]);
  const X = useMemo(() => (p.x && p.x.length === n ? p.x : Array.from({ length: n }, (_, i) => i)), [p.x, n]);
  const hasBars = series.some((s) => s.kind === "bar");
  const ext: View = n ? (hasBars && !p.x ? [X[0] - 0.5, X[n - 1] + 0.5] : [X[0], X[n - 1]]) : [0, 1];
  const intraday = useMemo(() => (T ? isIntraday(T) : false), [T]);
  const key = (s: Series) => s.id ?? s.label;

  const [hidden, setHidden] = useState<Set<string>>(() => new Set(series.filter((s) => s.hidden).map(key)));
  const [indexed, setIndexed] = useState(false);
  const [view, setViewRaw] = useState<View | null>(null);
  const [instant, setInstant] = useState(false);
  const [range, setRange] = useState<string>("all");
  const [hover, setHoverRaw] = useState<number | null>(null);
  const [remote, setRemote] = useState<number | null>(null);
  const [kbd, setKbd] = useState(false);
  const [sel, setSel] = useState<[number, number] | null>(null);
  const [showTable, setShowTable] = useState(false);
  const svg = useRef<SVGSVGElement>(null);

  // ---- the visible window ----
  const clampView = (v: View): View | null => {
    const span = ext[1] - ext[0];
    const minSpan = p.x ? span / 400 : Math.min(span, 4);
    let [a, b] = v[0] <= v[1] ? v : [v[1], v[0]];
    if (b - a < minSpan) { const c = (a + b) / 2; a = c - minSpan / 2; b = c + minSpan / 2; }
    if (b - a >= span - 1e-9) return null;
    if (a < ext[0]) { b += ext[0] - a; a = ext[0]; }
    if (b > ext[1]) { a -= b - ext[1]; b = ext[1]; }
    return [Math.max(ext[0], a), Math.min(ext[1], b)];
  };
  const toTimes = (v: View | null): View | null => {
    if (!v || !T) return v;
    const at = (x: number) => T[Math.max(0, Math.min(n - 1, nearest(X, x)))];
    return [at(v[0]), at(v[1])];
  };
  const sync = useSync(p.sync, uid, (m) => {
    if (m.hover !== undefined) {
      if (m.hover == null || !n) setRemote(null);
      else if (T) setRemote(m.hover >= T[0] - DAY && m.hover <= T[n - 1] + DAY ? nearest(T, m.hover) : null);
      else setRemote(nearest(X, m.hover));
    }
    if (m.view !== undefined) {
      setInstant(false);
      if (!m.view) { setViewRaw(null); setRange("all"); return; }
      const [t0, t1] = m.view;
      const v: View = T ? [X[Math.min(n - 1, lowerBound(T, t0))], X[Math.max(0, Math.min(n - 1, lowerBound(T, t1 + 1) - 1))]] : [t0, t1];
      setViewRaw(clampView(v)); setRange("");
    }
  });
  const setView = (v: View | null, opts: { animate?: boolean; tell?: boolean; range?: string } = {}) => {
    const next = v ? clampView(v) : null;
    setInstant(opts.animate === false);
    setViewRaw(next);
    setRange(opts.range ?? (next ? "" : "all"));
    if (opts.tell !== false) sync({ view: next ? toTimes(next) : null });
  };
  const setHover = (i: number | null, fromKeys = false) => {
    setHoverRaw(i); setKbd(fromKeys); p.onHover?.(i);
    sync({ hover: i == null ? null : T ? T[i] : X[i] });
  };

  // live data: when new points arrive at the right edge, a window that was showing the end keeps following it;
  // a different data set (the first time moved) starts from everything again
  const prev = useRef({ n, first: T?.[0] ?? X[0], last: ext[1] });
  useEffect(() => {
    const was = prev.current;
    const first = T?.[0] ?? X[0];
    prev.current = { n, first, last: ext[1] };
    if (first !== was.first || n < was.n) { setViewRaw(null); setRange("all"); setHoverRaw(null); return; }
    if (view && n > was.n && view[1] >= was.last - 1e-9) { const d = ext[1] - was.last; setViewRaw(clampView([view[0] + d, view[1] + d])); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n, T?.[0], X[0], ext[1]]);

  const target = view ?? ext;
  const [a, b] = useTween(target, 280, instant);
  const i0 = Math.max(0, lowerBound(X, a) - 1), i1 = Math.min(n - 1, lowerBound(X, b));
  const in0 = Math.min(n - 1, lowerBound(X, a - 1e-9)), in1 = Math.max(0, lowerBound(X, b + 1e-9) - 1);     // points inside the window

  // ---- values, possibly indexed to 100 at the window's first point ----
  const shown = series.filter((s) => !hidden.has(key(s)));
  const canIndex = !!p.compare && shown.length >= 1;
  const vals = useMemo(() => series.map((s) => {
    if (!indexed || !canIndex) return s.values;
    let base: number | null = null;
    for (let i = in0; i <= in1 && base == null; i++) { const v = s.values[i]; if (v != null && Number.isFinite(v) && v > 0) base = v; }
    return base == null ? s.values.map(() => null) : s.values.map((v) => (v == null ? null : (v / base!) * 100));
  }), [series, indexed, canIndex, in0, in1]);
  const fmtOf = (s: Series) => (indexed && canIndex ? plainTick : s.format ?? format);

  // ---- y range over what's in view ----
  const yTarget = useMemo(() => {
    let lo = Infinity, hi = -Infinity;
    series.forEach((s, k) => {
      if (hidden.has(key(s))) return;
      for (let i = in0; i <= in1; i++) { const v = vals[k][i]; if (v != null && Number.isFinite(v)) { if (v < lo) lo = v; if (v > hi) hi = v; } }
    });
    if (!indexed) for (const r of refs) if (Number.isFinite(r.v)) { lo = Math.min(lo, r.v); hi = Math.max(hi, r.v); }
    if (indexed) { lo = Math.min(lo, 100); hi = Math.max(hi, 100); }
    const d = niceDomain(lo, hi, H < 200 ? 4 : 5, hasBars || !!p.includeZero);
    return [d.min, d.max];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vals, hidden, in0, in1, refs, indexed, hasBars, p.includeZero, H]);
  const [ymin, ymax] = useTween(yTarget, 280, instant);
  const yTicks = useMemo(() => niceTicks(ymin, ymax, H < 200 ? 4 : 5).filter((t) => t >= ymin && t <= ymax), [ymin, ymax, H]);
  const yFmt = indexed && canIndex ? plainTick : p.axisFormat ?? format;
  const yLabels = yTicks.map(yFmt);

  // ---- layout ----
  const legendOn = p.legend ?? series.filter((s) => s.inLegend !== false).length >= 2;
  const ends = useMemo(() => {
    if (!legendOn || W < 640) return [];
    const out: { label: string; color: string; y: number; v: number }[] = [];
    series.forEach((s, k) => {
      if (hidden.has(key(s)) || s.inLegend === false || s.kind === "bar") return;
      for (let i = in1; i >= in0; i--) { const v = vals[k][i]; if (v != null && Number.isFinite(v)) { out.push({ label: s.label, color: s.color, v, y: 0 }); break; } }
    });
    return out.length >= 2 && out.length <= 4 ? out : [];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [legendOn, W, series, hidden, vals, in0, in1]);
  const endW = ends.length ? Math.min(140, Math.max(...ends.map((e) => textWidth(e.label, 12))) + 22) : 0;
  const padL = Math.max(30, Math.min(96, Math.max(0, ...yLabels.map((l) => textWidth(l))) + 10));
  const padT = PAD.t + (p.split != null && p.splitNotes ? 20 : 0) + (xMarkers.some((m) => m.label) ? 14 : 0);
  const padR = PAD.r + endW;
  const plotW = Math.max(40, W - padL - padR);
  const sx = linear(a, b, padL, padL + plotW);
  const sy = linear(ymin, ymax, H - PAD.b, padT);
  const clip = `ch-clip-${uid.replace(/:/g, "")}`;

  // direct labels: placed at their line ends; if two would touch, none are drawn (the legend carries identity)
  const endLabels = useMemo(() => {
    const ls = ends.map((e) => ({ ...e, y: sy(e.v) })).sort((m, k) => m.y - k.y);
    for (let k = 1; k < ls.length; k++) if (ls[k].y - ls[k - 1].y < 14) return [];
    return ls;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ends, ymin, ymax, H]);

  // ---- x ticks ----
  const xTicks = useMemo((): { px: number; label: string; anchor: "start" | "middle" | "end" }[] => {
    const max = Math.max(2, Math.floor(plotW / 84));
    const out: { px: number; label: string }[] = [];
    const push = (px: number, label: string) => {
      if (px < padL - 1 || px > padL + plotW + 1) return;
      const w = textWidth(label);
      const prevT = out[out.length - 1];
      if (prevT && px - prevT.px < (textWidth(prevT.label) + w) / 2 + 10) return;
      out.push({ px, label });
    };
    if (!n) return [];
    if (T) {
      const ta = T[Math.max(0, Math.min(n - 1, Math.ceil(a)))], tb = T[Math.max(0, Math.min(n - 1, Math.floor(b)))];
      for (const t of timeTicks(ta, tb, max, p.tz)) {
        const i = lowerBound(T, t.t - (intraday ? 0 : DAY / 2));
        if (i < n) push(sx(X[i]), t.label);
      }
    } else if (p.x || p.xFormat) {
      for (const v of niceTicks(a, b, max)) push(sx(v), (p.xFormat ?? plainTick)(v));
    } else {
      const ax = p.axisLabels ?? p.labels ?? [];
      const step = Math.max(1, Math.ceil((in1 - in0 + 1) / max));
      const changes = ax.length === n && new Set(ax.slice(in0, in1 + 1)).size < (in1 - in0 + 1) / 2;   // month labels repeat: tick where they change
      for (let i = in0; i <= in1; i++) {
        if (changes ? i > 0 && ax[i] !== ax[i - 1] : i % step === 0) push(sx(X[i]), ax[i] ?? "");
      }
    }
    // keep the end labels inside the plot
    return out.map((t) => ({ ...t, anchor: (t.px - textWidth(t.label) / 2 < padL ? "start" : t.px + textWidth(t.label) / 2 > padL + plotW ? "end" : "middle") as "start" | "middle" | "end" }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [T, a, b, plotW, padL, n, p.tz, p.x, p.xFormat, p.axisLabels, p.labels, intraday, in0, in1]);

  // vertical markers' labels, the strong ones (the spot) placed first; one that would overlap a placed one is left to
  // the tooltip and the table
  const markerLabels = useMemo(() => {
    const out: { px: number; label: string; anchor: "start" | "middle" | "end"; strong?: boolean; l: number; r: number }[] = [];
    for (const m of [...xMarkers].filter((m) => m.label && m.x >= a && m.x <= b).sort((u, v) => Number(!!v.strong) - Number(!!u.strong))) {
      const px = sx(m.x), w = textWidth(m.label!);
      const anchor = px - w / 2 < padL ? "start" : px + w / 2 > padL + plotW ? "end" : "middle";
      const l = anchor === "start" ? px : anchor === "end" ? px - w : px - w / 2;
      if (out.some((o) => l < o.r + 8 && l + w > o.l - 8)) continue;
      out.push({ px, label: m.label!, anchor, strong: m.strong, l, r: l + w });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [xMarkers, a, b, padL, plotW]);

  // ---- pointer, touch and keys ----
  const pxOf = (clientX: number) => {
    const box = svg.current?.getBoundingClientRect();
    return box ? ((clientX - box.left) / box.width) * W : 0;
  };
  const idxAt = (px: number) => Math.max(in0, Math.min(in1, nearest(X, sx.invert(px))));
  const zoomable = (p.zoom ?? n >= 8) && n >= 3;
  const drag = useRef<{ id: number; px: number; view: View; mode: "select" | "pan" | "touch" } | null>(null);
  const touches = useRef(new Map<number, number>());
  const pinch = useRef<{ d: number; mid: number; view: View } | null>(null);

  const zoomAround = (px: number, factor: number) => {
    const c = sx.invert(px), [va, vb] = view ?? ext;
    setView([c - (c - va) * factor, c + (vb - c) * factor], { animate: false });
  };
  const onDown = (e: RPointerEvent<SVGSVGElement>) => {
    const px = pxOf(e.clientX);
    if (e.pointerType === "touch") {
      touches.current.set(e.pointerId, px);
      if (touches.current.size === 2 && zoomable) {
        const [x1, x2] = [...touches.current.values()];
        pinch.current = { d: Math.max(20, Math.abs(x1 - x2)), mid: (x1 + x2) / 2, view: view ?? ext };
        setHover(null);
      } else if (touches.current.size === 1) setHover(idxAt(px));
      return;
    }
    if (e.button !== 0 || !zoomable) return;
    svg.current?.setPointerCapture(e.pointerId);
    drag.current = { id: e.pointerId, px, view: view ?? ext, mode: e.shiftKey ? "pan" : "select" };
  };
  const onMove = (e: RPointerEvent<SVGSVGElement>) => {
    const px = pxOf(e.clientX);
    if (e.pointerType === "touch") {
      touches.current.set(e.pointerId, px);
      const pc = pinch.current;
      if (pc && touches.current.size >= 2) {
        const [x1, x2] = [...touches.current.values()];
        const d = Math.max(20, Math.abs(x1 - x2)), mid = (x1 + x2) / 2;
        const span = ((pc.view[1] - pc.view[0]) * pc.d) / d;
        const c = pc.view[0] + ((pc.mid - padL) / plotW) * (pc.view[1] - pc.view[0]);
        const na = c - ((mid - padL) / plotW) * span;
        setView([na, na + span], { animate: false });
      } else if (touches.current.size === 1) setHover(idxAt(px));
      return;
    }
    const dg = drag.current;
    if (dg && dg.id === e.pointerId) {
      if (dg.mode === "select") { setSel([dg.px, px]); setHover(idxAt(px)); }
      else { const dx = ((dg.px - px) / plotW) * (dg.view[1] - dg.view[0]); setView([dg.view[0] + dx, dg.view[1] + dx], { animate: false }); }
      return;
    }
    setHover(idxAt(px));
  };
  const onUp = (e: RPointerEvent<SVGSVGElement>) => {
    if (e.pointerType === "touch") {
      touches.current.delete(e.pointerId);
      if (touches.current.size < 2) pinch.current = null;
      return;
    }
    const dg = drag.current;
    drag.current = null;
    if (dg?.mode === "select" && sel && Math.abs(sel[1] - sel[0]) > 8) setView([sx.invert(Math.min(...sel)), sx.invert(Math.max(...sel))]);
    setSel(null);
  };
  // a tap elsewhere on the page puts a touch tooltip away
  useEffect(() => {
    if (hover == null) return;
    const away = (e: PointerEvent) => { if (e.pointerType === "touch" && !wrap.current?.contains(e.target as Node)) setHover(null); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hover != null]);
  // Ctrl/⌘ + wheel (and a trackpad pinch) zooms; a sideways trackpad scroll pans once zoomed. Plain scrolling scrolls the page.
  const wheelState = useRef({ view, ext, sxa: a, sxb: b, padL, plotW, zoomable });
  wheelState.current = { view, ext, sxa: a, sxb: b, padL, plotW, zoomable };
  useEffect(() => {
    const el = svg.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      const s = wheelState.current;
      if (!s.zoomable) return;
      const box = el.getBoundingClientRect();
      const px = ((e.clientX - box.left) / box.width) * el.viewBox.baseVal.width;
      const [va, vb] = s.view ?? s.ext;
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault();
        const c = va + ((px - s.padL) / s.plotW) * (vb - va), f = Math.exp(e.deltaY * 0.004);
        setView([c - (c - va) * f, c + (vb - c) * f], { animate: false });
      } else if (s.view && Math.abs(e.deltaX) > Math.abs(e.deltaY)) {
        e.preventDefault();
        const dx = (e.deltaX / s.plotW) * (vb - va);
        setView([va + dx, vb + dx], { animate: false });
      }
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [n]);
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!n || e.target !== e.currentTarget) return;
    const cur = hover ?? in1;
    const [va, vb] = view ?? ext, span = vb - va;
    if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      const dir = e.key === "ArrowLeft" ? -1 : 1;
      if (e.shiftKey && zoomable) setView([va + dir * span * 0.2, vb + dir * span * 0.2]);
      else {
        const i = Math.max(0, Math.min(n - 1, cur + dir));
        if (X[i] < va || X[i] > vb) setView([va + (X[i] - (dir < 0 ? va : vb)), vb + (X[i] - (dir < 0 ? va : vb))]);
        setHover(i, true);
      }
    } else if (e.key === "Home" || e.key === "End") setHover(e.key === "Home" ? in0 : in1, true);
    else if ((e.key === "+" || e.key === "=") && zoomable) zoomAround(sx(X[cur]), 0.7);
    else if (e.key === "-" && zoomable) zoomAround(sx(X[cur]), 1 / 0.7);
    else if (e.key === "Escape") { if (view) setView(null); setHover(null); }
    else return;
    e.preventDefault();
  };

  // ---- ranges ----
  const presets = useMemo(() => {
    if (!T || n < 2 || p.ranges === false) return [];
    const spanDays = (T[n - 1] - T[0]) / DAY;
    if (p.ranges !== true && spanDays < 45) return [];
    return RANGE_PRESETS.filter((r) => r.days == null || r.days < spanDays * 0.95);
  }, [T, n, p.ranges]);
  const pickRange = (id: string, days: number | null) => {
    if (!T) return;
    if (days == null) { setView(null); return; }
    const from = lowerBound(T, T[n - 1] - days * DAY);
    setView([X[Math.min(n - 1, from)], ext[1]], { range: id });
  };

  if (!n || !series.some((s) => s.values.some((v) => v != null && Number.isFinite(v)))) {
    return <div ref={wrap}><ChartEmpty height={height} label={ariaLabel}>Nothing to draw yet.</ChartEmpty></div>;
  }

  // ---- drawing ----
  const at = hover ?? remote;
  const hx = at != null ? sx(X[at]) : 0;
  const zero = sy(Math.max(ymin, Math.min(ymax, 0)));
  const slot = (plotW / Math.max(1e-9, b - a)) * (n > 1 ? (X[n - 1] - X[0]) / (n - 1) : 1);
  const bw = Math.max(1, Math.min(24, slot >= 4 ? slot - 2 : slot));
  const barPath = (i: number, v: number) => {
    const x0 = sx(X[i]) - bw / 2, x1 = x0 + bw, y = sy(v), h = Math.abs(y - zero);
    if (h < 0.5) return "";
    const r = bw >= 8 ? Math.min(4, h, bw / 2) : 0, up = v >= 0;
    return up
      ? `M${x0},${zero}V${y + r}Q${x0},${y} ${x0 + r},${y}H${x1 - r}Q${x1},${y} ${x1},${y + r}V${zero}Z`
      : `M${x0},${zero}V${y - r}Q${x0},${y} ${x0 + r},${y}H${x1 - r}Q${x1},${y} ${x1},${y - r}V${zero}Z`;
  };
  const bars = (k: number) => {
    const v = vals[k], out: ReactNode[] = [];
    if (slot >= 1) {
      for (let i = i0; i <= i1; i++) { const y = v[i]; if (y != null && Number.isFinite(y) && y !== 0) out.push(<path key={i} d={barPath(i, y)} fill={series[k].color} opacity={at == null || at === i ? 1 : 0.5} />); }
      return out;
    }
    // more days than pixels: one hairline column per pixel, at that pixel's largest value
    let col = -1, best: number | null = null;
    const flush = () => { if (best != null && col >= 0) out.push(<line key={col} x1={col + 0.5} x2={col + 0.5} y1={zero} y2={sy(best)} stroke={series[k].color} strokeWidth={1} />); };
    for (let i = i0; i <= i1; i++) {
      const y = v[i], c = Math.floor(sx(X[i]));
      if (c !== col) { flush(); col = c; best = null; }
      if (y != null && Number.isFinite(y) && (best == null || Math.abs(y) > Math.abs(best))) best = y;
    }
    flush();
    return out;
  };
  const areaPath = (k: number, base: number) => {
    const line = linePath(X, vals[k], i0, i1, sx, sy);
    if (!line) return "";
    // close each run of points down to the base
    return line.split("M").filter(Boolean).map((seg) => {
      const pts = seg.split("L");
      const [fx] = pts[0].split(","), [lx] = pts[pts.length - 1].split(",");
      return `M${fx},${sy(base)}L${seg}L${lx},${sy(base)}Z`;
    }).join("");
  };
  const tipLeft = (hx / W) * 100;
  const flip = hx > padL + plotW * 0.6;
  const heading = (i: number) => T ? tipTime(T[i], intraday, p.tz) : p.labels?.[i] ?? (p.xFormat ? p.xFormat(X[i]) : p.axisLabels?.[i] ?? String(i + 1));
  const toolbar = legendOn || presets.length > 0 || view || canIndex && p.compare || p.table !== false;

  return (
    <div ref={wrap} className="ch" data-testid={p.testId}>
      {toolbar && (
        <div className="ch-bar">
          {legendOn ? <LegendToggles items={series.filter((s) => s.inLegend !== false).map((s) => ({ id: key(s), label: s.label, color: s.color, dash: !!s.dash, bar: s.kind === "bar", on: !hidden.has(key(s)) }))}
            onToggle={(id) => setHidden((h) => {
              const next = new Set(h);
              if (next.has(id)) next.delete(id);
              else if (series.filter((s) => !next.has(key(s))).length > 1) next.add(id);        // the last one stays on
              setInstant(false);
              return next;
            })} /> : <span />}
          <div className="ch-tools">
            {presets.length > 0 && (
              <div className="ch-seg" role="group" aria-label="Chart range">
                {presets.map((r) => <button key={r.id} type="button" aria-pressed={range === r.id} onClick={() => pickRange(r.id, r.days)}>{r.label}</button>)}
              </div>
            )}
            {canIndex && p.compare && <button type="button" className="ch-btn" aria-pressed={indexed} onClick={() => { setInstant(false); setIndexed((v) => !v); }}
              title="Both series start at 100 at the left edge of the window, so their moves compare directly">Index to 100</button>}
            {view && <button type="button" className="ch-btn" onClick={() => setView(null)}>Reset zoom</button>}
            {!view && zoomable && <span className="ch-hint" aria-hidden="true" />}
            {p.table !== false && <button type="button" className="ch-btn" aria-pressed={showTable} aria-label={`${showTable ? "Hide" : "Show"} the numbers as a table`} onClick={() => setShowTable((v) => !v)}>Table</button>}
          </div>
        </div>
      )}
      <div className="ch-plot" tabIndex={0} role="group" aria-label={`${ariaLabel}. Arrow keys move along the chart${zoomable ? ", plus and minus zoom, Escape resets" : ""}.`}
        onKeyDown={onKey} onBlur={() => kbd && setHover(null)}>
        <svg ref={svg} className="ch-svg" viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={ariaLabel}
          onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
          onPointerLeave={(e) => { if (e.pointerType !== "touch" && !drag.current) setHover(null); }}
          onDoubleClick={() => view && setView(null)}
          style={{ touchAction: "pan-y", cursor: zoomable ? (drag.current?.mode === "pan" ? "grabbing" : "crosshair") : undefined }}>
          <defs>
            <clipPath id={clip}><rect x={padL} y={0} width={plotW} height={H - PAD.b + 1} /></clipPath>
            {series.map((s, k) => s.area && (s.area.pos || s.area.neg) ? (
              <g key={k}>
                <clipPath id={`${clip}-up${k}`}><rect x={padL} y={0} width={plotW} height={Math.max(0, sy(s.area.base ?? 0))} /></clipPath>
                <clipPath id={`${clip}-dn${k}`}><rect x={padL} y={sy(s.area.base ?? 0)} width={plotW} height={Math.max(0, H - sy(s.area.base ?? 0))} /></clipPath>
              </g>
            ) : null)}
          </defs>
          {/* grid and y axis */}
          {yTicks.map((t, k) => (
            <g key={k}>
              <line x1={padL} x2={padL + plotW} y1={sy(t)} y2={sy(t)} stroke="var(--line)" strokeWidth={1} shapeRendering="crispEdges" />
              <text className="ch-tick" x={padL - 8} y={sy(t) + 4} textAnchor="end">{yLabels[k]}</text>
            </g>
          ))}
          <g clipPath={`url(#${clip})`}>
            {p.split != null && p.split > 0 && p.split < n && (
              <>
                <rect x={sx(X[p.split])} y={padT - (p.splitNotes ? 20 : 0)} width={Math.max(0, padL + plotW - sx(X[p.split]))} height={H - PAD.b - padT + (p.splitNotes ? 20 : 0)} fill="var(--orange-soft)" opacity={0.6} />
                <line x1={sx(X[p.split])} x2={sx(X[p.split])} y1={padT - (p.splitNotes ? 20 : 0)} y2={H - PAD.b} stroke="var(--ink)" strokeDasharray="3 4" />
              </>
            )}
            {!indexed && refs.map((r, k) => (
              <line key={`r${k}`} x1={padL} x2={padL + plotW} y1={sy(r.v)} y2={sy(r.v)} stroke={r.color ?? (r.strong ? "var(--muted)" : "var(--dash)")}
                strokeWidth={r.strong ? 1.25 : 1} strokeDasharray={r.dash ? "5 4" : undefined} shapeRendering="crispEdges" />
            ))}
            {indexed && <line x1={padL} x2={padL + plotW} y1={sy(100)} y2={sy(100)} stroke="var(--muted)" strokeWidth={1.25} />}
            {series.map((s, k) => {
              if (hidden.has(key(s)) || !s.area || s.kind === "bar") return null;
              const base = indexed ? 100 : s.area.base ?? 0;
              const d = areaPath(k, base);
              return s.area.pos || s.area.neg ? (
                <g key={`a${k}`}>
                  {s.area.pos && <path d={d} fill={s.area.pos} opacity={0.14} clipPath={`url(#${clip}-up${k})`} />}
                  {s.area.neg && <path d={d} fill={s.area.neg} opacity={0.14} clipPath={`url(#${clip}-dn${k})`} />}
                </g>
              ) : <path key={`a${k}`} d={d} fill={s.area.color ?? s.color} opacity={0.1} />;
            })}
            {series.map((s, k) => !hidden.has(key(s)) && s.kind === "bar" ? <g key={`b${k}`}>{bars(k)}</g> : null)}
            {series.map((s, k) => !hidden.has(key(s)) && s.kind !== "bar" ? (
              <path key={`l${k}`} className="ch-line" d={linePath(X, vals[k], i0, i1, sx, sy)} fill="none" stroke={s.color} strokeWidth={s.width ?? 2}
                strokeDasharray={s.dash} strokeLinejoin="round" strokeLinecap="round" />
            ) : null)}
            {!indexed && points.map((m, k) => {
              const v = vals[m.series ?? 0]?.[m.i];
              if (v == null || m.i < i0 || m.i > i1) return null;
              const cx = sx(X[m.i]), cy = sy(v);
              return m.kind === "buy" ? <path key={k} d={`M${cx},${cy + 7} l6,10 h-12z`} fill={m.color ?? "var(--blue)"} />
                : m.kind === "sell" ? <path key={k} d={`M${cx},${cy - 7} l6,-10 h-12z`} fill={m.color ?? "var(--orange)"} />
                : <circle key={k} cx={cx} cy={cy} r={4} fill={m.color ?? "var(--ink)"} stroke="var(--card)" strokeWidth={2} />;
            })}
            {xMarkers.map((m, k) => m.x >= a && m.x <= b && (
              <line key={`m${k}`} x1={sx(m.x)} x2={sx(m.x)} y1={padT - (m.label ? 4 : 0)} y2={H - PAD.b} stroke={m.color ?? "var(--muted)"}
                strokeWidth={m.strong ? 1.5 : 1} strokeDasharray={m.dash ? "4 4" : undefined} />
            ))}
          </g>
          {markerLabels.map((m, k) => <text key={`ml${k}`} className={`ch-tick${m.strong ? " strong" : ""}`} x={m.px} y={padT - 8} textAnchor={m.anchor}>{m.label}</text>)}
          {p.split != null && p.splitNotes && p.split > 0 && p.split < n && sx(X[p.split]) > padL && sx(X[p.split]) < padL + plotW && (
            <>
              <text className="ch-note" x={sx(X[p.split]) - 8} y={padT - 6} textAnchor="end">{W < 560 ? "" : p.splitNotes[0]}</text>
              <text className="ch-note unseen" x={Math.min(sx(X[p.split]) + 8, padL + plotW - 4)} y={padT - 6} textAnchor={sx(X[p.split]) > padL + plotW * 0.75 ? "end" : "start"}>{p.splitNotes[1]}</text>
            </>
          )}
          {/* x axis */}
          {xTicks.map((t, k) => <text key={k} className="ch-tick" x={t.px} y={H - 6} textAnchor={t.anchor}>{t.label}</text>)}
          {/* direct labels at the line ends */}
          {endLabels.map((e) => (
            <g key={e.label}>
              <line x1={padL + plotW + 6} x2={padL + plotW + 14} y1={e.y} y2={e.y} stroke={e.color} strokeWidth={2} strokeLinecap="round" />
              <text className="ch-end" x={padL + plotW + 18} y={e.y + 4}>{e.label}</text>
            </g>
          ))}
          {/* crosshair */}
          {at != null && at >= i0 && at <= i1 && (
            <g pointerEvents="none">
              {!hasBars && <line x1={hx} x2={hx} y1={padT} y2={H - PAD.b} stroke="var(--ink)" strokeWidth={1} opacity={0.35} />}
              {hasBars && <rect x={hx - Math.max(bw, 3) / 2 - 2} y={padT} width={Math.max(bw, 3) + 4} height={H - PAD.b - padT} fill="var(--ink)" opacity={0.06} />}
              {series.map((s, k) => {
                const v = vals[k][at];
                return !hidden.has(key(s)) && s.kind !== "bar" && v != null && Number.isFinite(v) && v >= ymin && v <= ymax
                  ? <circle key={k} cx={hx} cy={sy(v)} r={4} fill={s.color} stroke="var(--card)" strokeWidth={2} /> : null;
              })}
            </g>
          )}
          {sel && <rect x={Math.min(...sel)} y={padT} width={Math.abs(sel[1] - sel[0])} height={H - PAD.b - padT} fill="var(--blue)" opacity={0.12} pointerEvents="none" />}
        </svg>
        {at != null && at >= i0 && at <= i1 && (
          <ChartTip left={tipLeft} flip={flip} top={padT} live={kbd} heading={heading(at)}>
            {series.map((s, k) => {
              const v = vals[k][at];
              if (hidden.has(key(s)) || s.inTooltip === false || v == null || !Number.isFinite(v)) return null;
              const raw = s.values[at];
              return <TipRow key={k} color={s.color} dash={!!s.dash} bar={s.kind === "bar"} value={fmtOf(s)(v)} label={s.label}
                note={indexed && canIndex && raw != null ? (s.format ?? format)(raw) : undefined} />;
            })}
            {p.tipExtra?.(at)}
          </ChartTip>
        )}
      </div>
      {showTable && (
        <div className="table-wrap ch-table" data-testid="chart-table">
          <table>
            <caption className="sr-only">{ariaLabel}</caption>
            <thead><tr><th>{p.tableX ?? (T ? "Date" : "At")}</th>{shown.map((s) => <th key={key(s)} className="num">{s.label}</th>)}</tr></thead>
            <tbody>
              {Array.from({ length: Math.min(400, in1 - in0 + 1) }, (_, k) => in1 - k).map((i) => (
                <tr key={i}><td>{heading(i)}</td>{shown.map((s) => { const v = s.values[i]; return <td key={key(s)} className="num">{v == null || !Number.isFinite(v) ? "–" : (s.format ?? format)(v)}</td>; })}</tr>
              ))}
            </tbody>
          </table>
          {in1 - in0 + 1 > 400 && <p className="tiny muted">The latest 400 of {in1 - in0 + 1} points in view. Zoom in to see the rest.</p>}
        </div>
      )}
    </div>
  );
}
