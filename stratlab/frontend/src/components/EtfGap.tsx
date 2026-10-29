import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { asOf, dayIn, num, pct, price, fmtDate } from "../lib/format";
import { useMarketRefresh } from "../lib/marketLive";
import { etfGapApi, gapAtPrice, gapShort, gapSummary, gapWords, useEtfGaps, type EtfGapDetail } from "../lib/etfGaps";
import { LineChart } from "./Charts";
import { AlertButton } from "./AlertForm";
import { ChartFrame, Disclosure, ErrorState, Skeleton, Stat, StatRow, useRange } from "./kit";

/** An Indian ETF's gap to its last NAV as a small factual badge ("4.2% above last NAV"; "iNAV" only when a source
 * gives a real indicative NAV) that opens the ETF's page. Nothing for a stock, or for an ETF with neither value. With `price`
 * (the price the page shows beside it) the gap is worked out from that price, not the list's own, so the two never disagree. */
export function EtfGapBadge({ symbol, price: shown, day }: { symbol: string; price?: number | null; day?: string | null }) {
  const v = useEtfGaps();
  const listed = v?.rows.find((x) => x.symbol === symbol);
  const r = listed && gapAtPrice(listed, shown, day);
  if (!r || r.gap == null || !r.basis) return null;
  // a gap of an earlier day's close says which day: never the day's move against yesterday's NAV
  const closed = r.basis === "NAV" && r.nav_price_day && r.price_at !== null && dayIn(r.price_at ?? "") !== r.nav_price_day ? r.nav_price_day : null;
  const basis = r.basis === "iNAV" ? "iNAV" : closed ? "NAV" : "last NAV";
  const label = (Math.abs(r.gap) < 0.005 ? `At ${basis}` : `${gapShort(r.gap)} ${basis}`) + (closed ? `, ${fmtDate(closed, { year: false })} close` : "");
  const of = r.basis === "NAV" && r.nav_date ? ` of ${asOf(r.nav_date)}` : "";
  return (
    <Link className="etf-gap-badge" data-etf-gap={symbol} to={`/invest/etf-gaps?etf=${encodeURIComponent(symbol)}`}
      title={`${symbol} ${gapWords(r.gap, r.basis === "iNAV" ? "indicative NAV" : "last NAV")}${of}${r.price_at ? ` (price as of ${asOf(r.price_at)})` : ` (at the price shown, ${price(r.price, "INR")})`}`}>
      {label}
    </Link>
  );
}

/** "Price against NAV" for one ETF: the gap as the headline, then the price and the last published NAV (and the iNAV, only when a
 * source gives one), and each day's close against that day's NAV for as far back as the app has it (years, O1), on the app's one range
 * control. `quiet` leaves the panel out when the symbol isn't an ETF (a company page). */
export function EtfGapDetailView({ symbol, quiet, price: shown, day: shownDay }: { symbol: string; quiet?: boolean; price?: number | null; day?: string | null }) {
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
  // the price, the gap and their times again each minute while India trades, in place (LIVE-1)
  useMarketRefresh(["IN"], () => { etfGapApi.detail(symbol).then((x) => setD((cur) => (cur && cur.row.symbol === x.row.symbol ? x : cur))).catch(() => undefined); }, !!d);
  const all = useMemo(() => (d?.history ?? []).filter((h) => h.gap != null), [d]);
  const times = useMemo(() => all.map((h) => h.day), [all]);
  const rng = useRange("etf-gap", times);
  if (quiet && !known) return null;
  if (error) return quiet ? null : <ErrorState title={`${symbol} couldn't be read`}>{error}</ErrorState>;
  if (!d) return quiet ? null : <Skeleton label={`Reading ${symbol}`} lines={3} />;
  const r = gapAtPrice(d.row, shown, shownDay);
  const hist = all.slice(rng.from);
  const sum = gapSummary(hist);
  const day = (iso: string) => fmtDate(iso, { year: false });
  const dayY = (iso: string) => fmtDate(iso, { year: true });
  // the gap, the headline, with the one line on what it is against; when it is left out, the reason in a few words
  const headline = r.gap == null ? "–" : gapShort(r.gap);
  const against = r.gap != null
    ? (r.basis === "iNAV" ? "to the indicative NAV" : r.nav_price_day ? `${day(r.nav_price_day)} close, to that day's NAV` : "to the last NAV")
    : r.nav_doubtful ? "Left out: the close and the latest price disagree"
    : r.nav_mismatch ? "Left out: the NAV is of another unit"
    : r.nav_closed_day && r.nav_date ? `No gap: the NAV is of ${day(r.nav_date)}, a day with no trading`
    : r.nav_waiting && r.nav_date ? `Not yet: no close of ${day(r.nav_date)} to set against the NAV` : "No published NAV found";
  return (
    <ChartFrame id="etf-gap" title="Price against NAV"
      info="The gap between the price on the exchange and what one unit holds, as a percent. Above means the price is higher than the NAV; below, lower. Facts, not advice."
      ranges={hist.length >= 2 || all.length >= 3 ? rng.options : undefined} range={rng.value} onRange={rng.pick} rangeFor={{ chart: "etf-gap", times }}
      actions={d.alerts ? <AlertButton region="IN" symbol={r.symbol} label="Alert on the gap" condition="etfgap_either" />
        : <Link className="btn quiet sm" to="/plans">Alerts on the gap: Basic</Link>}
      stats={
        <StatRow label={`${r.symbol} price against NAV`}>
          <Stat item label="Gap to NAV" value={headline} note={against} />
          <Stat item label="Price" value={price(r.price, "INR")} note={r.price_at ? `As of ${asOf(r.price_at)}` : "Last traded"} />
          {r.inav != null && <Stat item label="Indicative NAV" value={price(r.inav, "INR")} note={r.inav_gap != null ? gapShort(r.inav_gap) : undefined} />}
          <Stat item label="Last NAV" value={r.nav == null ? "–" : price(r.nav, "INR")} note={r.nav_date ? `NAV of ${day(r.nav_date)}` : undefined} />
        </StatRow>
      }
      table={all.length >= 2 ? { label: `${r.symbol}'s gap to NAV by day`, rows: [...hist].reverse(), rowKey: (h) => h.day,
        columns: [{ key: "d", header: "Day", rowHeader: true, cell: (h) => dayY(h.day) }, { key: "c", header: "Close", numeric: true, cell: (h) => (h.close == null ? "–" : price(h.close, "INR")) },
          { key: "n", header: "NAV", numeric: true, cell: (h) => (h.nav == null ? "–" : price(h.nav, "INR")) }, { key: "g", header: "Gap", numeric: true, cell: (h) => gapShort(h.gap) }] } : undefined}
      footer={
        <Disclosure summary="How this is worked out">
          <p className="k-note">{d.note}</p>
          <p className="k-note">Above 0, the price is higher than the NAV; below 0, lower. The NAV is set once a day, after the close, so through the day the price moves
            against the last one{r.inav != null ? "; the iNAV moves with the holdings' prices" : ""}. The older days are each day's closing price against that day's NAV, from the fund house's published history.</p>
        </Disclosure>}>
      <div className="k-stack">
        {all.length >= 2 ? (
          <>
            <LineChart lines={[{ values: hist.map((h) => h.gap), color: "var(--blue)", width: 2, label: "Gap to NAV" }]}
              labels={hist.map((h) => dayY(h.day))} times={hist.map((h) => h.day)} height={190} baseline={0} ranges={false} table={false}
              format={(v) => pct(v, 2)} axisFormat={(v) => `${num(v, 1)}%`}
              ariaLabel={`${r.symbol}'s gap to NAV at each close, ${day(hist[0].day)} to ${day(hist[hist.length - 1].day)}`} />
            {sum && <span className="k-small" data-testid="etf-gap-line">{sum.days} trading days, {dayY(sum.from)} to {dayY(sum.to)}: from {gapShort(sum.low)} to {gapShort(sum.high)}, {gapShort(sum.avg)} on average.</span>}
          </>
        ) : <p className="k-small k-muted">The daily history builds up from each close; there isn't enough of it yet.</p>}
      </div>
    </ChartFrame>
  );
}
