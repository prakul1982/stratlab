import { RiskOverview } from "../components/RiskOverview";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, moneyShort, pct, price, priceAxis, qty, signClass, TF_NAME, tzOf, when } from "../lib/format";
import type { LiveRow, LiveSnapshot } from "../lib/types";
import { LineChart, type Marker } from "../components/Charts";
import { Empty, Info, Loading } from "../components/ui";
import { HELP } from "../lib/help";
import { GroupSession, type GroupSnapshot } from "../components/GroupSession";
import { SurvBadges, survRegion } from "../components/Surveillance";
import { Earlier, splitToday } from "../components/Earlier";
import { OrderList, type PaperOrder } from "../components/OrderList";

function SessionView({ sid, onStopped, onDeleted }: { sid: string; onStopped: () => void; onDeleted: () => void }) {
  const { fail, refreshMe } = useApp();
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);

  const load = useCallback(async () => {
    try { setSnap(await api<LiveSnapshot>(`/live/sessions/${sid}`)); } catch (e) { fail(e); }
  }, [sid, fail]);

  useEffect(() => {
    setSnap(null);
    load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 3000);
    return () => window.clearInterval(t);
  }, [load]);

  if (!snap) return <Loading label="Connecting to the session" />;
  if ((snap as unknown as GroupSnapshot).kind === "group") {
    const g = snap as unknown as GroupSnapshot;
    return <GroupSession snap={g}
      onStop={async () => { if (!confirm("Stop this session? Open paper positions are left as they are, and it can't be restarted.")) return;
        try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); } }}
      onDelete={async () => { if (!confirm(`Delete "${g.name}" and its orders? This can't be undone.`)) return;
        try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); } }} />;
  }
  const running = snap.status === "running";
  const cur = snap.instrument.currency || (snap.instrument.market === "IN" || !snap.instrument.market ? "INR" : "");
  const tz = tzOf(snap.instrument);
  const intraday = snap.strategy.tf !== "1d";
  const a = snap.account;
  const idx = new Map(snap.bars.map((b, i) => [b.t, i]));
  const markers: Marker[] = snap.events.map((e) => ({ i: idx.get(e.t) ?? -1, side: e.side })).filter((m) => m.i >= 0);
  const alwaysOpen = snap.instrument.market === "CRYPTO";
  // orders: today's in view, the earlier ones folded
  const orders: PaperOrder[] = snap.events.map((e) => ({ ...e, sym: snap.instrument.symbol }));
  const { today, earlier } = splitToday(orders, (e) => e.t, tz);
  const closedPnl = earlier.reduce((n, e) => n + (e.pnl ?? 0), 0);
  const feed = !running ? "" : snap.feed_connected
    ? (snap.last_tick_at ? "Live prices" : alwaysOpen ? "Fetching the latest prices" : "Waiting for the market to open")
    : "Reconnecting to prices";

  const stop = async () => {
    if (!confirm("Stop this session? Open paper positions are left as they are, and it can't be restarted.")) return;
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); }
  };

  const remove = async () => {
    if (!confirm(`Delete "${snap.name}" and its orders? This can't be undone.`)) return;
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); }
  };

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">{snap.instrument.symbol} · {TF_NAME[snap.strategy.tf]} candles · started {when(snap.started_at, tz, true)}</span>
          <SurvBadges region={survRegion(snap.instrument)} symbol={snap.instrument.symbol} />
          <h2 className="serif" style={{ fontSize: 34, fontWeight: 400, letterSpacing: "-0.02em" }}>{snap.name}</h2>
        </div>
        <div className="row" style={{ gap: 12 }}>
          {running && <span className="row small" style={{ gap: 8 }}><span style={{ width: 9, height: 9, borderRadius: "50%", background: snap.feed_connected && snap.last_tick_at ? "var(--blue)" : "var(--dash)" }} />{feed}<Info>{HELP.feed}</Info></span>}
          {running ? <button className="btn danger" onClick={stop}>Stop session</button>
            : <><span className={`badge ${snap.status}`}>{snap.status}</span><button className="btn danger sm" onClick={remove}>Delete</button></>}
        </div>
      </div>
      {!running && snap.stop_reason && <div className="banner">Stopped: {snap.stop_reason}</div>}

      <div className="nb-grid" style={{ gap: 16 }}>
        <div className="stack" style={{ gap: 16, minWidth: 0 }}>
          <section className="card stack" style={{ gap: 10 }}>
            <div className="spread"><h3 className="h3">Live chart</h3>
              {snap.last_price != null && <span className="mono small">{snap.instrument.symbol} {price(snap.last_price, cur)}</span>}</div>
            {snap.bars.length ? (
              <LineChart ariaLabel="Recent candles with paper trades" labels={snap.bars.map((b) => when(b.t, tz, intraday))} height={300}
                format={(x) => price(x, cur)} axisFormat={(x) => priceAxis(x, cur)} markers={markers}
                levels={[...(a.stop ? [{ v: a.stop, color: "var(--orange)", label: "Stop" }] : []), ...(a.target ? [{ v: a.target, color: "var(--blue)", label: "Target" }] : [])]}
                lines={[{ label: "Close", values: snap.bars.map((b) => b.c), color: "var(--ink)", width: 1.6 },
                  ...Object.entries(snap.overlays).map(([k, v], i) => ({ label: k, values: v, color: ["var(--blue)", "var(--orange)", "var(--muted)"][i % 3], width: 1.2 }))]} />
            ) : <p className="muted">The chart fills in as candles close.</p>}
          </section>
          <section className="card stack" style={{ gap: 10 }}>
            <h3 className="h3 row" style={{ gap: 0 }}>Paper equity<Info>{HELP.equityLive}</Info></h3>
            {snap.equity_curve.length > 1 ? (
              <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((p) => when(p.t, tz, intraday))} height={160}
                format={(x) => moneyShort(x, cur)} baseline={a.capital} lines={[{ label: "Equity", values: snap.equity_curve.map((p) => p.eq), color: "var(--blue)", width: 2 }]} />
            ) : <p className="muted small">Your equity curve starts after the first closed candle.</p>}
          </section>
        </div>
        <div className="stack" style={{ gap: 16 }}>
          <section className="card stack" style={{ gap: 0 }}>
            <div className="spread" style={{ marginBottom: 8 }}><h3 className="h3">Account</h3><span className="small muted">Fake money</span></div>
            {([
              ["Equity", money(a.equity, cur), null, HELP.equityLive],
              ["Return", pct((a.equity / a.capital - 1) * 100, 2), a.equity - a.capital, null],
              ["Cash", money(a.cash, cur), null, HELP.cash],
              ["Open position", a.qty ? `${qty(a.qty)} at ${price(a.entry ?? 0, cur)}` : "None", null, null],
              ["Unrealised P&L", money(a.unrealised, cur), a.unrealised, HELP.unrealised],
              ["Realised P&L", money(a.realised, cur), a.realised, HELP.realised],
              ["Closed trades", a.trades ? `${a.trades} (${a.wins} won)` : "0", null, null],
            ] as [string, string, number | null, string | null][]).map(([k, v, sign, help]) => (
              <div key={k} className="spread" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                <span className="muted row" style={{ gap: 0 }}>{k}{help && <Info label={`What is ${k}?`}>{help}</Info>}</span><b className={`mono ${signClass(sign)}`}>{v}</b>
              </div>
            ))}
          </section>
          <section className="card stack" style={{ gap: 10 }} aria-labelledby="p-orders">
            <h3 id="p-orders" className="h3">Orders today</h3>
            {today.length ? <OrderList events={today} cur={cur} tz={tz} newest />
              : <p className="small muted">{!snap.events.length ? "No orders yet. They appear when your rules fire on a closed candle." : "No orders today."}</p>}
            <Earlier label="Earlier orders" count={earlier.length} className="in-card"
              note={<><span className={signClass(closedPnl)}>{money(closedPnl, cur)}</span> on closed trades</>}>
              <OrderList events={earlier} cur={cur} tz={tz} newest />
            </Earlier>
          </section>
        </div>
      </div>
    </div>
  );
}

/** Sessions as a row of cards, the open one outlined. */
function SessionCards({ rows, sid, open }: { rows: LiveRow[]; sid?: string; open: (r: LiveRow) => void }) {
  return (
    <div className="row" style={{ gap: 10, overflowX: "auto", paddingBottom: 4 }}>
      {rows.map((r) => (
        <button key={r.id} className="card" onClick={() => open(r)} aria-current={r.id === sid}
          style={{ flex: "none", minWidth: 210, textAlign: "left", cursor: "pointer", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4,
            border: r.id === sid ? "2px solid var(--ink)" : undefined }}>
          <b>{r.name}</b>
          <span className="small muted">{r.instrument.symbol} · {new Date(r.started_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}</span>
          <SurvBadges region={survRegion(r.instrument)} symbol={r.instrument.symbol} plain />
          <span className={`badge ${r.status}`} style={{ alignSelf: "flex-start" }}>{r.status}</span>
        </button>
      ))}
    </div>
  );
}

export function PaperPage() {
  const { sid } = useParams();
  const nav = useNavigate();
  const { me, fail } = useApp();
  const [rows, setRows] = useState<LiveRow[] | null>(null);
  const load = useCallback(async () => {
    try { setRows(await api<LiveRow[]>("/live/sessions")); } catch (e) { fail(e); setRows([]); }
  }, [fail]);
  useEffect(() => { load(); }, [load, sid]);

  const stopped = (rows ?? []).filter((r) => r.status !== "running" && r.status !== "paused");
  const current = (rows ?? []).filter((r) => !stopped.includes(r));     // running and paused first; the stopped ones folded
  const open = (r: LiveRow) => nav(r.instrument?.type === "OPTIONS" ? `/options/s/${r.id}` : `/paper/${r.id}`);
  const clearStopped = async () => {
    if (!confirm(`Delete ${stopped.length} stopped session${stopped.length === 1 ? "" : "s"} and their orders? Running ones stay. This can't be undone.`)) return;
    try {
      await api("/live/sessions", { method: "DELETE" });
      if (sid && stopped.some((r) => r.id === sid)) nav("/paper");
      await load();
    } catch (e) { fail(e); }
  };

  let sub = me ? `${me.plan_info.name} plan · ${me.live_running} of ${me.live_limit} running` : "";
  if (me?.plan === "free" && me.trial) {
    sub = !me.trial.started ? "Free trial: 5 market days, starting with your first session"
      : me.trial.active ? `Free trial until ${new Date(me.trial.ends_at!).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}`
        : "Free trial ended · upgrade to keep paper trading";
  }

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <h1 className="page-title">Paper trading<Info>{HELP.paper}</Info></h1>
        <p className="page-sub">Your rules on live prices, with fake money. Each market runs in its own hours; crypto never closes.</p>
        {sub && <span className="page-chip">{sub}</span>}
      </div>
      {rows === null ? <Loading /> : rows.length === 0 ? (
        <Empty title="No paper trades yet">
          <p className="muted">Open a notebook and choose <b>Paper trade</b>. Best once a verdict says the edge looks real.</p>
          <Link to="/notebooks" className="btn">Go to your notebooks</Link>
        </Empty>
      ) : (
        <div className="stack" style={{ gap: 12 }}>
          {current.length ? <SessionCards rows={current} sid={sid} open={open} />
            : <p className="muted">None running. {stopped.length === 1 ? "The stopped one is" : "Stopped ones are"} below.</p>}
          <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
            <SessionCards rows={stopped} sid={sid} open={open} />
            <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={clearStopped}>Clear stopped sessions</button>
          </Earlier>
        </div>
      )}
      {!sid && rows && rows.some((r) => r.status === "running") && (
        <RiskOverview onOpen={(id, kind) => nav(kind === "options" ? `/options/s/${id}` : `/paper/${id}`)} />
      )}
      {sid && <SessionView sid={sid} onStopped={load} onDeleted={() => { nav("/paper"); load(); }} />}
      {!sid && rows && rows.length > 0 && <p className="muted">Pick a session above to see its chart, account and orders.</p>}
    </div>
  );
}
