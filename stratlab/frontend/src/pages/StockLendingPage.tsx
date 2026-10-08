import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { inr } from "../lib/format";
import { dayText, desksApi, plainPct, sharesShort, statusText, type DeskStatus, type LendRow, type LendTable } from "../lib/stockDesks";
import { Earlier } from "../components/Earlier";
import { Info } from "../components/ui";
import { Card, CardHead, DataTable, EmptyState, ErrorState, Field, PageHeader, Skeleton, Stat, StatRow, StockPicker, type Column } from "../components/kit";

/* /invest/stock-lending: what lending fees traded on the exchange's SLB segment for the stocks you hold and watch,
 * over the last 30 and 90 days, and any stock looked up day by day. Past traded fees with dates, never "you can earn";
 * StratLab doesn't arrange lending. Built from the kit (components/kit). */

type Trade = NonNullable<LendRow["trades"]>[number];
const range = (lo: number | null, hi: number | null) => (lo == null ? "–" : lo === hi ? plainPct(lo, 2) : `${plainPct(lo, 2)} to ${plainPct(hi, 2)}`);

function eligibleText(r: LendRow) {
  return r.eligible == null ? "Not known yet" : r.eligible ? "Eligible" : "Not on the lending list";
}

const tradeColumns: Column<Trade>[] = [
  { key: "day", header: "Day", rowHeader: true, cell: (t) => dayText(t.day) },
  { key: "end", header: "Series ends", cell: (t) => dayText(t.expiry) },
  { key: "fee", header: "Fee a share", numeric: true, cell: (t) => inr(t.fee, 2) },
  { key: "ann", header: "A year, of the price", numeric: true,
    info: "The day's average fee per share as a percent of that day's closing price, over the calendar days the series had left, scaled to a year.", cell: (t) => plainPct(t.ann, 2) },
  { key: "sh", header: "Shares lent", numeric: true, cell: (t) => sharesShort(t.shares) },
  { key: "n", header: "Trades", numeric: true, cell: (t) => t.trades },
];

function OneStock({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [d, setD] = useState<(LendRow & { status: DeskStatus; note: string }) | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    desksApi.lend(symbol).then((x) => live && setD(x)).catch((e) => live && setError(e instanceof ApiError ? e.message : "That stock couldn't be read."));
    return () => { live = false; };
  }, [symbol]);
  const cut = d?.as_of ? new Date(new Date(d.as_of).getTime() - 30 * 864e5).toISOString().slice(0, 10) : "";
  const recent = (d?.trades ?? []).filter((t) => t.day > cut), older = (d?.trades ?? []).filter((t) => t.day <= cut);
  const table = (rows: Trade[], label: string) => <DataTable label={label} rows={rows} rowKey={(t) => `${t.day}-${t.series}-${t.expiry}-${t.fee}`} sticky={rows.length > 14} columns={tradeColumns} />;
  return (
    <Card id="slb-one">
      <CardHead title={`${symbol}: lending fees that traded`} actions={<button className="btn quiet sm" onClick={onClose}>Close</button>} />
      {error ? <ErrorState title="That stock couldn't be read">{error}</ErrorState> : !d ? <Skeleton label={`Reading ${symbol}`} lines={3} /> : (
        <>
          <p className="k-small">{eligibleText(d)}{d.eligible_as_of ? ` (the exchange's list of ${dayText(d.eligible_as_of)})` : ""}.
            {" "}{d.summaries.map((s) => `${s.traded_days} of the last ${s.days} days had trades`).join("; ")}.</p>
          <StatRow>
            {d.summaries.map((s) => <Stat key={s.days} label={`Last ${s.days} days, a year`} value={range(s.ann_low, s.ann_high)} note={`${sharesShort(s.shares)} shares lent`} />)}
          </StatRow>
          {!d.trades?.length ? <EmptyState title={`No lending traded in ${symbol} in the last 90 days.`}>Nothing to list for this stock yet.</EmptyState> : (
            <>
              {recent.length ? table(recent, `${symbol} lending in the last 30 days`) : <p className="k-small k-muted">No lending in the last 30 days.</p>}
              <Earlier label="31 to 90 days ago" count={older.length}>{table(older, `${symbol} lending 31 to 90 days ago`)}</Earlier>
            </>
          )}
        </>
      )}
    </Card>
  );
}

export function StockLendingPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [t, setT] = useState<LendTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    setError(null);
    desksApi.lending().then(setT).catch((e) => setError(e instanceof ApiError ? e.message : "The lending fees couldn't be read."));
  }, [tries]);
  const open = (s: string | null) => { const p = new URLSearchParams(params); if (s) p.set("s", s); else p.delete("s"); setParams(p); };
  return (
    <div className="k-page slb-page">
      <PageHeader eyebrow={eyebrowOf("/invest/stock-lending")} title="Stock lending fees" asOf={t?.status.as_of}
        lede="The fees that lending your shares actually fetched on the exchange's SLB segment, for the stocks you hold and watch: past traded fees with their dates, and how often anything traded at all. Actual demand and fees vary; StratLab doesn't arrange lending."
        info={t ? <>{t.note} Source: {t.source}.</> : undefined} infoLabel="Where the numbers come from" />
      <Card id="slb-lookup">
        <CardHead title="Lending fees for any stock" info="Any company listed in India. Shows the lending fees that traded for it, day by day." />
        <Field label="Look up a stock">{(id) => <StockPicker id={id} value={pick} placeholder="Name or symbol, e.g. RELIANCE" onPick={(s) => open(s)} />}</Field>
      </Card>
      {pick && <OneStock key={pick} symbol={pick} onClose={() => open(null)} />}
      {error ? <ErrorState title="The lending fees couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState> : !t ? <Card><Skeleton label="Reading the lending fees" lines={4} /></Card> : (
        <Card label="Your holdings and watchlist">
          <CardHead title="Your holdings and watchlist" />
          <p className="k-note" data-testid="slb-status">{statusText(t.status, "the exchange's daily lending file")}<Info label="Where the numbers come from">{t.note} Source: {t.source}.</Info></p>
          {!t.rows.length ? (
            <EmptyState title="No Indian stocks to show yet">Add Indian stocks to <Link className="link" to="/holdings">My Holdings</Link> or your <Link className="link" to="/research/watchlist">watchlist</Link>, or look one up above.</EmptyState>
          ) : (
            <DataTable label="Lending fees for your stocks" rows={t.rows} rowKey={(r) => r.symbol} sticky={t.rows.length > 14} rowAttrs={(r) => ({ "data-stock": r.symbol })}
              columns={[
                { key: "s", header: "Stock", rowHeader: true, cell: (r) => (
                  <><a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
                    <span className="k-sub-line">{r.held ? "You hold it" : "Watchlist"}</span></>) },
                { key: "l", header: "Lending list", cell: (r) => eligibleText(r) },
                { key: "d", header: "Days with trades", numeric: true, cell: (r) => <>{r.summaries[0] ? `${r.summaries[0].traded_days} of 30` : "–"}<span className="k-sub-line">{r.summaries[1] ? `${r.summaries[1].traded_days} of 90` : ""}</span></> },
                { key: "a", header: "A year, last 30 days", numeric: true, cell: (r) => (r.summaries[0] ? range(r.summaries[0].ann_low, r.summaries[0].ann_high) : "–") },
                { key: "n", header: "Newest trade", numeric: true, cell: (r) => { const l = r.summaries[1]?.last; return l ? <>{plainPct(l.ann, 2)}<span className="k-sub-line">{dayText(l.day)}</span></> : <span className="k-muted">None in 90 days</span>; } },
                { key: "sh", header: "Shares lent, 30 days", numeric: true, cell: (r) => (r.summaries[0] ? sharesShort(r.summaries[0].shares) : "–") },
              ]} />
          )}
        </Card>
      )}
      {t && (
        <Card>
          <CardHead title="How lending works" />
          <dl className="k-dl">{t.facts.map((f) => <div key={f.title}><dt>{f.title}</dt><dd className="k-small">{f.text}</dd></div>)}</dl>
          <p className="k-note">Past fees, not what lending would fetch now. Lending goes through an approved intermediary, usually your broker.</p>
        </Card>
      )}
    </div>
  );
}

export default StockLendingPage;
