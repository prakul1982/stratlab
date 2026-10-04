/* The price chart for pages: the chart's code (engine, indicators, drawings) downloads only when a page with a
 * price chart opens. Pages import from here, never from PriceChart.tsx directly. */
import { lazy, Suspense } from "react";
import type { PriceChartProps } from "./PriceChart";
import { api } from "../../lib/api";
import type { BaseTf, Loader } from "./PriceChart";
import type { RawCandle } from "./transforms";
import type { StudyConfig, StudyType } from "./studies";

export type { PriceChartProps, Tf, RangeKey, Loader } from "./PriceChart";

const Chart = lazy(() => import("./PriceChart"));

export function PriceChart(props: PriceChartProps) {
  const h = props.height ?? 420;
  return (
    <Suspense fallback={<div className="chart-skel" style={{ height: h + 92 }} aria-label="Loading the chart" />}>
      <Chart {...props} />
    </Suspense>
  );
}

type Answer = { candles: RawCandle[]; more?: boolean; currency?: string };

/** Candles of a company on the research pages (India or the US). */
export function companyLoader(region: string, symbol: string): Loader {
  return (tf: BaseTf, o) => api<Answer>(`/research/chart/${region}/${encodeURIComponent(symbol)}?tf=${tf}&range=${(o.range ?? "1y").toLowerCase()}${o.before ? `&before=${encodeURIComponent(o.before)}` : ""}`);
}

/** Candles of any instrument the app trades on (notebooks, backtests, paper trading). */
export function instrumentLoader(instId: string): Loader {
  return (tf: BaseTf, o) => api<Answer>(`/chart/candles/${encodeURIComponent(instId)}?tf=${tf}&range=${(o.range ?? "1y").toLowerCase()}${o.before ? `&before=${encodeURIComponent(o.before)}` : ""}`);
}

const STUDY_OF: Partial<Record<string, StudyType>> = {
  sma: "sma", ema: "ema", rsi: "rsi", vwap: "vwap", supertrend: "supertrend", stage: "stage",
  bb_upper: "bb", bb_mid: "bb", bb_lower: "bb", macd: "macd", macd_signal: "macd", macd_hist: "macd",
};
const DEFAULTS: Record<StudyType, number[]> = { sma: [20], ema: [20], rsi: [14], vwap: [20], supertrend: [10, 3], stage: [150, 20], bb: [20, 2], macd: [12, 26, 9], hl52: [] };

/** The indicators a strategy's rules use, as chart indicators (on the chart's own timeframe only). */
export function strategyStudies(conds: { l: RefLike; r: RefLike }[]): StudyConfig[] {
  const out: StudyConfig[] = [];
  const seen = new Set<string>();
  for (const c of conds) for (const ref of [c.l, c.r]) {
    const type = ref && STUDY_OF[ref.t];
    if (!type || ref.tf || ref.ago || ref.k) continue;
    const def = DEFAULTS[type];
    const params = def.map((d, i) => (i === 0 && ref.p ? Number(ref.p) : i === 1 && ref.m ? Number(ref.m) : d));
    const key = `${type}:${params.join(",")}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ id: `rule-${key}`, type, params, slot: out.length });
  }
  return out.slice(0, 4);
}
interface RefLike { t: string; p?: number | null; m?: number | null; tf?: string | null; ago?: number | null; k?: number | null }
