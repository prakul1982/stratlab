import { useLayoutEffect, useRef, type ReactNode } from "react";
import { plotHeight, useWidth } from "./core";

/* The small pieces every chart shares: the tooltip, its rows, the legend (static or switchable) and the empty or
 * loading box that holds a chart's place at its own height, so nothing jumps when the data arrives. */

/** A box the height of the chart it stands in for: a message, or a shimmer while loading. */
export function ChartEmpty({ height = 240, loading, label, children }: { height?: number; loading?: boolean; label?: string; children?: ReactNode }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  return (
    <div ref={ref} className={`ch-empty${loading ? " chart-skel" : ""}`} style={{ height: plotHeight(height, w) }} role={loading ? "status" : undefined}
      aria-label={loading ? `Loading ${label ?? "the chart"}` : undefined}>
      {!loading && <span className="small muted">{children}</span>}
    </div>
  );
}

/** The tooltip: a heading (the date or x) and one row per series. `left` is the crosshair's place as a percentage of the
 * chart's width; the tooltip sits beside it (to the left when `flip`), moving to the other side or against the edge
 * when it would run off the chart, so it never makes a phone scroll sideways. */
export function ChartTip({ left, top = 0, flip, heading, live, children }: { left: number; top?: number; flip: boolean; heading: ReactNode; live?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current, box = el?.offsetParent as HTMLElement | null;
    if (!el || !box) return;
    const pw = box.clientWidth, w = el.offsetWidth, x = (left / 100) * pw;
    const right = x + 12, leftSide = x - 12 - w;
    let at = flip ? leftSide : right;
    if (at < 0) at = right + w <= pw ? right : 0;
    if (at + w > pw) at = leftSide >= 0 ? leftSide : Math.max(0, pw - w);
    el.style.left = `${Math.round(at)}px`;
    el.style.visibility = "visible";
  });
  return (
    <div ref={ref} className="ch-tip chart-tip" role={live ? "status" : undefined} aria-live={live ? "polite" : undefined}
      style={{ left: `${left}%`, top, visibility: "hidden" }}>
      <div className="ch-tip-h">{heading}</div>
      {children}
    </div>
  );
}

/** One tooltip row: a short line key in the series colour, the value (strong), then the series name. */
export function TipRow({ color, value, label, dash, bar, note, tone }: { color: string; value: string; label: string; dash?: boolean; bar?: boolean; note?: string; tone?: string }) {
  return (
    <div className="ch-tip-row">
      <Key color={color} dash={dash} bar={bar} />
      <b className={tone || undefined}>{value}</b><span className="muted">{label}{note ? ` (${note})` : ""}</span>
    </div>
  );
}

/** The series key: a short line (lines) or a small square (columns, areas). */
export function Key({ color, dash, bar }: { color: string; dash?: boolean; bar?: boolean }) {
  return bar
    ? <span className="ch-key-bar" style={{ background: color }} aria-hidden="true" />
    : <span className="ch-key-line" style={{ borderTopColor: color, borderTopStyle: dash ? "dashed" : "solid" }} aria-hidden="true" />;
}

/** A legend whose items switch series on and off. */
export function LegendToggles({ items, onToggle }: { items: { id: string; label: string; color: string; dash?: boolean; bar?: boolean; on: boolean }[]; onToggle: (id: string) => void }) {
  return (
    <div className="ch-legend" role="group" aria-label="Series shown">
      {items.map((i) => (
        <button key={i.id} type="button" aria-pressed={i.on} onClick={() => onToggle(i.id)} aria-label={`Series: ${i.label}`} title={i.on ? `Hide ${i.label}` : `Show ${i.label}`}>
          <Key color={i.color} dash={i.dash} bar={i.bar} />{i.label}
        </button>
      ))}
    </div>
  );
}

/** A legend that only names the series (for charts with no switching). */
export function Legend({ items }: { items: { label: string; color: string; dash?: boolean; bar?: boolean }[] }) {
  return (
    <div className="ch-legend static">
      {items.map((i) => <span key={i.label}><Key color={i.color} dash={i.dash} bar={i.bar} />{i.label}</span>)}
    </div>
  );
}
