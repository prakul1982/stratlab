import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { watchSize } from "../../lib/resize";

/* The chart system's plumbing: the drawn width, a linear scale, thinning thousands of points down to what the screen
 * can show, smooth moves that respect "reduce motion", and the little message bus that keeps stacked charts' crosshairs
 * and zoom together. No drawing here: XYChart and friends use these. */

/** The element's width in CSS pixels, kept up to date as it resizes (charts draw at their real width, so text stays
 * readable on phones). */
export function useWidth<T extends HTMLElement>(initial = 720, min = 260) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(initial);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setW(Math.max(min, Math.round(el.getBoundingClientRect().width || initial)));
    // a frame later: no "ResizeObserver loop" page error (R7T-014)
    return watchSize(el, (e) => { if (e) setW(Math.max(min, Math.round(e.contentRect.width))); });
  }, [initial, min]);
  return [ref, w] as const;
}

/** The plot's height for a width: a little shorter on a phone, never squashed. */
export const plotHeight = (height: number, width: number) => (width < 560 ? Math.max(150, Math.round(height * 0.8)) : height);

/** A linear map from [d0, d1] onto [r0, r1]. */
export function linear(d0: number, d1: number, r0: number, r1: number) {
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  const f = (v: number) => r0 + (v - d0) * k;
  f.invert = (p: number) => (k === 0 ? d0 : d0 + (p - r0) / k);
  return f;
}

/** The first index whose x is at least v (xs ascending). */
export function lowerBound(xs: ArrayLike<number>, v: number): number {
  let lo = 0, hi = xs.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (xs[m] < v) lo = m + 1; else hi = m; }
  return lo;
}

/** The index whose x is nearest v. */
export function nearest(xs: ArrayLike<number>, v: number): number {
  const n = xs.length;
  if (!n) return -1;
  const i = lowerBound(xs, v);
  if (i <= 0) return 0;
  if (i >= n) return n - 1;
  return v - xs[i - 1] <= xs[i] - v ? i - 1 : i;
}

/** Points of one series between indices i0..i1 as an SVG path, thinned to at most a few points per pixel column:
 * each column keeps its first, lowest, highest and last value, so peaks and troughs survive. Gaps (null) break the line. */
export function linePath(xs: ArrayLike<number>, vals: (number | null)[], i0: number, i1: number,
  sx: (v: number) => number, sy: (v: number) => number): string {
  let d = "", pen = false;
  const dense = i1 - i0 > 0 && Math.abs(sx(xs[i1]) - sx(xs[i0])) * 2 < i1 - i0;
  const put = (x: number, y: number) => { d += `${pen ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`; pen = true; };
  if (!dense) {
    for (let i = i0; i <= i1; i++) {
      const v = vals[i];
      if (v == null || !Number.isFinite(v)) { pen = false; continue; }
      put(sx(xs[i]), sy(v));
    }
    return d;
  }
  let col = NaN, first = -1, lo = -1, hi = -1, last = -1;
  const flush = () => {
    if (first < 0) return;
    const pts = [...new Set([first, lo, hi, last])].sort((a, b) => a - b);
    for (const i of pts) put(sx(xs[i]), sy(vals[i] as number));
    first = lo = hi = last = -1;
  };
  for (let i = i0; i <= i1; i++) {
    const v = vals[i];
    if (v == null || !Number.isFinite(v)) { flush(); pen = false; col = NaN; continue; }
    const c = Math.floor(sx(xs[i]));
    if (c !== col) { flush(); col = c; }
    if (first < 0) { first = lo = hi = i; }
    if (v < (vals[lo] as number)) lo = i;
    if (v > (vals[hi] as number)) hi = i;
    last = i;
  }
  flush();
  return d;
}

/** True when the reader asked the system for less motion. */
export function reducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

/** Numbers that glide to their new values over `ms` (ease-out), or jump when motion is reduced or `instant` is set.
 * Used for the visible window and the y range, so a range change, a toggled series or a live tick moves smoothly. */
export function useTween(target: number[], ms = 260, instant = false): number[] {
  const [cur, setCur] = useState(target);
  const from = useRef(target);
  const shown = useRef(target);
  const key = target.map((v) => (Number.isFinite(v) ? v.toPrecision(10) : "x")).join(",");
  useEffect(() => {
    if (instant || reducedMotion() || shown.current.length !== target.length || target.some((v) => !Number.isFinite(v))) {
      shown.current = target; setCur(target); return;
    }
    from.current = shown.current;
    const t0 = performance.now();
    let raf = 0;
    const step = (now: number) => {
      const k = Math.min(1, (now - t0) / ms), e = 1 - (1 - k) ** 3;
      const v = target.map((t, i) => from.current[i] + (t - from.current[i]) * e);
      shown.current = v; setCur(v);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, instant]);
  return cur;
}

/* ---------- linked charts ---------- */
/** What one chart in a group tells the others: where the pointer is (a time in ms, or an x value) and the window shown. */
export type SyncMsg = { from: string; hover?: number | null; view?: [number, number] | null };
const groups = new Map<string, Set<(m: SyncMsg) => void>>();

/** Join a group of linked charts: returns a function that tells the others; `on` hears them (never its own messages). */
export function useSync(group: string | undefined, id: string, on: (m: SyncMsg) => void) {
  const cb = useRef(on);
  cb.current = on;
  useEffect(() => {
    if (!group) return;
    const fn = (m: SyncMsg) => { if (m.from !== id) cb.current(m); };
    let set = groups.get(group);
    if (!set) groups.set(group, set = new Set());
    set.add(fn);
    return () => { set!.delete(fn); if (!set!.size) groups.delete(group); };
  }, [group, id]);
  return (m: Omit<SyncMsg, "from">) => { if (group) groups.get(group)?.forEach((f) => f({ ...m, from: id })); };
}

/** A rough width of a label in pixels at the axis font (11px sans, tabular figures), for spacing ticks. */
export const textWidth = (s: string, size = 11) => s.length * size * 0.58 + 2;
