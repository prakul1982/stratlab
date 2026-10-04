import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, price, signClass, when } from "../lib/format";
import { HELP } from "../lib/help";
import type { OptionSnapshot } from "../lib/types";
import { ChartEmpty, LineChart } from "../components/Charts";
import { Info, Loading } from "../components/ui";
import { Earlier, splitToday } from "../components/Earlier";
import { contract, OrderList, ordersBetween, ordersSince } from "../components/OrderList";
import { moneyCompact } from "../lib/chartFormat";

const TZ = "Asia/Kolkata";
const inr = (v: number | null | undefined) => money(v, "INR");
const t = (iso: string) => when(iso, TZ, true);

export function OptionsSession() {
  const { sid = "" } = useParams();
  const { fail, refreshMe } = useApp();
  const nav = useNavigate();
  const [snap, setSnap] = useState<OptionSnapshot | null>(null);
  const [shown, setShown] = useState<Set<string>>(new Set());     // closed trades whose orders are open
  const toggle = (k: string) => setShown((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  const load = useCallback(async () => {
    try { setSnap(await api<OptionSnapshot>(`/live/sessions/${sid}`)); } catch (e) { fail(e); }
  }, [sid, fail]);
  useEffect(() => {
    setSnap(null);
    load();
    const h = window.setInterval(() => { if (!document.hidden) load(); }, 3000);
    return () => window.clearInterval(h);
  }, [load]);

  if (!snap) return <Loading label="Connecting to the session" />;
  const running = snap.status === "running";
  const a = snap.account, p = snap.position, s = snap.strategy;
  const { today, earlier } = splitToday(snap.trades, (x) => x.closed, TZ);
  const openOrders = p ? ordersSince(snap.events, p.opened) : [];
  const feed = !running ? "" : !snap.feed_connected ? "Reconnecting to prices" : snap.fresh ? "Live option prices" : "Waiting for the market to open";

  const stop = async () => {
    if (!confirm("Stop this session? Any open paper position is left as it is, and it can't be restarted.")) return;
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); } catch (e) { fail(e); }
  };
  const remove = async () => {
    if (!confirm(`Delete "${snap.name}" and its orders? This can't be undone.`)) return;
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); nav("/options"); } catch (e) { fail(e); }
  };

  const stats: [string, string, number | null][] = [
    ["Open trade, after costs", p ? inr(p.net) : "No open trade", p ? p.net : null],
    ["Today", inr(a.today + (p ? p.net : 0)), a.today + (p ? p.net : 0)],
    ["All closed trades", inr(a.realised), a.realised],
    ["Paper account", inr(a.equity), a.equity - a.capital],
  ];

  return (
    <div className="stack" style={{ gap: 20 }}>
      <Link to="/options" className="small muted">← Options</Link>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">{snap.instrument.underlying} options · {snap.instrument.exchange}{snap.expiry ? ` · expiry ${snap.expiry}` : ""} · started {t(snap.started_at)}</span>
          <h2 className="serif" style={{ fontSize: 34, fontWeight: 400, letterSpacing: "-0.02em" }}>{snap.name}</h2>
        </div>
        <div className="row" style={{ gap: 12 }}>
          {running && <span className="row small" style={{ gap: 8 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: snap.fresh ? "var(--blue)" : "var(--dash)" }} />{feed}<Info>{HELP.optFeed}</Info></span>}
          {running ? <button className="btn danger" onClick={stop}>Stop session</button>
            : <><span className={`badge ${snap.status}`}>{snap.status}</span><button className="btn danger sm" onClick={remove}>Delete</button></>}
        </div>
      </div>
      {!running && snap.stop_reason && <div className="banner">Stopped: {snap.stop_reason}</div>}
      {running && a.halted && <div className="banner">The daily loss cap was hit. No more trades today; it starts again tomorrow.</div>}
      {running && snap.note && !p && <div className="banner">{snap.note}</div>}
      {snap.signal && (
        <div className="card row wrap" style={{ gap: 12, padding: "12px 16px", alignItems: "center" }}>
          <span className="eyebrow">Signal</span>
          <span><b>{snap.signal.name}</b> on {snap.instrument.underlying} {snap.signal.tf} candles</span>
          <span className={`badge ${snap.signal.position === "long" ? "pass" : snap.signal.position === "short" ? "warn" : "skip"}`}>
            {snap.signal.position === "long" ? "Rules long" : snap.signal.position === "short" ? "Rules short" : "Rules flat"}</span>
          {snap.signal.last_candle && <span className="small muted">last candle {new Date(snap.signal.last_candle).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST{snap.signal.price != null ? ` · ${price(snap.signal.price, "INR")}` : ""}</span>}
          {!snap.signal.ok && <span className="small" style={{ color: "var(--orange)" }}>Couldn't fetch the latest candles; retrying.</span>}
        </div>
      )}

      <div className="stats-grid opt-stats">
        {stats.map(([k, v, n]) => <div key={k} className="card"><span className="eyebrow">{k}</span><b className={`mono ${signClass(n)}`} style={{ fontSize: 22 }}>{v}</b></div>)}
      </div>

      <section className="card rules-strip" aria-label="Rules">
        <span className="eyebrow">Rules</span>
        <ul>
          <li>{s.legs.map((l) => `${l.side === "sell" ? "Sell" : "Buy"} ${l.offset === 0 ? "ATM" : `${l.offset}${s.offsetUnit === "points" ? " pts" : ""} ${l.offset > 0 ? "OTM" : "ITM"}`} ${l.opt}${l.lots > 1 ? ` × ${l.lots}` : ""}`).join(", ")}</li>
          <li>Enter {s.timing.entry}–{s.timing.lastEntry}, up to {s.timing.maxEntries} a day{s.timing.cooldown ? `, ${s.timing.cooldown} min apart` : ""}</li>
          <li>Square off {s.timing.squareoff}</li>
          {s.risk.stopType !== "none" && <li>Stop at {s.risk.stopType === "amount" ? inr(s.risk.stop) : `${s.risk.stop}% of premium`}</li>}
          {s.risk.tgtType !== "none" && <li>Target {s.risk.tgtType === "amount" ? inr(s.risk.tgt) : `${s.risk.tgt}% of premium`}</li>}
          {s.risk.trailAfter > 0 && s.risk.trailBy > 0 && <li>Trail after {inr(s.risk.trailAfter)} by {inr(s.risk.trailBy)}</li>}
          {s.risk.legStopPct > 0 && <li>Stop a sold leg at +{s.risk.legStopPct}%</li>}
          {s.risk.dailyLoss > 0 && <li>Daily loss cap {inr(s.risk.dailyLoss)}</li>}
          {s.recenter.enabled && <li>Re-centre every {s.recenter.every} min after a {s.recenter.threshold}-strike move ({s.recenter.roll === "all" ? "every leg" : "sold legs"})</li>}
          <li>{s.sizing.mode === "margin" ? `As much as margin allows on ${inr(s.sizing.capital)}` : `${s.sizing.lots} unit${s.sizing.lots === 1 ? "" : "s"}`}</li>
        </ul>
      </section>

      <section className="card stack" style={{ gap: 12 }} aria-labelledby="o-today">
        <div className="spread"><h3 id="o-today" className="h3">Today</h3>
          {snap.spot != null && <span className="mono small">{snap.instrument.underlying} {price(snap.spot, "INR")}</span>}</div>
        {!p ? <p className="muted">{flatLine(snap, today.length)}</p> : (
          <>
            <p className="small muted">Open since {t(p.opened)} with {snap.instrument.underlying} at {p.spot_in.toLocaleString("en-IN")} (centre {p.center}). {p.credit >= 0 ? "Premium collected" : "Premium paid"} {inr(Math.abs(p.credit))}.
              {" "}Best {inr(p.best)}, worst {inr(p.worst)} so far.{p.rolls ? ` Re-centred ${p.rolls} time${p.rolls === 1 ? "" : "s"}.` : ""} Costs so far {inr(p.costs)} over {p.orders} orders.</p>
            <div className="table-wrap">
              <table>
                <thead><tr><th>Leg</th><th>Side</th><th>Qty</th><th>Entry</th><th>Now<Info>{HELP.optMark}</Info></th><th>P&amp;L</th></tr></thead>
                <tbody>{snap.legs.map((l, i) => (
                  <tr key={i} style={{ opacity: l.open ? 1 : 0.55 }}>
                    <td title={l.sym}>{contract(l)}{!l.open && " (closed)"}</td><td>{l.side === "sell" ? "Sold" : "Bought"}</td><td className="mono">{l.qty.toLocaleString("en-IN")}</td>
                    <td className="mono">{price(l.entry, "INR")}</td><td className="mono">{price(l.mark, "INR")}</td>
                    <td className={`mono ${signClass(l.pnl)}`}>{inr(l.pnl)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <Earlier label="Orders in this trade" count={openOrders.length} className="in-card">
              <OrderList events={openOrders} cur="INR" tz={TZ} />
            </Earlier>
          </>
        )}
        {today.length > 0 && (
          <div className="stack" style={{ gap: 6 }}>
            {p && <span className="eyebrow" style={{ marginTop: 6 }}>Closed today</span>}
            <TradeList rows={today} events={snap.events} shown={shown} toggle={toggle} />
          </div>
        )}
      </section>

      {earlier.length > 0 && (
        <section className="card" aria-label="Earlier trades">
          <Earlier label="Earlier trades" count={earlier.length} note={<Totals rows={earlier} />}>
            <TradeList rows={earlier} events={snap.events} shown={shown} toggle={toggle} />
          </Earlier>
        </section>
      )}

      <section className="card stack" style={{ gap: 10 }}>
        <h3 className="h3">Paper equity</h3>
        {snap.equity_curve.length > 1 ? (
          <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((x) => t(x.t))} height={170} times={snap.equity_curve.map((x) => x.t)} tz={TZ}
            format={(v) => inr(v)} axisFormat={(v) => moneyCompact(v, "INR")} baseline={a.capital}
            lines={[{ label: "Account", values: snap.equity_curve.map((x) => x.eq), color: "var(--series-1)", width: 2 }]} />
        ) : <ChartEmpty height={170}>Fills in minute by minute while the market is open.</ChartEmpty>}
      </section>
    </div>
  );
}

type Trade = OptionSnapshot["trades"][number];
type OrderEvent = OptionSnapshot["events"][number];

/** "05 Oct, 09:30–11:30", or both dates when a trade was held overnight. */
function span(x: Trade): string {
  const a = t(x.opened), b = t(x.closed), [da] = a.split(", "), [db, tb] = b.split(", ");
  return da === db ? `${a}–${tb}` : `${a} → ${b}`;
}

/** Closed trades, newest first, one line each; tapping one opens its orders under it. */
function TradeList({ rows, events, shown, toggle }: { rows: Trade[]; events: OrderEvent[]; shown: Set<string>; toggle: (k: string) => void }) {
  return (
    <ul className="trade-lines">{[...rows].reverse().map((x) => {
      const key = x.opened + x.closed, open = shown.has(key);
      const orders = ordersBetween(events, x.opened, x.closed);
      return (
        <li key={key} className={open ? "open" : undefined}>
          <button className="trade-line" aria-expanded={open} disabled={!orders.length} onClick={() => toggle(key)}
            aria-label={`${open ? "Hide" : "Show"} the orders of the trade opened ${t(x.opened)}`}>
            <span className="chev" aria-hidden>{open ? "▾" : "▸"}</span>
            <span className="trade-main">
              <span className="trade-when">{span(x)}</span>
              <span className="small muted">{x.why}{x.rolls ? `, ${x.rolls} roll${x.rolls === 1 ? "" : "s"}` : ""} · premium {inr(x.credit)} · before costs {inr(x.gross)} · costs {inr(x.costs)}</span>
            </span>
            <b className={`trade-pnl mono ${signClass(x.pnl)}`}>{inr(x.pnl)}</b>
          </button>
          {open && <div className="trade-orders"><OrderList events={orders} cur="INR" tz={TZ} /></div>}
        </li>
      );
    })}</ul>
  );
}

/** "12 trades · −₹56,346 after costs · 4 won": the folded trades added up. */
function Totals({ rows }: { rows: Trade[] }) {
  const pnl = rows.reduce((n, x) => n + x.pnl, 0), won = rows.filter((x) => x.pnl > 0).length;
  return <><span className={signClass(pnl)}>{inr(pnl)}</span> after costs · {won} won</>;
}

/** What a flat session is waiting for, in one line: "No trades today. Next entry 09:30." */
function flatLine(snap: OptionSnapshot, closedToday: number): string {
  const s = snap.strategy, a = snap.account;
  const none = closedToday ? "Nothing open." : "No trades today.";
  if (snap.status !== "running") return none;
  if (a.halted || a.entries_today >= s.timing.maxEntries) return `${none} Done for today; next entry ${s.timing.entry} on the next market day.`;
  if (s.signal) return `${none} Enters when ${s.signal.name} signals, from ${s.timing.entry}.`;
  const now = new Date();
  const hm = now.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: TZ });
  const wd = now.toLocaleDateString("en-GB", { weekday: "short", timeZone: TZ });
  if (wd === "Sat" || wd === "Sun" || hm > s.timing.lastEntry) return `${none} Next entry ${s.timing.entry} on the next market day.`;
  return hm < s.timing.entry ? `${none} Next entry ${s.timing.entry}.` : `${none} Entries open until ${s.timing.lastEntry}.`;
}
