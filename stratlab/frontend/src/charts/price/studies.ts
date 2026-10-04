/* The indicators a person can add to the price chart: their settings, names and what each draws, computed with
 * the engine's maths (indicators.ts). Facts about past prices only: no signals. */
import * as I from "./indicators";
import type { Bar } from "./transforms";

export type StudyType = "sma" | "ema" | "bb" | "vwap" | "supertrend" | "rsi" | "macd" | "stage" | "hl52";

export interface StudyConfig { id: string; type: StudyType; params: number[]; slot: number }

export interface StudyParam { label: string; min: number; max: number; step: number; def: number }

export interface StudyDef {
  type: StudyType; name: string; pane: "price" | "own"; params: StudyParam[];
  about: string;
}

export const STUDIES: StudyDef[] = [
  { type: "sma", name: "Moving average (SMA)", pane: "price", about: "The average close of the last N candles.",
    params: [{ label: "Length", min: 1, max: 400, step: 1, def: 20 }] },
  { type: "ema", name: "Exponential average (EMA)", pane: "price", about: "An average that weighs recent closes more.",
    params: [{ label: "Length", min: 1, max: 400, step: 1, def: 50 }] },
  { type: "bb", name: "Bollinger bands", pane: "price", about: "The N-candle average with bands K standard deviations either side.",
    params: [{ label: "Length", min: 2, max: 200, step: 1, def: 20 }, { label: "Deviations", min: 0.5, max: 5, step: 0.1, def: 2 }] },
  { type: "vwap", name: "VWAP", pane: "price", about: "Volume-weighted average price: from each day's open on intraday candles, over the last N candles on daily ones.",
    params: [{ label: "Length (daily candles)", min: 1, max: 200, step: 1, def: 20 }] },
  { type: "supertrend", name: "Supertrend", pane: "price", about: "A trailing band, ATR times the multiplier from the candle's middle.",
    params: [{ label: "ATR length", min: 1, max: 100, step: 1, def: 10 }, { label: "Multiplier", min: 0.5, max: 10, step: 0.1, def: 3 }] },
  { type: "stage", name: "Stage (30-week average)", pane: "price", about: "Weinstein's stage 1 to 4 from the 150-day average and its slope; the legend shows the stage.",
    params: [{ label: "Average length", min: 10, max: 400, step: 1, def: 150 }, { label: "Slope look-back", min: 1, max: 100, step: 1, def: 20 }] },
  { type: "hl52", name: "52-week high and low", pane: "price", about: "The highest high and lowest low of the year before each candle.",
    params: [] },
  { type: "rsi", name: "RSI", pane: "own", about: "Relative strength index, 0 to 100, with 30 and 70 lines.",
    params: [{ label: "Length", min: 2, max: 100, step: 1, def: 14 }] },
  { type: "macd", name: "MACD", pane: "own", about: "Fast minus slow exponential average, its signal line and the gap between them.",
    params: [{ label: "Fast", min: 1, max: 100, step: 1, def: 12 }, { label: "Slow", min: 2, max: 200, step: 1, def: 26 }, { label: "Signal", min: 1, max: 50, step: 1, def: 9 }] },
];

export const STUDY: Record<StudyType, StudyDef> = Object.fromEntries(STUDIES.map((d) => [d.type, d])) as Record<StudyType, StudyDef>;

export function studyLabel(c: StudyConfig): string {
  const p = c.params;
  switch (c.type) {
    case "sma": return `SMA ${p[0]}`;
    case "ema": return `EMA ${p[0]}`;
    case "bb": return `BB ${p[0]}, ${p[1]}`;
    case "vwap": return "VWAP";
    case "supertrend": return `Supertrend ${p[0]}, ${p[1]}`;
    case "stage": return `Stage ${p[0]}`;
    case "hl52": return "52-wk high/low";
    case "rsi": return `RSI ${p[0]}`;
    case "macd": return `MACD ${p[0]}, ${p[1]}, ${p[2]}`;
  }
}

/** A setting kept inside its allowed range and step. */
export function clampParam(def: StudyParam, v: number): number {
  if (!Number.isFinite(v)) return def.def;
  const x = Math.min(def.max, Math.max(def.min, v));
  return def.step >= 1 ? Math.round(x) : Math.round(x * 10) / 10;
}

export function newStudy(type: StudyType, taken: StudyConfig[]): StudyConfig {
  const used = new Set(taken.map((s) => s.slot));
  let slot = 0;
  while (used.has(slot)) slot++;
  return { id: `${type}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`, type, params: STUDY[type].params.map((p) => p.def), slot };
}

/** One computed line. `color` is a slot (0..) in the chart's indicator colours, or a role. */
export interface StudyLine { name: string; values: number[]; color: number | "up" | "down" | "muted"; dash?: boolean; width?: number; step?: boolean }

export interface StudyOutput {
  config: StudyConfig; label: string; pane: "price" | "own";
  lines: StudyLine[];
  hist?: number[];                 // MACD's gap, drawn as bars around zero
  fill?: [number, number];         // shade between two lines (Bollinger)
  range?: [number, number];        // a fixed scale (RSI 0..100)
  guides?: number[];               // dotted reference lines (RSI 30/70, MACD 0)
  stage?: number[];                // Weinstein stage per candle, for the legend
}

export function compute(bars: Bar[], c: StudyConfig, intraday: boolean): StudyOutput {
  const close = bars.map((b) => b.c);
  const [a, b, d] = c.params;
  const base = { config: c, label: studyLabel(c), pane: STUDY[c.type].pane };
  switch (c.type) {
    case "sma": return { ...base, lines: [{ name: "SMA", values: I.sma(close, a), color: c.slot }] };
    case "ema": return { ...base, lines: [{ name: "EMA", values: I.ema(close, a), color: c.slot }] };
    case "bb": {
      const bb = I.bollinger(close, a, b);
      return { ...base, fill: [0, 2], lines: [{ name: "Upper", values: bb.upper, color: c.slot, width: 1 }, { name: "Middle", values: bb.mid, color: c.slot, dash: true, width: 1 },
        { name: "Lower", values: bb.lower, color: c.slot, width: 1 }] };
    }
    case "vwap": return { ...base, lines: [{ name: "VWAP", values: I.vwap(bars, a, intraday), color: c.slot }] };
    case "supertrend": {
      const st = I.supertrend(bars, a, b);
      // drawn in two pieces: below price (blue) and above it (orange), with a gap where it flips side
      const below = st.map((v, i) => (Number.isFinite(v) && v <= bars[i].c ? v : NaN));
      const above = st.map((v, i) => (Number.isFinite(v) && v > bars[i].c ? v : NaN));
      return { ...base, lines: [{ name: "Below price", values: below, color: "up", width: 1.6 }, { name: "Above price", values: above, color: "down", width: 1.6 }] };
    }
    case "stage": {
      return { ...base, stage: I.stage(close, a, b), lines: [{ name: "Average", values: I.sma(close, a), color: c.slot, width: 1.6 }] };
    }
    case "hl52": {
      const { high, low } = I.rangeHighLow(bars, bars.map((x) => x.t), 365 * 86_400_000);
      return { ...base, lines: [{ name: "High", values: high, color: "muted", dash: true, width: 1, step: true }, { name: "Low", values: low, color: "muted", dash: true, width: 1, step: true }] };
    }
    case "rsi": return { ...base, range: [0, 100], guides: [30, 50, 70], lines: [{ name: "RSI", values: I.rsi(close, a), color: c.slot }] };
    case "macd": {
      const m = I.macd(close, a, b, d);
      return { ...base, guides: [0], hist: m.hist, lines: [{ name: "MACD", values: m.line, color: c.slot }, { name: "Signal", values: m.signal, color: "muted", dash: true }] };
    }
  }
}

export const STAGE_NAMES = ["", "Stage 1 (basing)", "Stage 2 (advancing)", "Stage 3 (topping)", "Stage 4 (declining)"];
