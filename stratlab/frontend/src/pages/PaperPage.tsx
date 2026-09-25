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
          <section className="card stack" style={{ gap: 8 }}>
            <h3 className="h3">Orders</h3>
            {snap.orders.length === 0 && <p className="small muted">No orders yet. They appear when your rules fire on a closed candle.</p>}
            <div className="stack" style={{ gap: 0, maxHeight: 340, overflowY: "auto" }}>
              {snap.orders.map((o, k) => (
                <p key={k} className="small" style={{ padding: "8px 0", borderBottom: "1px solid var(--line)" }}>
                  <b className={o.side === "buy" ? "pos" : "neg"}>{o.side === "buy" ? "Bought" : "Sold"}</b> {qty(o.qty)} at {price(o.price, cur)}
                  {o.side === "sell" && <>, {(o.reason || "").toLowerCase()}, <span className={signClass(o.pnl)}>{money(o.pnl, cur)}</span></>}
                  <span className="muted"> · {when(o.ts, tz, true)}</span>
                </p>
              ))}
            </div>
          </section>
        </div>
      </div>
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
  const clearStopped = async () => {
    if (!confirm(`Delete ${stopped.length} stopped session${stopped.length === 1 ? "" : "s"} and their orders? Running ones stay. This can't be undone.`)) return;
    try {
      await api("/live/sessions", { method: "DELETE" });
      if (sid && stopped.some((r) => r.id === sid)) nav("/paper");
      await load();
    } catch (e) { fail(e); }
  };

  let sub = me ? `Your plan runs ${me.live_limit} paper strateg${me.live_limit === 1 ? "y" : "ies"} at a time.` : "";
  if (me?.plan === "free" && me.trial) {
    sub = !me.trial.started ? "Free plan: starting a session begins your free trial: 5 market days (Monday to Friday) of paper trading."
      : me.trial.active ? `Free trial active until ${new Date(me.trial.ends_at!).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}.`
        : "Your free paper trading trial has ended. Upgrade to keep paper trading.";
  }

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <h1 className="serif row" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", gap: 0 }}>Paper trading<Info>{HELP.paper}</Info></h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: "70ch" }}>
          Your rules on live prices with fake money, in every market: India, crypto, the US, UK, Europe, Japan and forex. Each runs in its own market hours; crypto trades around the clock. {sub}
        </p>
      </div>
      {rows === null ? <Loading /> : rows.length === 0 ? (
        <Empty title="No paper trades yet">
          <p className="muted">Open a notebook and choose <b>Paper trade</b>. Best once a verdict says the edge looks real.</p>
          <Link to="/" className="btn">Go to your notebooks</Link>
        </Empty>
      ) : (
        <>
        {stopped.length > 1 && (
          <div className="spread" style={{ marginBottom: -12 }}>
            <span className="small muted">{rows.length} session{rows.length === 1 ? "" : "s"} · {stopped.length} stopped</span>
            <button className="btn quiet sm" onClick={clearStopped}>Clear stopped sessions</button>
          </div>
        )}
        <div className="row" style={{ gap: 10, overflowX: "auto", paddingBottom: 4 }}>
          {rows.map((r) => (
            <button key={r.id} className="card" onClick={() => nav(r.instrument?.type === "OPTIONS" ? `/options/s/${r.id}` : `/paper/${r.id}`)} aria-current={r.id === sid}
              style={{ flex: "none", minWidth: 210, textAlign: "left", cursor: "pointer", padding: "12px 14px", display: "flex", flexDirection: "column", gap: 4,
                border: r.id === sid ? "2px solid var(--ink)" : undefined }}>
              <b>{r.name}</b>
              <span className="small muted">{r.instrument.symbol} · {new Date(r.started_at).toLocaleDateString("en-GB", { day: "2-digit", month: "short" })}</span>
              <span className={`badge ${r.status}`} style={{ alignSelf: "flex-start" }}>{r.status}</span>
            </button>
          ))}
        </div>
        </>
      )}
      {sid && <SessionView sid={sid} onStopped={load} onDeleted={() => { nav("/paper"); load(); }} />}
      {!sid && rows && rows.length > 0 && <p className="muted">Pick a session above to see its chart, account and orders.</p>}
    </div>
  );
}
