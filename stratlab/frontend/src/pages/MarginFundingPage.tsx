import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { croreText, dayText, desksApi, plainPct, rupees, sharesShort, signedPct, statusText, type CostIn, type CostOut, type MtfChange, type MtfOne, type MtfPage } from "../lib/stockDesks";
import { ChartEmpty, LineChart } from "../components/Charts";
import { AlertButton } from "../components/AlertForm";
import { Info, Loading } from "../components/ui";

/* /invest/margin-funding: what brokers together had funded under the margin trading facility, for the whole market and
 * for each stock you hold or watch (the exchange's daily disclosure), and your own MTF position worked out. Dated facts
 * and arithmetic: no "risky" labels, no ranking. Today's numbers and the calculator on every plan; history and the
 * alert on a funded level on Basic. */

const chg = (c: MtfChange | undefined) => (c ? `${c.crore >= 0 ? "+" : "−"}₹${Math.abs(c.crore).toLocaleString("en-IN", { maximumFractionDigits: 2 })} cr (${signedPct(c.pct, 1)})` : "–");

function Market({ p }: { p: MtfPage }) {
  const m = p.market;
  const h = m.history ?? [];
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="mtf-book-h">
      <h2 id="mtf-book-h" className="h3 row" style={{ gap: 0 }}>The market's MTF book<Info label="The MTF book">{p.about.book}</Info></h2>
      {!m.as_of ? <p className="small muted">{p.status.reason ?? "Nothing stored yet."}</p> : (
        <>
          <div className="space-figs">
            <div className="space-fig"><span className="tiny muted">Funded at the end of {dayText(m.as_of)}</span><b className="num">{croreText(m.end)}</b>
              <span className="tiny muted">{m.stocks?.toLocaleString("en-IN")} stocks</span></div>
            <div className="space-fig"><span className="tiny muted">That day</span><b className="num">{m.end != null && m.start != null ? `${m.end >= m.start ? "+" : "−"}₹${Math.abs(m.end - m.start).toLocaleString("en-IN", { maximumFractionDigits: 0 })} cr` : "–"}</b>
              <span className="tiny muted">fresh {croreText(m.fresh)} · liquidated {croreText(m.liquidated)}</span></div>
            <div className="space-fig"><span className="tiny muted">Over 30 days</span><b className="num">{m.d30 ? `${m.d30.crore >= 0 ? "+" : "−"}₹${Math.abs(m.d30.crore).toLocaleString("en-IN", { maximumFractionDigits: 0 })} cr` : "–"}</b>
              <span className="tiny muted">{m.d30 ? `${signedPct(m.d30.pct, 1)} since ${dayText(m.d30.from)}` : "Not 30 days stored yet"}</span></div>
          </div>
          {p.full ? (h.length < 2 ? <ChartEmpty height={180}>Not enough stored days to draw yet.</ChartEmpty> : (
            <LineChart lines={[{ values: h.map((x) => x.end), color: "var(--pos-call)", width: 2, label: "MTF book" }]} labels={h.map((x) => dayText(x.day))} times={h.map((x) => x.day)}
              ranges={false} format={(v) => croreText(v)} axisFormat={(v) => `₹${(v / 1000).toFixed(1)}k cr`} height={180} ariaLabel="The market's margin-funded book by day, ₹ crore" />
          )) : <p className="tiny muted" style={{ margin: 0 }}>The book day by day is on the <Link className="link" to="/plans">{p.plan_needed} plan</Link>.</p>}
        </>
      )}
    </section>
  );
}

function OneStock({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const [d, setD] = useState<MtfOne | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    desksApi.mtfOne(symbol).then((x) => live && setD(x)).catch((e) => live && setError(e instanceof ApiError ? e.message : "That stock couldn't be read."));
    return () => { live = false; };
  }, [symbol]);
  const h = d?.history ?? [];
  return (
    <section className="card stack" style={{ gap: 12 }} id="mtf-one" aria-labelledby="mtf-one-h">
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 id="mtf-one-h" className="h3">{symbol}: margin funded</h2>
        <div className="row" style={{ gap: 8 }}>
          {d?.full && d.funded && <AlertButton region="IN" symbol={symbol} condition="mtf_above" label="Alert on a level" />}
          <button className="btn quiet sm" onClick={onClose}>Close</button>
        </div>
      </div>
      {error ? <p className="small muted">{error}</p> : !d ? <Loading label={`Reading ${symbol}`} /> : !d.funded ? (
        <p className="small muted">{d.as_of ? `${symbol} had no margin funding in the exchange's disclosure of ${dayText(d.as_of)}.` : "Nothing stored yet."}</p>
      ) : (
        <>
          <p className="small">{croreText(d.crore)} is margin funded on {dayText(d.as_of)}{d.pct_shares != null ? `, ${plainPct(d.pct_shares, 2)} of shares issued` : ""}.</p>
          <div className="space-figs">
            <div className="space-fig"><span className="tiny muted">Shares funded</span><b className="num">{sharesShort(d.shares)}</b>
              <span className="tiny muted">{plainPct(d.pct_shares, 2)} of shares issued<Info label="Of shares issued">{d.about.pct_shares}</Info></span></div>
            <div className="space-fig"><span className="tiny muted">Of market value</span><b className="num">{plainPct(d.pct_mcap, 2)}</b>
              <span className="tiny muted">at the close of ₹{d.close?.toLocaleString("en-IN")}<Info label="Of market value">{d.about.pct_mcap}</Info></span></div>
            <div className="space-fig"><span className="tiny muted">Change</span><b className="num">{chg(d.day)}</b>
              <span className="tiny muted">30 days: {chg(d.d30)}</span></div>
          </div>
          {d.full ? (h.length < 2 ? <ChartEmpty height={180}>Not enough stored days to draw yet.</ChartEmpty> : (
            <LineChart lines={[{ values: h.map((x) => x.crore), color: "var(--pos-call)", width: 2, label: "Funded" }]} labels={h.map((x) => dayText(x.day))} times={h.map((x) => x.day)}
              ranges={false} format={(v) => croreText(v)} height={180} ariaLabel={`${symbol}'s margin-funded amount by day, ₹ crore`} />
          )) : <p className="tiny muted" style={{ margin: 0 }} data-testid="mtf-locked">A year of {symbol}'s margin funding, and an alert when it crosses a level, are on the <Link className="link" to="/plans">{d.plan_needed} plan</Link>.</p>}
        </>
      )}
    </section>
  );
}

const START: Record<keyof CostIn, string> = { buy: "", qty: "", margin_pct: "25", rate_pct: "15", days: "30", charges: "0", price: "", maint_pct: "" };
const FIELDS: [keyof CostIn, string, string][] = [["buy", "Buy price (₹ a share)", "1000"], ["qty", "Shares", "100"], ["margin_pct", "Your part of the buy value (%)", "25"],
  ["rate_pct", "Broker's interest (% a year)", "15"], ["days", "Days the funding is open", "30"], ["charges", "Pledge and other charges (₹, all told)", "0"],
  ["price", "Price now (₹, optional)", ""], ["maint_pct", "Margin the broker asks you to keep (%, optional)", ""]];

function Calculator() {
  const { fail } = useApp();
  const [f, setF] = useState(START);
  const [out, setOut] = useState<CostOut | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    const n = (k: keyof CostIn) => (f[k].trim() === "" ? null : Number(f[k]));
    const body = { buy: n("buy"), qty: n("qty"), margin_pct: n("margin_pct"), rate_pct: n("rate_pct"), days: n("days"), charges: n("charges") ?? 0,
      price: n("price"), maint_pct: n("maint_pct") ?? 0 } as CostIn;
    setBusy(true);
    try { setOut(await desksApi.cost(body)); } catch (err) { fail(err); } finally { setBusy(false); }
  };
  return (
    <section className="card stack" style={{ gap: 12 }} id="mtf-cost" aria-labelledby="mtf-cost-h">
      <h2 id="mtf-cost-h" className="h3">What your MTF position costs</h2>
      <p className="small muted">Enter your own position. Interest is worked out daily on the funded amount, as most brokers charge it; check your broker's contract note for the exact figures.</p>
      <form className="mtf-form" onSubmit={run}>
        {FIELDS.map(([k, label, ph]) => (
          <label key={k} className="field">{label}
            <input inputMode="decimal" value={f[k]} placeholder={ph} onChange={(e) => setF({ ...f, [k]: e.target.value })} />
          </label>
        ))}
        <button className="btn" disabled={busy} style={{ alignSelf: "end" }}>{busy ? "Working it out…" : "Work it out"}</button>
      </form>
      {out && (
        <div className="stack" style={{ gap: 8 }} data-testid="mtf-cost-out">
          <div className="space-figs">
            <div className="space-fig"><span className="tiny muted">Funded by the broker</span><b className="num">{rupees(out.funded, 0)}</b><span className="tiny muted">your part {rupees(out.own, 0)}</span></div>
            <div className="space-fig"><span className="tiny muted">Interest so far</span><b className="num">{rupees(out.interest)}</b><span className="tiny muted">{rupees(out.interest_day)} a day</span></div>
            <div className="space-fig"><span className="tiny muted">Price that covers interest and charges</span><b className="num">{rupees(out.breakeven)}</b><span className="tiny muted">{signedPct(out.breakeven_pct)} on the buy price</span></div>
            {out.breach_price != null && <div className="space-fig"><span className="tiny muted">Price where the margin falls under the broker's %</span><b className="num">{rupees(out.breach_price)}</b>
              <span className="tiny muted">{(out.breach_fall_pct ?? 0) > 0 ? `${plainPct(out.breach_fall_pct, 2)} under ${rupees(out.breach_from)}` : `already at or under it at ${rupees(out.breach_from)}`}</span></div>}
          </div>
          {out.pnl != null && <p className="small">At {rupees(out.price)}, the position is {out.pnl >= 0 ? "up" : "down"} {rupees(Math.abs(out.pnl))} after interest and charges ({signedPct(out.pnl_pct_own, 1)} of your part); the margin left is {plainPct(out.margin_now_pct, 1)}.</p>}
          <p className="tiny muted" style={{ margin: 0 }}>Arithmetic on the numbers you entered, not advice.</p>
        </div>
      )}
    </section>
  );
}

export function MarginFundingPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [p, setP] = useState<MtfPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  useEffect(() => { desksApi.mtf().then(setP).catch((e) => setError(e instanceof ApiError ? e.message : "The margin funding numbers couldn't be read.")); }, []);
  const open = (s: string | null) => { const x = new URLSearchParams(params); if (s) x.set("s", s); else x.delete("s"); setParams(x); };
  const look = (e: React.FormEvent) => { e.preventDefault(); const s = q.trim().toUpperCase(); if (/^[A-Z0-9&-]{1,20}$/.test(s)) open(s); };
  return (
    <div className="stack mtf-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Invest · India</span>
        <h1 className="page-title">Margin funding (MTF)</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>How much of each stock is bought with money borrowed from brokers under the margin trading facility, from the exchange's
          daily disclosure, and what your own MTF position costs. Dated facts and arithmetic.</p>
      </div>
      {error ? <div className="banner">{error}</div> : !p ? <Loading label="Reading the margin trading disclosure" /> : (
        <>
          <p className="tiny muted" style={{ margin: 0 }} data-testid="mtf-status">{statusText(p.status, "the margin trading disclosure")}<Info label="Where the numbers come from">{p.note} Source: {p.source}.</Info></p>
          <Market p={p} />
          <form className="row wrap" style={{ gap: 8 }} onSubmit={look}>
            <input className="input" type="search" aria-label="Look up a stock" placeholder="Look up a stock, like RELIANCE" value={q} onChange={(e) => setQ(e.target.value)} style={{ flex: "1 1 200px", maxWidth: 320 }} />
            <button className="btn sm">Show funding</button>
          </form>
          {pick && <OneStock key={pick} symbol={pick} onClose={() => open(null)} />}
          <section className="card stack" style={{ gap: 12 }} aria-labelledby="mtf-mine-h">
            <h2 id="mtf-mine-h" className="h3">Your holdings and watchlist</h2>
            {!p.rows.length ? <p className="small muted">Add Indian stocks to <Link className="link" to="/holdings">My Holdings</Link> or your <Link className="link" to="/research/watchlist">watchlist</Link>, or look one up above.</p> : (
              <div className="table-wrap">
                <table className="nums mtf-table" aria-label="Margin funding for your stocks">
                  <thead><tr><th scope="col" style={{ textAlign: "left" }}>Stock</th><th scope="col">Funded</th>
                    <th scope="col">Of shares issued<Info label="Of shares issued">{p.about.pct_shares}</Info></th><th scope="col">Day</th><th scope="col">30 days</th></tr></thead>
                  <tbody>{p.rows.map((r) => (
                    <tr key={r.symbol} data-stock={r.symbol}>
                      <th scope="row" style={{ textAlign: "left" }}>
                        <a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
                        <div className="tiny muted">{r.held ? "You hold it" : "Watchlist"}</div>
                      </th>
                      {r.funded ? (<>
                        <td>{croreText(r.crore)}</td><td>{plainPct(r.pct_shares, 2)}</td><td className="small">{chg(r.day)}</td><td className="small">{chg(r.d30)}</td>
                      </>) : <td colSpan={4} className="small muted" style={{ textAlign: "left" }}>No margin funding in the newest disclosure</td>}
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
            {!p.full && <p className="tiny muted" style={{ margin: 0 }}>A year of each stock's funding and alerts on a funded level are on the <Link className="link" to="/plans">{p.plan_needed} plan</Link>.</p>}
          </section>
        </>
      )}
      <Calculator />
    </div>
  );
}

export default MarginFundingPage;
