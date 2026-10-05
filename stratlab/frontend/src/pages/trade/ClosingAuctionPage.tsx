import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { asOf, money, price } from "../../lib/format";
import { gapText, LIVE_PHASES, PHASE_TEXT, qtyText, steps, type CasHistory, type CasStock, type CasView } from "../../lib/closingAuction";
import { Empty, Info, Loading } from "../../components/ui";
import { Earlier } from "../../components/Earlier";

/* /trade/closing-auction: India's closing auction session as the exchange publishes it. Through the auction (15:15-15:35)
 * each F&O stock's reference price, band, indicative equilibrium price (IEP) and quantities, and the indices'
 * indicative close; afterwards the final prices (the official closes). On expiry days, the settlement method in force
 * and your paper option positions at the indicative settlement. 60 days of history on Basic. Facts only: the IEP is
 * labelled indicative, and nothing here says what a close will be. */

const REFRESH_MS = 30_000;
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }) : null);

function Timeline({ v }: { v: CasView }) {
  const s = steps(v.timetable, v.phase);
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="cas-time-h">
      <h2 id="cas-time-h" className="h3">Today's timetable</h2>
      <p className="small" data-testid="cas-phase">{PHASE_TEXT[v.phase]}</p>
      {s.length > 0 && (
        <ol className="cas-steps">
          {s.map((x) => (
            <li key={x.id} className={x.now ? "on" : undefined} aria-current={x.now ? "step" : undefined}>
              <span className="cas-step-time">{x.from}–{x.to}</span><span className="small">{x.label}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="tiny muted">Other stocks trade continuously to {v.timetable.other_continuous_end}; futures and options to {v.timetable.derivatives_close}.
        {" "}Stop-loss and iceberg orders, and limit orders outside the auction's band, are cancelled when continuous trading ends.</p>
    </section>
  );
}

function Expiry({ v }: { v: CasView }) {
  const e = v.expiry;
  if (!e.series.length && !e.positions.length) return null;
  return (
    <section className="card stack cas-expiry" style={{ gap: 10 }} aria-labelledby="cas-exp-h">
      <h2 id="cas-exp-h" className="h3">{e.series.length ? `Expiry today: ${e.series.join(", ")}` : "Your options expiring today"}</h2>
      <p className="small">{e.settlement}</p>
      <p className="tiny muted">{e.proposal}</p>
      {e.positions.map((p) => (
        <div key={p.session} className="stack" style={{ gap: 6 }} data-cas-position={p.session}>
          <p className="small"><Link className="link" to={`/options/s/${p.session}`}><b>{p.name}</b></Link>
            {" "}at {p.settle_on == null ? "no price yet" : price(p.settle_on, "INR")} ({p.basis}, indicative)</p>
          <div className="table-wrap">
            <table className="cas-table" aria-label={`${p.name}: open legs at the indicative settlement`}>
              <thead><tr><th style={{ textAlign: "left" }}>Leg</th><th>Qty</th><th>Filled at</th><th>Value at settlement</th><th>P&amp;L</th></tr></thead>
              <tbody>
                {p.legs.map((l) => (
                  <tr key={l.sym}>
                    <td style={{ textAlign: "left" }}>{l.side === "sell" ? "Sold" : "Bought"} {l.strike} {l.opt}</td>
                    <td className="num">{qtyText(l.qty)}</td><td className="num">{price(l.entry, "INR")}</td>
                    <td className="num">{l.value == null ? "–" : price(l.value, "INR")}</td><td className="num">{l.pnl == null ? "–" : money(l.pnl, "INR")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="tiny muted">Open legs {p.open_pnl == null ? "–" : money(p.open_pnl, "INR")} before charges; legs already closed {money(p.closed_pnl, "INR")}.
            Worked out on the indicative price, which changes until the auction ends.</p>
        </div>
      ))}
    </section>
  );
}

function Indices({ v }: { v: CasView }) {
  if (!v.indices.length) return null;
  const done = v.phase === "closed";
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="cas-idx-h">
      <h2 id="cas-idx-h" className="h3">Indices</h2>
      <div className="table-wrap">
        <table className="cas-table" aria-label="Indices during the auction">
          <thead><tr><th style={{ textAlign: "left" }}>Index</th><th>{done ? "Close" : "Value"}</th><th>Indicative close</th><th>Gap</th><th>At 15:15</th></tr></thead>
          <tbody>
            {v.indices.map((i) => (
              <tr key={i.name} data-cas-index={i.name}>
                <td style={{ textAlign: "left" }}><b>{i.name}</b></td>
                <td className="num">{i.value == null ? "–" : price(i.value)}</td>
                <td className="num">{i.indicative == null ? "–" : price(i.indicative)}</td>
                <td className="num">{gapText(i.gap)}</td>
                <td className="num">{i.start == null ? "–" : price(i.start)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny muted">An index isn't auctioned. Through the auction its value uses the constituents' last continuous prices, and the
        indicative close their indicative prices; the close comes from their final prices.</p>
    </section>
  );
}

function StockRow({ r }: { r: CasStock }) {
  return (
    <tr data-cas-stock={r.symbol}>
      <td style={{ textAlign: "left" }}><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link></td>
      <td className="num">{r.ref == null ? "–" : price(r.ref, "INR")}
        {r.lower != null && r.upper != null && <div className="tiny muted">{price(r.lower, "INR")}–{price(r.upper, "INR")}</div>}</td>
      <td className="num">{r.price == null ? "–" : price(r.price, "INR")}<div className="tiny muted">{r.final_out ? "final" : "indicative"}</div></td>
      <td className="num">{gapText(r.gap)}</td>
      <td className="num">{qtyText(r.final_out ? r.final_qty : r.ieq)}</td>
      <td className="num">{qtyText(r.imbalance)}</td>
    </tr>
  );
}

function Stocks({ v }: { v: CasView }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return t ? v.stocks.filter((r) => r.symbol.includes(t)) : v.stocks;
  }, [v.stocks, q]);
  const shown = rows.slice(0, 40), rest = rows.slice(40);
  const head = (
    <thead><tr><th style={{ textAlign: "left" }}>Stock</th><th>Reference (band)</th><th>{v.phase === "closed" ? "Final price" : "IEP"}</th>
      <th>Gap to reference</th><th>{v.phase === "closed" ? "Quantity" : "Indicative quantity"}</th><th>Unmatched</th></tr></thead>
  );
  return (
    <section className="card stack" style={{ gap: 12 }} aria-labelledby="cas-stocks-h">
      <div className="row wrap" style={{ gap: 10, alignItems: "center", justifyContent: "space-between" }}>
        <h2 id="cas-stocks-h" className="h3">F&amp;O stocks{v.stocks.length ? ` (${v.stocks.length})` : ""}</h2>
        <input className="input cas-search" type="search" aria-label="Find a stock" placeholder="Find a stock" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>
        {v.as_of ? `As of ${asOf(v.as_of)}` : v.read ? `Read at ${time(v.read)} India time` : ""}{v.day && !v.fresh ? ` · the auction of ${asOf(v.day)}` : ""}
        {" "}· the widest gap first<Info label="What the numbers are">{v.note}</Info>
      </p>
      {!rows.length ? <p className="small muted">{v.stocks.length ? "No stock matches that." : "Nothing published yet."}</p> : (
        <>
          <div className="table-wrap"><table className="cas-table" aria-label="F&O stocks in the closing auction">{head}
            <tbody>{shown.map((r) => <StockRow key={r.symbol} r={r} />)}</tbody></table></div>
          <Earlier key={q.trim() ? "find" : "all"} label="More stocks" count={rest.length} open={!!q.trim()}>
            <div className="table-wrap"><table className="cas-table" aria-label="More F&O stocks in the closing auction">{head}
              <tbody>{rest.map((r) => <StockRow key={r.symbol} r={r} />)}</tbody></table></div>
          </Earlier>
        </>
      )}
    </section>
  );
}

function History({ v }: { v: CasView }) {
  const [h, setH] = useState<CasHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!v.history.allowed) return;
    api<CasHistory>("/trade/closing-auction/history").then(setH).catch(() => setError("The history couldn't be read just now."));
  }, [v.history.allowed]);
  const recent = h?.days.slice(0, 5) ?? [], older = h?.days.slice(5) ?? [];
  const day = (d: CasHistory["days"][number]) => {
    const n50 = d.indices.find((i) => i.name === "NIFTY 50");
    return (
      <tr key={d.day} data-cas-day={d.day}>
        <td style={{ textAlign: "left" }}>{asOf(d.day)}</td>
        <td className="num">{d.stocks}</td>
        <td className="num">{d.avg_abs_gap == null ? "–" : `${d.avg_abs_gap.toFixed(2)}%`}</td>
        <td className="num">{d.up} / {d.down}</td>
        <td className="num">{d.widest ? <>{d.widest.symbol} {gapText(d.widest.gap)}</> : "–"}</td>
        <td className="num">{n50 ? <>{n50.close == null ? "–" : price(n50.close)}<div className="tiny muted">{gapText(n50.gap)} from 15:15</div></> : "–"}</td>
      </tr>
    );
  };
  const head = <thead><tr><th style={{ textAlign: "left" }}>Day</th><th>Stocks</th><th>Average gap (either way)</th><th>Above / below</th><th>Widest</th><th>NIFTY 50 close</th></tr></thead>;
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="cas-hist-h">
      <h2 id="cas-hist-h" className="h3">Past auctions</h2>
      {!v.history.allowed ? (
        <p className="small">60 days of auction closes against the reference price, and each index's close against its value at 15:15, are on the {v.history.plan} plan. <Link className="link" to="/plans">See the {v.history.plan} plan</Link></p>
      ) : error ? <p className="small muted">{error}</p> : !h ? <Loading label="Reading past auctions" /> : !h.days.length ? (
        <Empty title="No auctions stored yet">Each trading day's auction is stored after 15:40.</Empty>
      ) : (
        <>
          <p className="tiny muted" style={{ margin: 0 }}>Each day: the final prices against the reference prices (VWAP of 15:00–15:15).</p>
          <div className="table-wrap"><table className="cas-table" aria-label="Past auctions">{head}<tbody>{recent.map(day)}</tbody></table></div>
          <Earlier label="Earlier auctions" count={older.length}>
            <div className="table-wrap"><table className="cas-table" aria-label="Earlier auctions">{head}<tbody>{older.map(day)}</tbody></table></div>
          </Earlier>
        </>
      )}
    </section>
  );
}

export function ClosingAuctionPage() {
  const [v, setV] = useState<CasView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true, timer: number | undefined;
    const load = () => api<CasView>("/trade/closing-auction").then((x) => {
      if (!live) return;
      setV(x);
      setError(null);
      if (LIVE_PHASES.includes(x.phase)) timer = window.setTimeout(load, REFRESH_MS);
    }).catch(() => { if (live) setError("The closing auction couldn't be read just now. Try again in a minute."); });
    load();
    return () => { live = false; window.clearTimeout(timer); };
  }, []);

  return (
    <div className="stack cas-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Trade · India</span>
        <h1 className="page-title">Closing auction</h1>
        <p className="page-sub" style={{ maxWidth: "70ch" }}>Since 3 Aug 2026, stocks with futures and options close through an auction from 15:15 to 15:35. Each stock's
          reference price, its indicative price through the auction and its final price, which is the official close. Facts, not advice.</p>
      </div>
      {error ? <div className="banner">{error}</div> : !v ? <Loading label="Reading the closing auction" /> : (
        <>
          <Expiry v={v} />
          <div className="grid2" style={{ alignItems: "start" }}>
            <Timeline v={v} />
            <Indices v={v} />
          </div>
          <Stocks v={v} />
          <History v={v} />
          <p className="tiny muted">Rules: SEBI circular of 16 Jan 2026 and the exchange's circulars of 29 May 2026 on the closing auction. The same timetable
            runs StratLab's paper trading: F&amp;O stocks stop continuous fills at 15:15, and a square-off after that fills at the auction's closing price.</p>
        </>
      )}
    </div>
  );
}
