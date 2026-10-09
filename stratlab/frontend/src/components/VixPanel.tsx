import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api, ApiError } from "../lib/api";
import { vixChange, vixFreshness, vixNum, vixPercentileLine, type Vix } from "../lib/vix";
import { ChartEmpty, LineChart } from "./Charts";
import { Badge, Card, CardHead, ErrorState, Skeleton, Stat, StatRow } from "./kit";
import "../pages/trade/trade.css";
import "../pages/trade/positioning.css";
import { asOf, fmtDate, IST } from "../lib/format";
import { chainWords } from "../lib/positioning";
const upperFirst = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/* India VIX on the Positioning page: the value now and its change, the day's range, where it sits among the past year's
 * closes, NIFTY's ATM IV beside it, the day's line and the year's closes with NIFTY ATM IV drawn on the same chart. A
 * published index: no reading of what a level means. Figures read on an earlier day say so, and are never titled
 * "today". */

/** "5 Oct, 12:04 IST" from an ISO time with an offset, in India time. */
const vixTime = (iso: string | null | undefined): string | null => asOf(iso, { tz: IST, year: false });
const short = (d: string) => fmtDate(d);

export function VixPanel() {
  const [v, setV] = useState<Vix | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<Vix>("/trade/vix").then(setV).catch((e) => setError(e instanceof ApiError ? e.message : "India VIX couldn't be read just now."));
  }, []);
  const year = useMemo(() => {
    if (!v) return null;
    const iv = new Map(v.nifty_iv.series.map((p) => [p.day, p.iv]));
    return { days: v.history.map((p) => p.day), vix: v.history.map((p) => p.close), iv: v.history.map((p) => iv.get(p.day) ?? null) };
  }, [v]);
  const q = v?.quote;
  const ivNow = v?.nifty_iv.today;
  const fresh = v ? vixFreshness(v) : null;
  const val = (x: ReactNode | null, missing: string) => (x == null || x === false ? <span className="k-small k-muted">{missing}</span> : x);
  return (
    <Card id="india-vix" testId="vix-panel" label="India VIX">
      <CardHead title="India VIX" infoLabel="About India VIX"
        info="The exchange's volatility index, worked out from NIFTY option prices. NIFTY ATM IV is StratLab's own model estimate from the nearest expiry, so the two are close but not the same number."
        actions={fresh?.asOf ? <>
          {fresh.stale && <span data-testid="vix-stale"><Badge tone="warn">Not updated today</Badge></span>}
          <span className="k-note" data-testid="vix-asof">As of {fresh.asOf}</span>
        </> : undefined} />
      {error ? <ErrorState title="India VIX couldn't be read">{error}</ErrorState>
        : !v ? <Skeleton label="Reading India VIX" />
        : (
          <>
            <div data-testid="vix-figs">
              <StatRow label="India VIX figures">
                <Stat label="India VIX" value={val(v.value != null ? vixNum(v.value) : null, "Not read yet")}
                  note={vixChange(q ?? null) ? <span data-testid="vix-change">{vixChange(q ?? null)} from {q?.prev_close != null ? vixNum(q.prev_close) : "the last close"}</span> : undefined} />
                <Stat label={fresh?.rangeLabel ?? "Today's range"} value={val(q?.low != null && q?.high != null ? `${vixNum(q.low)} – ${vixNum(q.high)}` : null, "Not available")}
                  note={q?.open != null ? `Opened at ${vixNum(q.open)}` : undefined} />
                <Stat label="Percentile, past year" value={val(v.percentile.percentile != null ? String(Math.round(v.percentile.percentile)) : null, "Not enough days yet")}
                  note={<span data-testid="vix-pct">{vixPercentileLine(v.percentile)}{v.percentile.low != null && v.percentile.high != null ? `; range ${vixNum(v.percentile.low)} – ${vixNum(v.percentile.high)}` : ""}</span>} />
                <Stat label="NIFTY ATM IV" value={val(ivNow ? `${ivNow.iv.toFixed(2)}%` : null, "Not recorded yet")}
                  note={ivNow ? `${upperFirst(chainWords(ivNow))}, ${vixTime(ivNow.as_of) ?? ""}` : undefined} />
              </StatRow>
            </div>
            <div className="k-two">
              <div className="k-stack pos-chart">
                <h3 className="k-sub" data-testid="vix-line-title">{fresh?.lineTitle ?? "Today"}</h3>
                {v.intraday.length < 2 ? <ChartEmpty height={200}>Today's line starts when the market opens.</ChartEmpty> : (
                  <LineChart lines={[{ values: v.intraday.map((p) => p.v), color: "var(--series-1)", width: 2, label: "India VIX" }]}
                    labels={v.intraday.map((p) => vixTime(p.t) ?? p.t)} times={v.intraday.map((p) => p.t)} tz={IST} ranges={false}
                    format={vixNum} height={200} testId="vix-intraday" include={fresh && fresh.quoteDay === fresh.lineDay ? [q?.low, q?.high, q?.open] : undefined} ariaLabel={fresh?.lineStale ? `India VIX through ${fresh.lineTitle}, times in IST` : "India VIX through today, times in IST"}
                    refs={q?.prev_close != null ? [{ v: q.prev_close, label: "Previous close", dash: true }] : []} />
                )}
              </div>
              <div className="k-stack pos-chart">
                <h3 className="k-sub">Past year: India VIX and NIFTY ATM IV (%)</h3>
                {!year || year.days.length < 2 ? <ChartEmpty height={200}>The history is being read; it shows here once stored.</ChartEmpty> : (
                  <LineChart lines={[{ values: year.vix, color: "var(--series-1)", width: 2, label: "India VIX" },
                    ...(year.iv.some((x) => x != null) ? [{ values: year.iv, color: "var(--series-2)", width: 1.6, label: "NIFTY ATM IV" }] : [])]}
                    labels={year.days.map(short)} times={year.days} legend ranges={false} format={(x) => x.toFixed(2)} height={200}
                    testId="vix-year" ariaLabel="India VIX's daily close and NIFTY's at-the-money IV over the past year" />
                )}
              </div>
            </div>
            <p className="k-note" data-testid="vix-source">
              {v.stored.days ? `${v.stored.days.toLocaleString("en-IN")} trading days of history, ${short(v.stored.first!)} to ${short(v.stored.last!)}. ` : ""}
              {v.note}
            </p>
          </>
        )}
    </Card>
  );
}
