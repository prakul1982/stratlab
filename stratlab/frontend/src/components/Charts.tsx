import { useState } from "react";
import { XYChart, type XYChartProps } from "./chart/XYChart";
import { ChartTip } from "./chart/parts";
import { fall, signCls } from "../lib/format";

/* The app's charts. Everything that plots values over time or across prices is drawn by chart/XYChart (crosshair and
 * tooltip, zoom and pan, ranges, legends, linked charts, table view); this file keeps the older entry points and the
 * small one-off figures. Colours come from CSS variables, so both themes work. */

export { XYChart } from "./chart/XYChart";
export type { Series, RefLine, XMarker, PointMark, XYChartProps } from "./chart/XYChart";
export { PayoffChart } from "./chart/PayoffChart";
export type { PayoffCurve, PayoffMarker } from "./chart/PayoffChart";
export { ChartEmpty, Legend } from "./chart/parts";

export interface Line {
  values: (number | null)[];
  color: string;          // a CSS color or var(--x)
  width?: number;
  dash?: string;
  label: string;
}
export interface Marker { i: number; side: "buy" | "sell" }

interface LineChartProps extends Partial<Omit<XYChartProps, "series" | "format" | "ariaLabel" | "labels">> {
  lines: Line[];
  labels: string[];                 // tooltip label per point
  height?: number;
  format: (v: number) => string;
  markers?: Marker[];
  baseline?: number | null;
  ariaLabel: string;
  levels?: { v: number; color: string; label: string }[];
}

/** The older line-chart entry point: lines, a label per point and optional baseline, levels and buy/sell marks, drawn by
 * XYChart. Pages that render their own legend keep it (legend off by default here). */
export function LineChart({ lines, baseline, levels = [], markers = [], legend = false, refs = [], ...rest }: LineChartProps) {
  return (
    <XYChart {...rest} legend={legend}
      series={lines.map((l) => ({ label: l.label, values: l.values, color: l.color, width: l.width ?? 2, dash: l.dash }))}
      refs={[...(baseline != null ? [{ v: baseline, strong: baseline === 0 }] : []), ...levels.map((lv) => ({ v: lv.v, color: lv.color, dash: true, label: lv.label })), ...refs]}
      points={markers.map((m) => ({ i: m.i, kind: m.side }))} />
  );
}

/* 5×5 grid of returns for nearby indicator settings; yours outlined. Each cell shows its return on hover or focus. */
export function Heatmap({ grid, yours, label }: { grid: number[][]; yours: [number, number]; label: string }) {
  const cols = grid[0]?.length ?? 0;
  const [on, setOn] = useState<[number, number] | null>(null);
  const fmt = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`;
  const v = on ? grid[on[0]]?.[on[1]] : null;
  return (
    <div style={{ position: "relative" }} onPointerLeave={() => setOn(null)}>
      <div role="grid" aria-label={label} style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`, gap: 2 }}>
        {grid.flatMap((row, r) => row.map((val, c) => {
          const a = Math.min(1, 0.25 + Math.abs(val) / 20).toFixed(2);
          const mine = r === yours[0] && c === yours[1];
          return (
            <span key={`${r}-${c}`} role="gridcell" tabIndex={0} aria-label={`${fmt(val)}${mine ? ", your settings" : ""}`}
              title={`${fmt(val)}${val > 0 ? ", made money" : val < 0 ? ", lost money" : ""}${mine ? " · your settings" : ""}`}
              onPointerEnter={() => setOn([r, c])} onFocus={() => setOn([r, c])} onBlur={() => setOn(null)} style={{
                height: 28, borderRadius: 4, cursor: "default",
                background: val > 0 ? `color-mix(in srgb, var(--series-1) ${+a * 100}%, transparent)` : `color-mix(in srgb, var(--series-2) ${+a * 100}%, transparent)`,
                outline: mine ? "2.5px solid var(--ink)" : on && on[0] === r && on[1] === c ? "1.5px solid var(--ink-2)" : undefined, outlineOffset: 1,
              }} />
          );
        }))}
      </div>
      <div className="ch-legend static" aria-label="Colour key">
        <span><i className="ch-key-bar" style={{ background: "var(--series-1)" }} />Made money</span>
        <span><i className="ch-key-bar" style={{ background: "var(--series-2)" }} />Lost money</span>
        <span><i className="ch-key-bar" style={{ outline: "2px solid var(--ink)", outlineOffset: 1 }} />Your settings</span>
        <span className="muted">A stronger colour is a bigger move. Hover or tap a square for its return.</span>
      </div>
      {on && v != null && (
        <ChartTip left={((on[1] + 0.5) / cols) * 100} top={(on[0] + 1) * 30} flip={on[1] >= cols / 2} heading={on[0] === yours[0] && on[1] === yours[1] ? "Your settings" : "Nearby setting"}>
          <div className="ch-tip-row"><b className={signCls(v, fmt(v))}>{fmt(v)}</b><span className="muted">return</span></div>
        </ChartTip>
      )}
    </div>
  );
}

/* Where your drawdown sits among 1,000 reshuffles. */

export function DrawdownBand({ yours, p95, worst }: { yours: number; p95: number; worst: number }) {
  const max = Math.max(worst, yours, 1) * 1.05;
  const X = (v: number) => 8 + (v / max) * 264;
  return (
    <svg className="ch-svg" viewBox="0 0 280 64" width="100%" role="img" aria-label={`Your worst fall ${fall(yours)}, 95% of reshuffles no deeper than ${fall(p95)}, deepest ${fall(worst)}`}>
      <line x1={8} y1={30} x2={272} y2={30} stroke="var(--line)" strokeWidth={10} strokeLinecap="round" />
      <line x1={X(yours)} y1={30} x2={X(p95)} y2={30} stroke="var(--orange-soft)" strokeWidth={10} />
      <line x1={X(yours)} y1={16} x2={X(yours)} y2={44} stroke="var(--ink)" strokeWidth={2} />
      <circle cx={X(worst)} cy={30} r={5} fill="var(--orange)" stroke="var(--card)" strokeWidth={2} />
      <text className="ch-tick strong" x={Math.max(30, X(yours))} y={60} textAnchor="middle">yours {fall(yours)}</text>
      <text className="ch-tick strong" x={272} y={12} textAnchor="end">worst {fall(worst)}</text>
      <text className="ch-tick" x={8} y={12}>0%</text>
    </svg>
  );
}

/* Built-on vs unseen returns as two bars. */
export function SplitBars({ built, unseen, builtLabel, unseenLabel }: { built: number; unseen: number; builtLabel: string; unseenLabel: string }) {
  const max = Math.max(Math.abs(built), Math.abs(unseen), 1);
  const bar = (v: number) => (
    <div className="row" style={{ gap: 8 }}>
      <span style={{ height: 14, width: `${Math.max(4, (Math.abs(v) / max) * 150)}px`, borderRadius: "0 4px 4px 0", background: v >= 0 ? "var(--series-1)" : "var(--series-2)" }} />
      <span className={`ch-num ${signCls(v, v.toFixed(1))}`} style={{ fontSize: 14, fontWeight: 600 }}>{v > 0 ? "+" : v < 0 ? "−" : ""}{Math.abs(v).toFixed(1)}%</span>
    </div>
  );
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="stack" style={{ gap: 5 }}><span className="small muted">{builtLabel}</span>{bar(built)}</div>
      <div className="stack" style={{ gap: 5 }}><span className="small muted">{unseenLabel}</span>{bar(unseen)}</div>
    </div>
  );
}

/* Two counts a day on one scale: the first drawn up from zero, the second down (new highs over new lows, stocks up 4%
 * over those down 4%). Thin columns with a per-day tooltip; zoom, ranges and linked crosshairs come from XYChart. */
export function PairBars({ up, down, labels, times, upLabel, downLabel, upName, downName, upColor, downColor, ariaLabel, height = 200, format = (v) => String(v), sync, ranges }: {
  up: number[]; down: number[]; labels: string[]; times?: string[]; upLabel: string; downLabel: string; upName?: string; downName?: string; upColor: string; downColor: string;
  ariaLabel: string; height?: number; format?: (v: number) => string; sync?: string; ranges?: boolean;
}) {
  const abs = (v: number) => format(Math.abs(v));
  return (
    <XYChart ariaLabel={ariaLabel} height={height} times={times} labels={times ? undefined : labels} axisLabels={labels} sync={sync} ranges={ranges}
      format={abs} axisFormat={abs} refs={[{ v: 0, strong: true }]}
      series={[
        { id: "up", label: upName ?? upLabel, tipLabel: upLabel, values: up, color: upColor, kind: "bar" },
        { id: "down", label: downName ?? downLabel, tipLabel: downLabel, values: down.map((v) => (v == null ? v : -v)), color: downColor, kind: "bar" },
      ]} />
  );
}

