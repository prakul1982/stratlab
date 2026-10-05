import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../lib/api";
import { vixChange, vixNum, vixPercentileLine, vixTime, type Vix } from "../lib/vix";
import { ChartEmpty, LineChart } from "./Charts";
import { Fig, Info, Loading } from "./ui";

/* India VIX on the Positioning page: the value now and its change, the day's range, where it sits among the past year's
 * closes, NIFTY's ATM IV beside it, today's line and the year's closes with NIFTY ATM IV drawn on the same chart. A
 * published index: no reading of what a level means. */

const short = (d: string) => new Date(d + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "2-digit" });

/** The panel's data, read once per page. */
export function useVix() {
  const [v, setV] = useState<Vix | null | "error">(null);
  useEffect(() => { api<Vix>("/trade/vix").then(setV).catch(() => setV("error")); }, []);
  return v;
}

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
  return (
    <section className="card stack pos-section" style={{ gap: 14 }} aria-labelledby="vix-h" id="india-vix" data-testid="vix-panel">
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 id="vix-h" className="h3 row" style={{ gap: 0 }}>India VIX
          <Info>The exchange's volatility index, worked out from NIFTY option prices. NIFTY ATM IV is StratLab's own model estimate from the nearest expiry, so the two are close but not the same number.</Info></h2>
        {q?.as_of && <span className="tiny muted">As of {vixTime(q.as_of)}</span>}
      </div>
      {error ? <p className="small muted">{error}</p>
        : !v ? <Loading label="Reading India VIX" />
        : (
          <>
            <div className="space-figs" data-testid="vix-figs">
              <Fig label="India VIX" value={v.value != null ? vixNum(v.value) : null} missing="Not read yet"
                note={vixChange(q ?? null) && <span data-testid="vix-change">{vixChange(q ?? null)} from {q?.prev_close != null ? vixNum(q.prev_close) : "the last close"}</span>} />
              <Fig label="Today's range" value={q?.low != null && q?.high != null ? `${vixNum(q.low)} – ${vixNum(q.high)}` : null} missing="Not available"
                note={q?.open != null && `Opened at ${vixNum(q.open)}`} />
              <Fig label="Percentile, past year" value={v.percentile.percentile != null ? String(Math.round(v.percentile.percentile)) : null} missing="Not enough days yet"
                note={<span data-testid="vix-pct">{vixPercentileLine(v.percentile)}{v.percentile.low != null && v.percentile.high != null ? `; range ${vixNum(v.percentile.low)} – ${vixNum(v.percentile.high)}` : ""}</span>} />
              <Fig label="NIFTY ATM IV" value={ivNow ? `${ivNow.iv.toFixed(2)}%` : null} missing="Not recorded yet"
                note={ivNow && `${ivNow.source === "live" ? "Live chain" : "Recorded chain"}, ${vixTime(ivNow.as_of) ?? ""}`} />
            </div>
            <div className="grid2" style={{ gap: 18 }}>
              <div className="stack pos-chart" style={{ gap: 8 }}>
                <h3 className="small" style={{ fontWeight: 600 }}>Today</h3>
                {v.intraday.length < 2 ? <ChartEmpty height={200}>Today's line starts when the market opens.</ChartEmpty> : (
                  <LineChart lines={[{ values: v.intraday.map((p) => p.v), color: "var(--series-1)", width: 2, label: "India VIX" }]}
                    labels={v.intraday.map((p) => vixTime(p.t) ?? p.t)} times={v.intraday.map((p) => p.t)} tz="Asia/Kolkata" ranges={false}
                    format={vixNum} height={200} testId="vix-intraday" ariaLabel="India VIX through today"
                    refs={q?.prev_close != null ? [{ v: q.prev_close, label: "Previous close", dash: true }] : []} />
                )}
              </div>
              <div className="stack pos-chart" style={{ gap: 8 }}>
                <h3 className="small" style={{ fontWeight: 600 }}>Past year: India VIX and NIFTY ATM IV (%)</h3>
                {!year || year.days.length < 2 ? <ChartEmpty height={200}>The history is being read; it shows here once stored.</ChartEmpty> : (
                  <LineChart lines={[{ values: year.vix, color: "var(--series-1)", width: 2, label: "India VIX" },
                    ...(year.iv.some((x) => x != null) ? [{ values: year.iv, color: "var(--series-2)", width: 1.6, label: "NIFTY ATM IV" }] : [])]}
                    labels={year.days.map(short)} times={year.days} legend ranges={false} format={(x) => x.toFixed(2)} height={200}
                    testId="vix-year" ariaLabel="India VIX's daily close and NIFTY's at-the-money IV over the past year" />
                )}
              </div>
            </div>
            <p className="tiny muted" data-testid="vix-source">
              {v.stored.days ? `${v.stored.days.toLocaleString("en-IN")} trading days stored, ${short(v.stored.first!)} to ${short(v.stored.last!)}. ` : ""}
              {v.note}
            </p>
          </>
        )}
    </section>
  );
}
