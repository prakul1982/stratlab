import { money, price, qty, signClass, TF_NAME, tzOf, when } from "../lib/format";
import { HELP } from "../lib/help";
import { ChartEmpty, LineChart } from "./Charts";
import { moneyCompact } from "../lib/chartFormat";
import { Info } from "./ui";
import { Earlier, splitToday } from "./Earlier";
import { OrderList } from "./OrderList";

export interface GroupSnapshot {
  id: string; name: string; kind: "group"; status: "running" | "stopped" | "paused"; stop_reason?: string | null;
  instrument: { symbol: string; market: string; currency?: string; tz?: string; maxOpen?: number };
  strategy: { tf: string; risk: { capital: number } }; started_at: string; last_tick_at?: string | null; feed_connected?: boolean;
  members: { symbol: string; id: string; price: number; trades: number; pnl: number; skipped?: number; spread?: number | null;
    position: { side: "long" | "short"; qty: number; entry: number; unrealised: number; stop: number | null; target: number | null } | null }[];
  skipped: string[]; events: { t: string; side: "buy" | "sell"; qty: number; px: number; why: string; sym: string; pnl?: number }[];
  equity_curve: { t: string; eq: number }[];
  account: { capital: number; equity: number; realised: number; unrealised: number; open: number; max_open: number; halted: boolean;
    today: number; trades: number; wins: number; skipped?: { spread: number; price: number } };
  fast?: { ticks?: boolean; maxSpreadPct?: number; minPrice?: number };
}

export function GroupSession({ snap, onStop, onDelete }: { snap: GroupSnapshot; onStop: () => void; onDelete: () => void }) {
  const running = snap.status === "running";
  const cur = snap.instrument.currency || (snap.instrument.market === "IN" ? "INR" : "");
  const tz = tzOf(snap.instrument as never);
  const a = snap.account;
  const holding = snap.members.filter((m) => m.position);
  const { today, earlier } = splitToday(snap.events, (e) => e.t, tz);     // today's orders in view, the earlier ones folded
  const closedPnl = earlier.reduce((n, e) => n + (e.pnl ?? 0), 0);
  const feed = !running ? "" : snap.feed_connected ? (snap.last_tick_at ? "Live prices" : "Waiting for the market to open") : "Reconnecting to prices";
  const stats: [string, string, number | null][] = [
    ["Open positions", `${a.open} of ${a.max_open}`, null],
    ["Today", money(a.today, cur), a.today],
    ["Closed trades", `${money(a.realised, cur)} · ${a.trades}`, a.realised],
    ["Paper account", money(a.equity, cur), a.equity - a.capital],
  ];
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">{snap.instrument.symbol} · {TF_NAME[snap.strategy.tf]} candles · started {when(snap.started_at, tz, true)}</span>
          <h2 className="serif" style={{ fontSize: 34, fontWeight: 400, letterSpacing: "-0.02em" }}>{snap.name}</h2>
        </div>
        <div className="row" style={{ gap: 12 }}>
          {running && <span className="row small" style={{ gap: 8 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: snap.feed_connected && snap.last_tick_at ? "var(--blue)" : "var(--dash)" }} />{feed}<Info>{HELP.feed}</Info></span>}
          {running ? <button className="btn danger" onClick={onStop}>Stop session</button>
            : <><span className={`badge ${snap.status}`}>{snap.status}</span><button className="btn danger sm" onClick={onDelete}>Delete</button></>}
        </div>
      </div>
      {!running && snap.stop_reason && <div className="banner">Stopped: {snap.stop_reason}</div>}
      {running && a.halted && <div className="banner">The group's daily loss cap was hit: everything was closed and nothing new opens until tomorrow.</div>}
      {snap.skipped.length > 0 && <p className="hint">Left out (not enough live history): {snap.skipped.join(" · ")}</p>}
      {(() => {
        const f = snap.fast || {}, sk = a.skipped || { spread: 0, price: 0 };
        const on = [f.ticks && "faster entries on the live price", f.maxSpreadPct && `spread limit ${f.maxSpreadPct}%`, f.minPrice && `nothing under ${price(f.minPrice, cur)}`].filter(Boolean);
        if (!on.length) return null;
        const skipped = [sk.spread && `${sk.spread} for a wide or unknown spread`, sk.price && `${sk.price} for price`].filter(Boolean);
        return <p className="hint">On: {on.join(" · ")}.{skipped.length ? ` Entries skipped: ${skipped.join(", ")}.` : ""}</p>;
      })()}
      <div className="stats-grid opt-stats">
        {stats.map(([k, v, n]) => <div key={k} className="card"><span className="eyebrow">{k}</span><b className={`mono ${signClass(n)}`} style={{ fontSize: 20 }}>{v}</b></div>)}
      </div>
      <div className="nb-grid" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 16, minWidth: 0 }}>
          <section className="card stack" style={{ gap: 10 }}>
            <h3 className="h3">Open positions</h3>
            {holding.length === 0 ? <p className="muted">{running ? "None right now. Positions open as the rules fire, up to " + a.max_open + " at once." : "None."}</p> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Now</th><th>Stop</th><th>Target</th><th>P&amp;L</th></tr></thead>
                <tbody>{holding.map((m) => (
                  <tr key={m.id}><td className="mono">{m.symbol}</td><td>{m.position!.side === "short" ? "Short" : "Long"}</td><td className="mono">{qty(m.position!.qty)}</td>
                    <td className="mono">{price(m.position!.entry, cur)}</td><td className="mono">{price(m.price, cur)}</td>
                    <td className="mono">{m.position!.stop ? price(m.position!.stop, cur) : "–"}</td><td className="mono">{m.position!.target ? price(m.position!.target, cur) : "–"}</td>
                    <td className={`mono ${signClass(m.position!.unrealised)}`}>{money(m.position!.unrealised, cur)}</td></tr>
                ))}</tbody>
              </table></div>
            )}
          </section>
          <section className="card stack" style={{ gap: 10 }}>
            <h3 className="h3">Paper equity</h3>
            {snap.equity_curve.length > 1 ? (
              <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((p) => when(p.t, tz, true))} height={170} times={snap.equity_curve.map((p) => p.t)} tz={tz}
                format={(v) => money(v, cur)} axisFormat={(v) => moneyCompact(v, cur ?? "INR")} baseline={a.capital}
                lines={[{ label: "Account", values: snap.equity_curve.map((p) => p.eq), color: "var(--series-1)", width: 2 }]} />
            ) : <ChartEmpty height={170}>Fills in as candles close.</ChartEmpty>}
          </section>
          {snap.members.length > 0 && (
            <details className="card">
              <summary className="h3">Every member ({snap.members.length})</summary>
              <div className="table-wrap" style={{ marginTop: 10 }}><table>
                <thead><tr><th>Symbol</th><th>Price</th>{snap.fast?.maxSpreadPct ? <th>Spread</th> : null}<th>Trades</th><th>Skipped</th><th>Closed P&amp;L</th></tr></thead>
                <tbody>{snap.members.map((m) => (
                  <tr key={m.id}><td className="mono">{m.symbol}</td><td className="mono">{price(m.price, cur)}</td>
                    {snap.fast?.maxSpreadPct ? <td className="mono">{m.spread == null ? "–" : `${m.spread.toFixed(2)}%`}</td> : null}
                    <td className="mono">{m.trades}</td><td className="mono">{m.skipped || "–"}</td>
                    <td className={`mono ${signClass(m.pnl)}`}>{money(m.pnl, cur)}</td></tr>
                ))}</tbody>
              </table></div>
            </details>
          )}
        </div>
        <section className="card stack" style={{ gap: 10, alignSelf: "start" }} aria-labelledby="g-orders">
          <h3 id="g-orders" className="h3">Orders today</h3>
          {today.length ? <OrderList events={today} cur={cur} tz={tz} newest />
            : <p className="muted small">{snap.events.length ? "No orders today." : "None yet."}</p>}
          <Earlier label="Earlier orders" count={earlier.length} className="in-card"
            note={<><span className={signClass(closedPnl)}>{money(closedPnl, cur)}</span> on closed trades</>}>
            <OrderList events={earlier} cur={cur} tz={tz} newest />
          </Earlier>
        </section>
      </div>
    </div>
  );
}
