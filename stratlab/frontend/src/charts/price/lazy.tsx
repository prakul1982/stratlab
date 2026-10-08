/* The price chart for pages: the chart's code (engine, indicators, drawings) downloads only when a page with a
 * price chart opens. Pages import from here, never from PriceChart.tsx directly. */
import { lazy, Suspense } from "react";
import type { PriceChartProps } from "./PriceChart";
import { api } from "../../lib/api";
import { dayIn } from "../../lib/format";
import type { BaseTf, Loader } from "./PriceChart";
import type { RawCandle } from "./transforms";
import type { StudyConfig, StudyType } from "./studies";

export type { PriceChartProps, Tf, RangeKey, Loader } from "./PriceChart";

const load = () => import("./PriceChart");
const Chart = lazy(load);

/** Start downloading the chart's code now, for a page that shows it once its own data is in. */
export function preloadPriceChart() {
  load().catch(() => undefined);      // only a head start: the chart itself reports a failed download
}

export function PriceChart(props: PriceChartProps) {
  const h = props.height ?? 420;
  return (
    <Suspense fallback={<div className="chart-skel" style={{ height: h + 92 }} aria-label="Loading the chart" />}>
      <Chart {...props} />
    </Suspense>
  );
}

type Answer = { candles: RawCandle[]; more?: boolean; currency?: string };

/** The page's one reading of the price: what the company's header and tab title show, and when it was read. */
export interface QuoteReading { price: number | null | undefined; asOf: string | null | undefined; tz: string }

/** The calendar day of a candle's time (a date as written, or an instant in the market's zone). */
const candleDay = (t: string, tz: string): string | null => (/^\d{4}-\d{2}-\d{2}$/.test(t) ? t : dayIn(t, tz));

/** The newest candle brought to the price the page already shows. The header, the tab title and the chart's last candle are
 * one reading: when the newest candle is from the day that price was read, its close is that price (its high and low
 * widened to hold it), so the legend's close and change never differ from the header's by the cents a second reading
 * moved. Candles of another day, or a page without a price, are as the source sent them. */
export function settleLast(candles: RawCandle[], r: QuoteReading | null | undefined): RawCandle[] {
  const px = r?.price;
  if (!r || px == null || !Number.isFinite(px) || !candles.length) return candles;
  const last = candles[candles.length - 1];
  const day = dayIn(r.asOf, r.tz);
  if (!day || candleDay(last.t, r.tz) !== day) return candles;
  const hi = last.h == null ? px : Math.max(last.h, px), lo = last.l == null ? px : Math.min(last.l, px);
  return [...candles.slice(0, -1), { ...last, c: px, h: hi, l: lo }];
}

/** Candles of a company on the research pages (India or the US). With `reading`, the newest candle is the page's own price. */
export function companyLoader(region: string, symbol: string, reading?: QuoteReading | null): Loader {
  return (tf: BaseTf, o) => api<Answer>(`/research/chart/${region}/${encodeURIComponent(symbol)}?tf=${tf}&range=${(o.range ?? "1y").toLowerCase()}${o.before ? `&before=${encodeURIComponent(o.before)}` : ""}`)
    .then((a) => (o.before ? a : { ...a, candles: settleLast(a.candles ?? [], reading) }));
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
