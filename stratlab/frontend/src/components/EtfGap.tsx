import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { asOf, price, fmtDate } from "../lib/format";
import { etfGapApi, gapShort, gapWords, useEtfGaps, type EtfGapDetail } from "../lib/etfGaps";
import { LineChart } from "./Charts";
import { AlertButton } from "./AlertForm";
import { Info } from "./ui";
import { ChartFrame, ErrorState, Skeleton, Stat, StatRow } from "./kit";

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
  if (error) return quiet ? null : <ErrorState title={`${symbol} couldn't be read`}>{error}</ErrorState>;
  if (!d) return quiet ? null : <Skeleton label={`Reading ${symbol}`} lines={3} />;
  const r = d.row;
  const hist = d.history.filter((h) => h.gap != null);
  const day = (iso: string) => fmtDate(iso, { year: false });
  return (
    <ChartFrame id="etf-gap" title="Price against NAV"
      info="The gap between the price on the exchange and what one unit holds, as a percent. Above means the price is higher than the NAV; below, lower. Facts, not advice."
      actions={d.alerts ? <AlertButton region="IN" symbol={r.symbol} label="Alert on the gap" condition="etfgap_either" />
        : <Link className="btn quiet sm" to="/plans">Alerts on the gap: Basic</Link>}
      stats={
        <StatRow label={`${r.symbol} price against NAV`}>
          <Stat item label="Price" value={price(r.price, "INR")} note={r.price_at ? `As of ${asOf(r.price_at)}` : "Last traded"} />
          {r.inav != null && <Stat item label="Indicative NAV" value={price(r.inav, "INR")} note={r.inav_gap != null ? `Price ${gapWords(r.inav_gap, "iNAV").replace(/^trades /, "")}` : undefined} />}
          <Stat item label="Last NAV" value={r.nav == null ? "–" : price(r.nav, "INR")}
            note={<>{r.nav_gap == null ? "No published NAV found" : `Price ${gapWords(r.nav_gap, "last NAV").replace(/^trades /, "")}`}{r.nav_date && <><br />NAV of {day(r.nav_date)}</>}</>} />
        </StatRow>
      }
      table={hist.length >= 2 ? { label: `${r.symbol}'s gap to NAV by day`, rows: [...hist].reverse(), rowKey: (h) => h.day,
        columns: [{ key: "d", header: "Day", rowHeader: true, cell: (h) => day(h.day) }, { key: "c", header: "Close", numeric: true, cell: (h) => (h.close == null ? "–" : price(h.close, "INR")) },
          { key: "n", header: "NAV", numeric: true, cell: (h) => (h.nav == null ? "–" : price(h.nav, "INR")) }, { key: "g", header: "Gap", numeric: true, cell: (h) => gapShort(h.gap) }] } : undefined}
      footer={<p className="k-note">{d.note}<Info label="Where the gap comes from">Above 0, the price is higher than the NAV;
        below 0, lower. The NAV is set once a day, after the close, so through the day the price moves against the last one{r.inav != null ? "; the iNAV moves with the holdings' prices" : ""}.</Info></p>}>
      <div className="k-stack">
        {r.text && <p className="k-small">{r.text}.</p>}
        {hist.length >= 2 ? (
          <>
            <span className="k-eyebrow">Each day's close against that day's NAV</span>
            <LineChart lines={[{ values: hist.map((h) => h.gap), color: "var(--blue)", width: 2, label: "Gap to NAV" }]}
              labels={hist.map((h) => day(h.day))} height={190} baseline={0} ranges={false} table={false}
              format={(v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`} axisFormat={(v) => `${v.toFixed(1)}%`}
              ariaLabel={`${r.symbol}'s gap to NAV at each close, ${day(hist[0].day)} to ${day(hist[hist.length - 1].day)}`} />
            {d.days && <span className="k-small">Over {d.days.days} trading days: from {gapShort(d.days.low)} to {gapShort(d.days.high)}, {gapShort(d.days.avg)} on average.</span>}
          </>
        ) : <p className="k-small k-muted">The daily history builds up from each close; there isn't enough of it yet.</p>}
      </div>
    </ChartFrame>
  );
}
