/* The price chart for pages: the chart's code (engine, indicators, drawings) downloads only when a page with a
 * price chart opens. Pages import from here, never from PriceChart.tsx directly. */
import { lazy, Suspense } from "react";
import type { PriceChartProps } from "./PriceChart";
import { api } from "../../lib/api";
import { importWithRetry } from "../../lib/lazyRetry";
import { settleLast, type QuoteReading } from "./settle";
import type { BaseTf, Loader } from "./PriceChart";
import type { RawCandle } from "./transforms";
import type { StudyConfig, StudyType } from "./studies";

export type { PriceChartProps, Tf, RangeKey, Loader, LiveFeed } from "./PriceChart";
export type { QuoteReading } from "./settle";

const load = () => import("./PriceChart");
const Chart = lazy(() => importWithRetry(load));

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

type Answer = { candles: RawCandle[]; more?: boolean; currency?: string; live?: boolean; delayed?: boolean };

/** Candles of a company on the research pages (India or the US). With `reading`, the newest candle is the page's own price. */
/** A company's candles as last read, kept a few minutes: the page reads its price again each minute while the market
 * trades (lib/liveRefresh), and each new price settles the newest candle on these instead of reading the whole year again
 * (R64-003: the 1-year hourly chart was downloaded every minute). Read again after CHART_KEEP_MS, so the candles' volume
 * moves on too. */
const CHART_KEEP_MS = 5 * 60_000;
const kept = new Map<string, { at: number; got: Promise<Answer> }>();
export function companyLoader(region: string, symbol: string, reading?: QuoteReading | null, fresh = false): Loader {
  return (tf: BaseTf, o) => {
    const url = `/research/chart/${region}/${encodeURIComponent(symbol)}?tf=${tf}&range=${(o.range ?? "1y").toLowerCase()}${o.before ? `&before=${encodeURIComponent(o.before)}` : ""}`;
    // the older candles a scrolled-back chart asks for are kept too: each minute's new price draws the chart again, and it
    // asked for them again each time (R65-001)
    const hit = fresh ? undefined : kept.get(url);        // `fresh`: the chart workspace's minute charts must not open on a five-minute-old copy
    let got = hit && Date.now() - hit.at < CHART_KEEP_MS ? hit.got : undefined;
    if (!got) {
      got = api<Answer>(url);
      if (!fresh) kept.set(url, { at: Date.now(), got });
      got.catch(() => kept.delete(url));
      if (kept.size > 40) kept.delete(kept.keys().next().value!);
    }
    return o.before ? got : got.then((a) => ({ ...a, candles: settleLast(a.candles ?? [], reading) }));
  };
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
