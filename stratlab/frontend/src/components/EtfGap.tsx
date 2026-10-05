import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { asOf, price } from "../lib/format";
import { etfGapApi, gapShort, gapWords, useEtfGaps, type EtfGapDetail } from "../lib/etfGaps";
import { LineChart } from "./Charts";
import { AlertButton } from "./AlertForm";
import { Panel } from "./Research";
import { Info } from "./ui";

/** An Indian ETF's gap to its last NAV as a small factual badge ("4.2% above last NAV"; "iNAV" only when a source
 * gives a real indicative NAV) that opens the ETF's page. Nothing for a stock, or for an ETF with neither value. */
export function EtfGapBadge({ symbol }: { symbol: string }) {
  const v = useEtfGaps();
  const r = v?.rows.find((x) => x.symbol === symbol);
  if (!r || r.gap == null || !r.basis) return null;
  const basis = r.basis === "iNAV" ? "iNAV" : "last NAV";
  const label = Math.abs(r.gap) < 0.005 ? `At ${basis}` : `${gapShort(r.gap)} ${basis}`;
  const of = r.basis === "NAV" && r.nav_date ? ` of ${asOf(r.nav_date)}` : "";
  return (
    <Link className="etf-gap-badge" data-etf-gap={symbol} to={`/invest/etf-gaps?etf=${encodeURIComponent(symbol)}`}
      title={`${symbol} ${gapWords(r.gap, r.basis === "iNAV" ? "indicative NAV" : "last NAV")}${of}${r.price_at ? ` (price as of ${asOf(r.price_at)})` : ""}`}>
      {label}
    </Link>
  );
}

/** "Price against NAV" for one ETF: the price against its last published NAV (and its iNAV, only when a source gives
 * one), and each day's close against that day's NAV over the last 30 trading days. `quiet` leaves the panel out when the symbol isn't an ETF (a company page). */
export function EtfGapDetailView({ symbol, quiet }: { symbol: string; quiet?: boolean }) {
  const list = useEtfGaps();
  const known = !!list?.rows.some((x) => x.symbol === symbol);
  const [d, setD] = useState<EtfGapDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (quiet && !known) return;
    let live = true;
    setD(null); setError(null);
    etfGapApi.detail(symbol).then((x) => live && setD(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [symbol, quiet, known]);
  if (quiet && !known) return null;
  if (error) return quiet ? null : <p className="small muted">{error}</p>;
  if (!d) return null;
  const r = d.row;
  const hist = d.history.filter((h) => h.gap != null);
  const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
  return (
    <Panel title="Price against NAV" span="full" id="etf-gap"
      info="The gap between the price on the exchange and what one unit holds, as a percent. Above means the price is higher than the NAV; below, lower. Facts, not advice."
      right={d.alerts ? <AlertButton region="IN" symbol={r.symbol} label="Alert on the gap" condition="etfgap_either" />
        : <Link className="btn quiet sm" to="/plans">Alerts on the gap: Basic</Link>}>
      <div className="etf-gap-figs" aria-label={`${r.symbol} price against NAV`}>
        <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Price</span><span className="num serif etf-gap-big">{price(r.price, "INR")}</span>
          <span className="tiny muted">{r.price_at ? `As of ${asOf(r.price_at)}` : "Last traded"}</span></div>
        {r.inav != null && <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Indicative NAV</span><span className="num serif etf-gap-big">{price(r.inav, "INR")}</span>
          {r.inav_gap != null && <span className="small">Price {gapWords(r.inav_gap, "iNAV").replace(/^trades /, "")}</span>}</div>}
        <div className="stack" style={{ gap: 2 }}><span className="eyebrow">Last NAV</span><span className="num serif etf-gap-big">{r.nav == null ? "–" : price(r.nav, "INR")}</span>
          <span className="small">{r.nav_gap == null ? <span className="muted">No published NAV found</span> : <>Price {gapWords(r.nav_gap, "last NAV").replace(/^trades /, "")}</>}</span>
          {r.nav_date && <span className="tiny muted">NAV of {day(r.nav_date)}</span>}</div>
      </div>
      {r.text && <p className="small" style={{ margin: 0 }}>{r.text}.</p>}
      {hist.length >= 2 ? (
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">Each day's close against that day's NAV</span>
          <LineChart lines={[{ values: hist.map((h) => h.gap), color: "var(--blue)", width: 2, label: "Gap to NAV" }]}
            labels={hist.map((h) => day(h.day))} height={190} baseline={0}
            format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`} axisFormat={(v) => `${v.toFixed(1)}%`}
            ariaLabel={`${r.symbol}'s gap to NAV at each close, ${day(hist[0].day)} to ${day(hist[hist.length - 1].day)}`} />
          {d.days && <span className="small">Over {d.days.days} trading days: from {gapShort(d.days.low)} to {gapShort(d.days.high)}, {gapShort(d.days.avg)} on average.</span>}
        </div>
      ) : <p className="small muted" style={{ margin: 0 }}>The daily history builds up from each close; there isn't enough of it yet.</p>}
      <p className="tiny muted" style={{ margin: 0 }}>{d.note}<Info label="Where the gap comes from">Above 0, the price is higher than the NAV;
        below 0, lower. The NAV is set once a day, after the close, so through the day the price moves against the last one{r.inav != null ? "; the iNAV moves with the holdings' prices" : ""}.</Info></p>
    </Panel>
  );
}
