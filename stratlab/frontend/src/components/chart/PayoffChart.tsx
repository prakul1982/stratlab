import type { ReactNode } from "react";
import { XYChart, type Series, type XMarker } from "./XYChart";

/* Profit or loss across underlying prices: the options builder's payoff chart. One or more curves over the same prices
 * (at expiry, "today" from the pricing model, and either after charges), the profit side washed blue and the loss side
 * orange under the first curve, a zero line, and vertical markers for the spot, the breakevens and anything else a
 * caller adds. Hover, zoom on a price range, a legend that switches curves, and the table all come from XYChart. */

export interface PayoffCurve {
  id?: string;
  label: string;
  tipLabel?: string;                // the tooltip's words for it, when they differ from the legend's ("today, model estimate")
  values: (number | null)[];        // P&L at each price in `xs`
  color?: string;                   // series colours in order otherwise
  dash?: string;
  width?: number;
  shade?: boolean;                  // profit/loss wash (the first curve has it unless set false)
  hidden?: boolean;                 // starts switched off in the legend
}
export interface PayoffMarker { x: number; label: string; kind?: "spot" | "breakeven" | "strike" | "other"; color?: string; side?: "left" | "right" }

const COLORS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];

export function PayoffChart({ xs, curves, markers = [], format, axisFormat, xFormat, ariaLabel, height = 220, testId, tipExtra }: {
  xs: number[]; curves: PayoffCurve[]; markers?: PayoffMarker[];
  format: (v: number) => string; axisFormat?: (v: number) => string; xFormat: (x: number) => string; ariaLabel: string; height?: number; testId?: string;
  tipExtra?: (i: number) => ReactNode;
}) {
  const series: Series[] = curves.map((c, k) => ({
    id: c.id, label: c.label, tipLabel: c.tipLabel, values: c.values, color: c.color ?? COLORS[k % COLORS.length], dash: c.dash, width: c.width ?? 2,
    hidden: c.hidden, area: (c.shade ?? k === 0) ? { base: 0, pos: "var(--series-1)", neg: "var(--series-2)" } : undefined,
  }));
  const xMarkers: XMarker[] = markers.map((m) => ({
    x: m.x, label: m.label, color: m.color ?? (m.kind === "spot" ? "var(--ink)" : "var(--muted)"),
    dash: m.kind !== "spot", strong: m.kind === "spot", side: m.side,
  }));
  return (
    <XYChart series={series} x={xs} xFormat={xFormat} labels={xs.map((x) => `At ${xFormat(x)}`)} tableX="Underlying at"
      format={format} axisFormat={axisFormat} height={height} refs={[{ v: 0, strong: true }]} xMarkers={xMarkers} ariaLabel={ariaLabel}
      legend={curves.length > 1} testId={testId} tipExtra={tipExtra} />
  );
}
