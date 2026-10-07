import { RiskOverview } from "../components/RiskOverview";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { money, pct, price, qty, TF_NAME, tzOf, when, fmtDate, fmtDateTime } from "../lib/format";
import { upDown } from "../lib/tradeUi";
import type { LiveRow, LiveSnapshot } from "../lib/types";
import { ChartEmpty, LineChart } from "../components/Charts";
import { PriceChart, strategyStudies, type Tf } from "../charts/price/lazy";
import type { PriceLevel } from "../charts/price/engine";
import { Info } from "../components/ui";
import { Badge, Card, CardHead, ChartFrame, ConfirmDialog, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from "../components/kit";
import { HELP } from "../lib/help";
import { sessionFeed } from "../lib/marketHours";
import { GroupSession, type GroupSnapshot } from "../components/GroupSession";
import { SurvBadges, survRegion } from "../components/Surveillance";
import { FoBadges } from "../components/FoBadges";
import { foSymbol } from "../lib/foChanges";
import { Earlier, splitToday } from "../components/Earlier";
import { OrderList, type PaperOrder } from "../components/OrderList";
import { moneyCompact } from "../lib/chartFormat";
import "./trade/trade.css";
import "./trade/paper.css";

/* /paper and /paper/:sid: every paper session as a row of cards, and the open one's chart, account and orders. Built from
 * the kit (components/kit). */

const statusTone = (s: string) => (s === "running" ? "ok" : s === "paused" ? "warn" : "plain") as "ok" | "warn" | "plain";

/** The session's candles, updated in place every few seconds: the forming candle grows from the ticks seen so far. */
function LiveChart({ snap, cur }: { snap: LiveSnapshot; cur: string }) {
  const forming = useRef<{ t: string; o: number; h: number; l: number } | null>(null);
  const f = snap.forming;
  if (f && (!forming.current || forming.current.t !== f.t)) forming.current = { t: f.t, o: f.c, h: f.c, l: f.c };
  if (f && forming.current) { forming.current.h = Math.max(forming.current.h, f.c); forming.current.l = Math.min(forming.current.l, f.c); }
  const bars = useMemo(() => {
    const out: { t: string; o: number; h: number; l: number; c: number }[] = snap.bars.slice();
    const fm = forming.current;
    if (f && fm && (!out.length || f.t > out[out.length - 1].t)) out.push({ t: f.t, o: fm.o, h: fm.h, l: fm.l, c: f.c });
    return out;
  }, [snap.bars, f]);
  const markers = useMemo(() => snap.events.map((e) => ({ t: e.t, side: e.side })), [snap.events]);
  const a = snap.account;
  const levels = useMemo<PriceLevel[]>(() => [...(a.stop ? [{ price: a.stop, label: "Stop", tone: "down" as const }] : []),
    ...(a.target ? [{ price: a.target, label: "Target", tone: "up" as const }] : [])], [a.stop, a.target]);
  const s = snap.strategy;
  const studies = useMemo(() => strategyStudies([...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])]), [s]);
  return <PriceChart symbol={snap.instrument.symbol} storageKey={(snap.instrument.id || snap.instrument.symbol).slice(0, 40)} currency={cur}
    bars={bars} tf={s.tf as Tf} timeframes={[s.tf as Tf]} markers={markers} levels={levels} pageStudies={studies} height={340} />;
}

function SessionView({ sid, onStopped, onDeleted }: { sid: string; onStopped: () => void; onDeleted: () => void }) {
  const { fail, refreshMe, markets } = useApp();
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);

  const load = useCallback(async () => {
    try { setSnap(await api<LiveSnapshot>(`/live/sessions/${sid}`)); } catch (e) { fail(e); }
  }, [sid, fail]);

  useEffect(() => {
    setSnap(null);
    load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 3000);
    return () => window.clearInterval(t);
  }, [load]);

  if (!snap) return <Card><Skeleton label="Connecting to the session" /></Card>;
  if ((snap as unknown as GroupSnapshot).kind === "group") {
    const g = snap as unknown as GroupSnapshot;
    return <GroupSession snap={g}
      onStop={async () => { try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); } }}
      onDelete={async () => { try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); } }} />;
  }
  const running = snap.status === "running";
  const cur = snap.instrument.currency || (snap.instrument.market === "IN" || !snap.instrument.market ? "INR" : "");
  const tz = tzOf(snap.instrument);
  const intraday = snap.strategy.tf !== "1d";
  const a = snap.account;
  const alwaysOpen = snap.instrument.market === "CRYPTO";
  // orders: today's in view, the earlier ones open under them
  const orders: PaperOrder[] = snap.events.map((e) => ({ ...e, sym: snap.instrument.symbol }));
  const { today, earlier } = splitToday(orders, (e) => e.t, tz);
  const closedPnl = earlier.reduce((n, e) => n + (e.pnl ?? 0), 0);
  // the market's own hours first: after the close it's "Market closed · opens …", not a lost connection (lib/marketHours)
  const feed = sessionFeed({ feedConnected: snap.feed_connected, lastTickAt: snap.last_tick_at, alwaysOpen,
    market: markets.find((m) => m.id === snap.instrument.market) });

  const stop = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); }
  };

  const remove = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); }
  };

  const rows: [string, string, number | null, string | null][] = [
    ["Equity", money(a.equity, cur), null, HELP.equityLive],
    ["Return", pct((a.equity / a.capital - 1) * 100, 2), a.equity - a.capital, null],
    ["Cash", money(a.cash, cur), null, HELP.cash],
    ["Open position", a.qty ? `${qty(a.qty)} at ${price(a.entry ?? 0, cur)}` : "None", null, null],
    ["Unrealised P&L", money(a.unrealised, cur), a.unrealised, HELP.unrealised],
    ["Realised P&L", money(a.realised, cur), a.realised, HELP.realised],
    ["Closed trades", a.trades ? `${a.trades} (${a.wins} won)` : "0", null, null],
  ];

  return (
    <div className="k-page">
      <div className="k-spread k-session-head">
        <div className="k-stack k-tight">
          <span className="k-eyebrow">{snap.instrument.symbol} · {TF_NAME[snap.strategy.tf]} candles · started {when(snap.started_at, tz, true, true)}</span>
          <div className="k-row">
            <SurvBadges region={survRegion(snap.instrument)} symbol={snap.instrument.symbol} />
            <FoBadges region={survRegion(snap.instrument)} symbol={foSymbol(snap.instrument)} />
          </div>
          <h2 className="k-session-name">{snap.name}</h2>
        </div>
        <div className="k-row">
          {running && <span className="k-row" data-testid="feed-line"><Badge tone={feed.tone}>{feed.text}</Badge><Info>{HELP.feed}</Info></span>}
          {running ? <button type="button" className="btn danger" onClick={() => setAsk("stop")}>Stop session</button>
            : <><Badge tone={statusTone(snap.status)}>{snap.status}</Badge><button type="button" className="btn danger sm" onClick={() => setAsk("delete")}>Delete</button></>}
        </div>
      </div>
      {!running && snap.stop_reason && <Notice>Stopped: {snap.stop_reason}</Notice>}

      <div className="nb-grid">
        <div className="k-page">
          <Card label="Live chart">
            <CardHead level={3} title="Live chart" actions={snap.last_price != null ? <span className="k-small">{snap.instrument.symbol} {price(snap.last_price, cur)}</span> : undefined} />
            {snap.bars.length ? <LiveChart snap={snap} cur={cur} /> : <p className="k-small k-muted">The chart fills in as candles close.</p>}
          </Card>
          <ChartFrame title="Paper equity" info={HELP.equityLive}>
            {snap.equity_curve.length > 1 ? (
              <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((p) => when(p.t, tz, intraday))} times={snap.equity_curve.map((p) => p.t)} tz={tz} height={160}
                format={(x) => money(x, cur)} axisFormat={(x) => moneyCompact(x, cur ?? "INR")} baseline={a.capital} lines={[{ label: "Equity", values: snap.equity_curve.map((p) => p.eq), color: "var(--series-1)", width: 2 }]} />
            ) : <ChartEmpty height={160}>Your equity curve starts after the first closed candle.</ChartEmpty>}
          </ChartFrame>
        </div>
        <div className="k-page">
          <Card label="Account">
            <CardHead level={3} title="Account" actions={<span className="k-note">Fake money</span>} />
            <div className="k-rows" role="list" aria-label="Paper account">
              {rows.map(([k, v, sign, help]) => (
                <div key={k} role="listitem"><span>{k}{help && <Info label={`What is ${k}?`}>{help}</Info>}</span><b className={upDown(sign)}>{v}</b></div>
              ))}
            </div>
          </Card>
          <Card label="Orders today">
            <CardHead level={3} title="Orders today" />
            {today.length ? <OrderList events={today} cur={cur} tz={tz} newest />
              : <p className="k-small k-muted">{!snap.events.length ? "No orders yet. They appear when your rules fire on a closed candle." : "No orders today."}</p>}
            <Earlier label="Earlier orders" count={earlier.length} className="in-card" open
              note={<><span className={upDown(closedPnl)}>{money(closedPnl, cur)}</span> on closed trades</>}>
              <OrderList events={earlier} cur={cur} tz={tz} newest />
            </Earlier>
          </Card>
        </div>
      </div>
      {ask === "stop" && <ConfirmDialog title="Stop this session?" confirmLabel="Stop session" onConfirm={stop} onClose={() => setAsk(null)}>
        Open paper positions are left as they are, and it can't be restarted.</ConfirmDialog>}
      {ask === "delete" && <ConfirmDialog title={`Delete "${snap.name}"?`} confirmLabel="Delete session" onConfirm={remove} onClose={() => setAsk(null)}>
        Its orders go with it. This can't be undone.</ConfirmDialog>}
    </div>
  );
}

/** Sessions as a row of cards, the open one outlined. */
function SessionCards({ rows, sid, open }: { rows: LiveRow[]; sid?: string; open: (r: LiveRow) => void }) {
  return (
    <div className="k-sessions">
      {rows.map((r) => (
        <button type="button" key={r.id} className="k-sess" onClick={() => open(r)} aria-current={r.id === sid}>
          <b>{r.name}</b>
          <span className="k-note">{r.instrument.symbol} · {fmtDate(r.started_at, { year: false })}</span>
          <SurvBadges region={survRegion(r.instrument)} symbol={r.instrument.symbol} plain />
          <FoBadges region={survRegion(r.instrument)} symbol={foSymbol(r.instrument)} plain />
          <Badge tone={statusTone(r.status)}>{r.status}</Badge>
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
  const [failed, setFailed] = useState(false);
  const [clearing, setClearing] = useState(false);
  const load = useCallback(async () => {
    try { setRows(await api<LiveRow[]>("/live/sessions")); setFailed(false); } catch (e) { fail(e); setFailed(true); setRows([]); }
  }, [fail]);
  useEffect(() => { load(); }, [load, sid]);

  const stopped = (rows ?? []).filter((r) => r.status !== "running" && r.status !== "paused");
  const current = (rows ?? []).filter((r) => !stopped.includes(r));     // running and paused first; the stopped ones folded
  const open = (r: LiveRow) => nav(r.instrument?.type === "OPTIONS" ? `/options/s/${r.id}` : (r.instrument as { signal?: boolean })?.signal ? `/trade/signals/${r.id}` : `/paper/${r.id}`);
  const clearStopped = async () => {
    setClearing(false);
    try {
      await api("/live/sessions", { method: "DELETE" });
      if (sid && stopped.some((r) => r.id === sid)) nav("/paper");
      await load();
    } catch (e) { fail(e); }
  };

  let sub = me ? `${me.plan_info.name} plan · ${me.live_running} of ${me.live_limit} running` : "";
  if (me?.plan === "free" && me.trial) {
    sub = !me.trial.started ? "Free trial: 5 market days, starting with your first session"
      : me.trial.active ? `Free trial until ${fmtDateTime(me.trial.ends_at, { year: false, zone: true })}`
        : "Free trial ended · upgrade to keep paper trading";
  }

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Practise" title="Paper trading" info={HELP.paper} infoLabel="About paper trading"
        lede="Your rules on live prices, with fake money. Each market runs in its own hours; crypto never closes."
        actions={sub ? <Badge tone="plain" dot={false}>{sub}</Badge> : undefined} />
      {rows === null ? <Card><Skeleton label="Opening your sessions" /></Card>
        : failed ? <ErrorState title="Your sessions couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>Nothing was changed.</ErrorState>
        : rows.length === 0 ? (
          <EmptyState title="No paper trades yet" action={{ label: "Go to your notebooks", to: "/notebooks" }}>
            Open a notebook and choose Paper trade. A session runs its rules on live prices with fake money.
          </EmptyState>
        ) : (
          <Card label="Your sessions">
            <CardHead title="Your sessions" />
            {current.length ? <SessionCards rows={current} sid={sid} open={open} />
              : <p className="k-small k-muted">None running. {stopped.length === 1 ? "The stopped one is" : "Stopped ones are"} below.</p>}
            <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
              <SessionCards rows={stopped} sid={sid} open={open} />
              <button type="button" className="btn quiet sm k-btn-end" onClick={() => setClearing(true)}>Clear stopped sessions</button>
            </Earlier>
          </Card>
        )}
      {!sid && rows && rows.some((r) => r.status === "running") && (
        <RiskOverview onOpen={(id, kind) => nav(kind === "options" ? `/options/s/${id}` : `/paper/${id}`)} />
      )}
      {sid && <SessionView sid={sid} onStopped={load} onDeleted={() => { nav("/paper"); load(); }} />}
      {!sid && rows && rows.length > 0 && <p className="k-small k-muted">Pick a session above to see its chart, account and orders.</p>}
      {clearing && (
        <ConfirmDialog title={`Delete ${stopped.length} stopped session${stopped.length === 1 ? "" : "s"}?`} confirmLabel="Delete stopped sessions" onConfirm={clearStopped} onClose={() => setClearing(false)}>
          Their orders go with them. Running ones stay. This can't be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
