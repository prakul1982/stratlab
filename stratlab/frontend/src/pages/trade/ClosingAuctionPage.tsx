import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { asOf, money, price } from "../../lib/format";
import { upDown } from "../../lib/tradeUi";
import { gapText, LIVE_PHASES, PHASE_TEXT, qtyText, steps, type CasDay, type CasHistory, type CasPosition, type CasStock, type CasView } from "../../lib/closingAuction";
import { Earlier } from "../../components/Earlier";
import { Search } from "../../components/Icons";
import { Badge, Card, CardHead, DataTable, EmptyState, ErrorState, PageHeader, Skeleton, type Column } from "../../components/kit";
import "./trade.css";

/* /trade/closing-auction: India's closing auction session as the exchange publishes it. Through the auction (15:15-15:35)
 * each F&O stock's reference price, band, indicative equilibrium price (IEP) and quantities, and the indices'
 * indicative close; afterwards the final prices (the official closes), and when the market is closed the last auction
 * that ran and when the next one does. On expiry days, the settlement method in force and your paper option positions at
 * the indicative settlement. 60 days of history on Basic. Facts only: the IEP is labelled indicative, and nothing here
 * says what a close will be. Built from the kit (components/kit). */

const REFRESH_MS = 30_000;
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZone: "Asia/Kolkata" }) : null);
const weekday = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" });

/** Where the auction is, and when the next one runs: the status the page leads with. */
function Status({ v }: { v: CasView }) {
  const n = v.next;
  const open = LIVE_PHASES.includes(v.phase);
  return (
    <Card label="Status">
      <div className="k-row">
        <Badge tone={open ? "live" : v.phase === "closed" ? "ok" : "plain"}>{open ? "Auction session" : v.phase === "closed" ? "Auction over for today" : v.trading_day ? "No auction right now" : "Market closed"}</Badge>
        <span className="k-small" data-testid="cas-phase">{PHASE_TEXT[v.phase]}</span>
      </div>
      {n && <p className="k-small" data-testid="cas-next">Next auction window: <b>{n.today ? "today" : weekday(n.day)}, {n.from}–{n.to}</b> India time.</p>}
      {v.day && !v.fresh && <p className="k-note">Showing the auction of {asOf(v.day)}{v.from_stored ? ", from the stored days" : ""}.</p>}
    </Card>
  );
}

function Timeline({ v }: { v: CasView }) {
  const s = steps(v.timetable, v.phase);
  return (
    <Card label="Today's timetable">
      <CardHead level={3} title="Today's timetable" />
      {s.length > 0 && (
        <ol className="cas-steps">
          {s.map((x) => (
            <li key={x.id} className={x.now ? "on" : undefined} aria-current={x.now ? "step" : undefined}>
              <span className="cas-step-time">{x.from}–{x.to}</span><span className="k-small">{x.label}</span>
            </li>
          ))}
        </ol>
      )}
      <p className="k-note">Other stocks trade continuously to {v.timetable.other_continuous_end}; futures and options to {v.timetable.derivatives_close}.
        {" "}Stop-loss and iceberg orders, and limit orders outside the auction's band, are cancelled when continuous trading ends.</p>
    </Card>
  );
}

function Coming({ v }: { v: CasView }) {
  return (
    <Card label="Rule changes coming">
      <CardHead level={3} title="Rule changes coming" info="From SEBI's consultation paper and the exchange's circulars on the closing auction. Facts as published: no date is set for any change, and nothing here changes until a circular sets one." infoLabel="About rule changes" />
      <p className="k-small">{v.expiry.proposal}</p>
      <ul className="k-list muted">
        <li>No change to the 15:15–15:35 timetable or to how expiring contracts settle has a date yet. What is in force: {v.expiry.settlement}</li>
        {v.sources.consultation && <li><a className="link" href={v.sources.consultation} target="_blank" rel="noopener noreferrer">SEBI's consultation paper of 12 Sep 2026</a></li>}
      </ul>
    </Card>
  );
}

function Expiry({ v }: { v: CasView }) {
  const e = v.expiry;
  if (!e.series.length && !e.positions.length) return null;
  type L = CasPosition["legs"][number];
  const cols: Column<L>[] = [
    { key: "leg", header: "Leg", rowHeader: true, cell: (l) => `${l.side === "sell" ? "Sold" : "Bought"} ${l.strike} ${l.opt}` },
    { key: "qty", header: "Qty", numeric: true, cell: (l) => qtyText(l.qty) },
    { key: "fill", header: "Filled at", numeric: true, cell: (l) => price(l.entry, "INR") },
    { key: "val", header: "Value at settlement", numeric: true, cell: (l) => (l.value == null ? "–" : price(l.value, "INR")) },
    { key: "pnl", header: "P&L", numeric: true, cell: (l) => (l.pnl == null ? "–" : <span className={upDown(l.pnl)}>{money(l.pnl, "INR")}</span>) },
  ];
  return (
    <Card label="Expiry today" id="cas-expiry">
      <CardHead level={3} title={e.series.length ? `Expiry today: ${e.series.join(", ")}` : "Your options expiring today"} />
      <p className="k-small">{e.settlement}</p>
      {e.positions.map((p) => (
        <div key={p.session} className="k-stack" data-cas-position={p.session}>
          <p className="k-small"><Link className="link" to={`/options/s/${p.session}`}><b>{p.name}</b></Link>
            {" "}at {p.settle_on == null ? "no price yet" : price(p.settle_on, "INR")} ({p.basis}, indicative)</p>
          <DataTable label={`${p.name}: open legs at the indicative settlement`} columns={cols} rows={p.legs} rowKey={(l) => l.sym} />
          <p className="k-note">Open legs {p.open_pnl == null ? "–" : money(p.open_pnl, "INR")} before charges; legs already closed {money(p.closed_pnl, "INR")}.
            Worked out on the indicative price, which changes until the auction ends.</p>
        </div>
      ))}
    </Card>
  );
}

function Indices({ v }: { v: CasView }) {
  if (!v.indices.length) return null;
  const done = v.phase === "closed" || !!v.from_stored;
  const cols: Column<CasView["indices"][number]>[] = [
    { key: "name", header: "Index", rowHeader: true, cell: (i) => <b>{i.name}</b> },
    { key: "value", header: done ? "Close" : "Value", numeric: true, cell: (i) => (i.value == null ? "–" : price(i.value)) },
    { key: "ind", header: "Indicative close", numeric: true, cell: (i) => (i.indicative == null ? "–" : price(i.indicative)) },
    { key: "gap", header: "Gap", numeric: true, cell: (i) => gapText(i.gap) },
    { key: "start", header: "At 15:15", numeric: true, cell: (i) => (i.start == null ? "–" : price(i.start)) },
  ];
  return (
    <Card label="Indices">
      <CardHead level={3} title="Indices" />
      <DataTable label="Indices during the auction" columns={cols} rows={v.indices} rowKey={(i) => i.name} rowAttrs={(i) => ({ "data-cas-index": i.name })} />
      <p className="k-note">An index isn't auctioned. Through the auction its value uses the constituents' last continuous prices, and the
        indicative close their indicative prices; the close comes from their final prices.</p>
    </Card>
  );
}

function Stocks({ v }: { v: CasView }) {
  const [q, setQ] = useState("");
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return t ? v.stocks.filter((r) => r.symbol.includes(t)) : v.stocks;
  }, [v.stocks, q]);
  const shown = rows.slice(0, 40), rest = rows.slice(40);
  const final = v.phase === "closed" || !!v.from_stored;
  const cols: Column<CasStock>[] = [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => <Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link> },
    { key: "ref", header: "Reference (band)", numeric: true, cell: (r) => <>{r.ref == null ? "–" : price(r.ref, "INR")}
      {r.lower != null && r.upper != null && <span className="k-sub-line">{price(r.lower, "INR")}–{price(r.upper, "INR")}</span>}</> },
    { key: "price", header: final ? "Final price" : "IEP", numeric: true, cell: (r) => <>{r.price == null ? "–" : price(r.price, "INR")}<span className="k-sub-line">{r.final_out ? "final" : "indicative"}</span></> },
    { key: "gap", header: "Gap to reference", numeric: true, cell: (r) => gapText(r.gap) },
    { key: "qty", header: final ? "Quantity" : "Indicative quantity", numeric: true, cell: (r) => qtyText(r.final_out ? r.final_qty : r.ieq) },
    { key: "bid", header: "Bid / ask quantity", numeric: true, cell: (r) => `${qtyText(r.buy_qty)} / ${qtyText(r.sell_qty)}` },
    { key: "imb", header: "Unmatched", numeric: true, cell: (r) => qtyText(r.imbalance) },
  ];
  const attrs = (r: CasStock) => ({ "data-cas-stock": r.symbol });
  return (
    <Card label={`F&O stocks${v.stocks.length ? ` (${v.stocks.length})` : ""}`}>
      <CardHead title={`F&O stocks${v.stocks.length ? ` (${v.stocks.length})` : ""}`} infoLabel="What the numbers are" info={v.note}
        actions={<label className="k-search cas-search"><Search size={16} /><input type="search" aria-label="Find a stock" placeholder="Find a stock" value={q} onChange={(e) => setQ(e.target.value)} /></label>} />
      <p className="k-note">
        {v.as_of ? `As of ${asOf(v.as_of)}` : v.read && !v.from_stored ? `Read at ${time(v.read)} India time` : ""}{v.day && !v.fresh ? `${v.as_of || v.read ? " · " : ""}the auction of ${asOf(v.day)}` : ""}
        {" "}· the widest gap first
      </p>
      {!rows.length ? <EmptyState title={v.stocks.length ? "No stock matches that." : "No auction stored yet"}>{v.stocks.length ? "Try another symbol." : "Each trading day's auction shows here once it has run."}</EmptyState> : (
        <>
          <DataTable label="F&O stocks in the closing auction" columns={cols} rows={shown} rowKey={(r) => r.symbol} rowAttrs={attrs} />
          <Earlier key={q.trim() ? "find" : "all"} label="More stocks" count={rest.length} open={!!q.trim()}>
            <DataTable label="More F&O stocks in the closing auction" columns={cols} rows={rest} rowKey={(r) => r.symbol} rowAttrs={attrs} />
          </Earlier>
        </>
      )}
    </Card>
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
  const cols: Column<CasDay>[] = [
    { key: "day", header: "Day", rowHeader: true, cell: (d) => asOf(d.day) },
    { key: "n", header: "Stocks", numeric: true, cell: (d) => d.stocks },
    { key: "avg", header: "Average gap (either way)", numeric: true, cell: (d) => (d.avg_abs_gap == null ? "–" : `${d.avg_abs_gap.toFixed(2)}%`) },
    { key: "ud", header: "Above / below", numeric: true, cell: (d) => `${d.up} / ${d.down}` },
    { key: "wide", header: "Widest", numeric: true, cell: (d) => (d.widest ? <>{d.widest.symbol} {gapText(d.widest.gap)}</> : "–") },
    { key: "n50", header: "NIFTY 50 close", numeric: true, cell: (d) => { const n50 = d.indices.find((i) => i.name === "NIFTY 50"); return n50 ? <>{n50.close == null ? "–" : price(n50.close)}<span className="k-sub-line">{gapText(n50.gap)} from 15:15</span></> : "–"; } },
  ];
  const attrs = (d: CasDay) => ({ "data-cas-day": d.day });
  return (
    <Card label="Past auctions">
      <CardHead level={3} title="Past auctions" />
      {!v.history.allowed ? (
        <p className="k-small">60 days of auction closes against the reference price, and each index's close against its value at 15:15, are on the {v.history.plan} plan. <Link className="link" to="/plans">See the {v.history.plan} plan</Link></p>
      ) : error ? <ErrorState title="The history couldn't be read">{error}</ErrorState> : !h ? <Skeleton label="Reading past auctions" /> : !h.days.length ? (
        <EmptyState title="No auctions stored yet">Each trading day's auction is stored after 15:40.</EmptyState>
      ) : (
        <>
          <p className="k-note">Each day: the final prices against the reference prices (VWAP of 15:00–15:15).</p>
          <DataTable label="Past auctions" columns={cols} rows={recent} rowKey={(d) => d.day} rowAttrs={attrs} />
          <Earlier label="Earlier auctions" count={older.length}>
            <DataTable label="Earlier auctions" columns={cols} rows={older} rowKey={(d) => d.day} rowAttrs={attrs} />
          </Earlier>
        </>
      )}
    </Card>
  );
}

export function ClosingAuctionPage() {
  const [v, setV] = useState<CasView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);

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
  }, [again]);

  return (
    <div className="k-page cas-page">
      <PageHeader eyebrow="Trade · F&O desk" title="Closing auction" asOf={v?.as_of ?? v?.day}
        lede="Since 3 Aug 2026, stocks with futures and options close through an auction from 15:15 to 15:35. Each stock's reference price, its indicative price through the auction and its final price, which is the official close. Facts, not advice." />
      {error ? <ErrorState title="The closing auction couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !v ? <Card><Skeleton label="Reading the closing auction" /></Card> : (
        <>
          <Status v={v} />
          <Expiry v={v} />
          <div className="k-two">
            <Timeline v={v} />
            <Indices v={v} />
          </div>
          <Stocks v={v} />
          <History v={v} />
          <Coming v={v} />
          <p className="k-note">Rules: SEBI circular of 16 Jan 2026 and the exchange's circulars of 29 May 2026 on the closing auction. The same timetable
            runs StratLab's paper trading: F&amp;O stocks stop continuous fills at 15:15, and a square-off after that fills at the auction's closing price.</p>
        </>
      )}
    </div>
  );
}
