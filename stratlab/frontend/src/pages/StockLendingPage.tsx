import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { dayText, desksApi, plainPct, rupees, sharesShort, statusText, type DeskStatus, type LendRow, type LendTable } from "../lib/stockDesks";
import { Earlier } from "../components/Earlier";
import { Info, Loading } from "../components/ui";

/* /invest/stock-lending: what lending fees traded on the exchange's SLB segment for the stocks you hold and watch,
 * over the last 30 and 90 days, and any stock looked up day by day. Past traded fees with dates, never "you can earn";
 * StratLab doesn't arrange lending. */

const range = (lo: number | null, hi: number | null) => (lo == null ? "–" : lo === hi ? plainPct(lo, 2) : `${plainPct(lo, 2)} to ${plainPct(hi, 2)}`);

function eligibleText(r: LendRow) {
  return r.eligible == null ? "Not known yet" : r.eligible ? "Eligible" : "Not on the lending list";
}

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
  const table = (rows: NonNullable<LendRow["trades"]>, label: string) => (
    <div className="table-wrap">
      <table className="nums slb-trades" aria-label={label}>
        <thead><tr><th scope="col" style={{ textAlign: "left" }}>Day</th><th scope="col">Series ends</th><th scope="col">Fee a share</th>
          <th scope="col">A year, of the price<Info label="Annualised fee">The day's average fee per share as a percent of that day's closing price, over the calendar days the series had left, scaled to a year.</Info></th>
          <th scope="col">Shares lent</th><th scope="col">Trades</th></tr></thead>
        <tbody>{rows.map((t, i) => (
          <tr key={`${t.day}-${t.series}-${i}`}>
            <th scope="row" style={{ textAlign: "left" }}>{dayText(t.day)}</th><td>{dayText(t.expiry)}</td><td>{rupees(t.fee)}</td>
            <td>{plainPct(t.ann, 2)}</td><td>{sharesShort(t.shares)}</td><td>{t.trades}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
  return (
    <section className="card stack" style={{ gap: 12 }} id="slb-one" aria-labelledby="slb-one-h">
      <div className="spread" style={{ gap: 10 }}>
        <h2 id="slb-one-h" className="h3">{symbol}: lending fees that traded</h2>
        <button className="btn quiet sm" onClick={onClose}>Close</button>
      </div>
      {error ? <p className="small muted">{error}</p> : !d ? <Loading label={`Reading ${symbol}`} /> : (
        <>
          <p className="small">{eligibleText(d)}{d.eligible_as_of ? ` (the exchange's list of ${dayText(d.eligible_as_of)})` : ""}.
            {" "}{d.summaries.map((s) => `${s.traded_days} of the last ${s.days} days had trades`).join("; ")}.</p>
          <div className="space-figs">
            {d.summaries.map((s) => (
              <div key={s.days} className="space-fig"><span className="tiny muted">Last {s.days} days, a year</span>
                <b className="num">{range(s.ann_low, s.ann_high)}</b><span className="tiny muted">{sharesShort(s.shares)} shares lent</span></div>
            ))}
          </div>
          {!d.trades?.length ? <p className="small muted">No lending traded in {symbol} in the last 90 days.</p> : (
            <>
              {recent.length ? table(recent, `${symbol} lending in the last 30 days`) : <p className="small muted">No lending in the last 30 days.</p>}
              <Earlier label="31 to 90 days ago" count={older.length}>{table(older, `${symbol} lending 31 to 90 days ago`)}</Earlier>
            </>
          )}
        </>
      )}
    </section>
  );
}

export function StockLendingPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [t, setT] = useState<LendTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => { desksApi.lending().then(setT).catch((e) => setError(e instanceof ApiError ? e.message : "The lending fees couldn't be read.")); }, []);
  const open = (s: string | null) => { const p = new URLSearchParams(params); if (s) p.set("s", s); else p.delete("s"); setParams(p); };
  const look = (e: React.FormEvent) => { e.preventDefault(); const s = q.trim().toUpperCase(); if (/^[A-Z0-9&-]{1,20}$/.test(s)) open(s); };
  return (
    <div className="stack slb-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Invest · India</span>
        <h1 className="page-title">Stock lending fees</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>The fees that lending your shares actually fetched on the exchange's SLB segment, for the stocks you hold and
          watch: past traded fees with their dates, and how often anything traded at all. Actual demand and fees vary; StratLab doesn't arrange lending.</p>
      </div>
      <form className="row wrap" style={{ gap: 8 }} onSubmit={look}>
        <input className="input" type="search" aria-label="Look up a stock" placeholder="Look up a stock, like RELIANCE" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 200px", maxWidth: 320 }} />
        <button className="btn sm">Show fees</button>
      </form>
      {pick && <OneStock key={pick} symbol={pick} onClose={() => open(null)} />}
      {error ? <div className="banner">{error}</div> : !t ? <Loading label="Reading the lending fees" /> : (
        <section className="card stack" style={{ gap: 12 }} aria-labelledby="slb-mine-h">
          <h2 id="slb-mine-h" className="h3">Your holdings and watchlist</h2>
          <p className="tiny muted" style={{ margin: 0 }} data-testid="slb-status">{statusText(t.status, "the SLB bhavcopy")}<Info label="Where the numbers come from">{t.note} Source: {t.source}.</Info></p>
          {!t.rows.length ? (
            <p className="small muted">Add Indian stocks to <Link className="link" to="/holdings">My Holdings</Link> or your <Link className="link" to="/research/watchlist">watchlist</Link>, or look one up above.</p>
          ) : (
            <div className="table-wrap">
              <table className="nums slb-table" aria-label="Lending fees for your stocks">
                <thead><tr><th scope="col" style={{ textAlign: "left" }}>Stock</th><th scope="col" style={{ textAlign: "left" }}>Lending list</th>
                  <th scope="col">Days with trades</th><th scope="col">A year, last 30 days</th><th scope="col">Newest trade</th><th scope="col">Shares lent, 30 days</th></tr></thead>
                <tbody>{t.rows.map((r) => {
                  const [s30, s90] = r.summaries;
                  return (
                    <tr key={r.symbol} data-stock={r.symbol}>
                      <th scope="row" style={{ textAlign: "left" }}>
                        <a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
                        <div className="tiny muted">{r.held ? "You hold it" : "Watchlist"}</div>
                      </th>
                      <td style={{ textAlign: "left" }} className="small">{eligibleText(r)}</td>
                      <td>{s30 ? `${s30.traded_days} of 30` : "–"}<span className="tiny muted" style={{ display: "block" }}>{s90 ? `${s90.traded_days} of 90` : ""}</span></td>
                      <td>{s30 ? range(s30.ann_low, s30.ann_high) : "–"}</td>
                      <td>{s90?.last ? <>{plainPct(s90.last.ann, 2)}<span className="tiny muted" style={{ display: "block" }}>{dayText(s90.last.day)}</span></> : <span className="muted small">None in 90 days</span>}</td>
                      <td>{s30 ? sharesShort(s30.shares) : "–"}</td>
                    </tr>
                  );
                })}</tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {t && (
        <section className="card stack" style={{ gap: 10 }} aria-labelledby="slb-facts-h">
          <h2 id="slb-facts-h" className="h3">How lending works</h2>
          <dl className="slb-facts">{t.facts.map((f) => <div key={f.title}><dt>{f.title}</dt><dd className="small">{f.text}</dd></div>)}</dl>
          <p className="tiny muted" style={{ margin: 0 }}>Past fees, not what lending would fetch now. Lending goes through an approved intermediary, usually your broker.</p>
        </section>
      )}
    </div>
  );
}

export default StockLendingPage;
