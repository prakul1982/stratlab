import { RiskOverview } from "../components/RiskOverview";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { money, pct, price, qtyShort, TF_NAME, tzOf, when, fmtDate, fmtDateTime } from "../lib/format";
import { viewedFreeKeepsSessions } from "../lib/account";
import { sessionPath, upDown } from "../lib/tradeUi";
import type { LiveRow, LiveSnapshot } from "../lib/types";
import { ChartEmpty, LineChart } from "../components/Charts";
import { PriceChart, strategyStudies, type Tf } from "../charts/price/lazy";
import type { PriceLevel } from "../charts/price/engine";
import { Info } from "../components/ui";
import { Badge, Card, CardHead, ChartFrame, ConfirmDialog, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from "../components/kit";
import { HELP } from "../lib/help";
import { marketState, optionsMarket, sessionFeed } from "../lib/marketHours";
import { GroupSession, type GroupSnapshot } from "../components/GroupSession";
import { SurvBadges, survRegion } from "../components/Surveillance";
import { FoBadges } from "../components/FoBadges";
import { foSymbol } from "../lib/foChanges";
import { Earlier, splitToday } from "../components/Earlier";
import { OrderList, type PaperOrder } from "../components/OrderList";
import { moneyCompact } from "../lib/chartFormat";
import { fillsLine, rulesLines, STOP_DIALOG, stoppedOpenLine, trialLastDay } from "../lib/paperText";
import { opSay, refName, stopWords } from "../lib/rules";
import "./trade/trade.css";
import "./trade/paper.css";

/* /paper and /paper/:sid: every paper session as a row of cards, and the open one's chart, account and orders. Built from
 * the kit (components/kit). */

const statusTone = (s: string) => (s === "running" ? "ok" : s === "paused" ? "warn" : "plain") as "ok" | "warn" | "plain";

/** The session's candles, updated in place every few seconds: the forming candle grows from the ticks seen so far. */
function LiveChart({ snap, cur, note }: { snap: LiveSnapshot; cur: string; note?: string }) {
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
  const markers = useMemo(() => snap.events.filter((e) => e.side).map((e) => ({ t: e.t, side: e.side })), [snap.events]);
  const a = snap.account;
  const levels = useMemo<PriceLevel[]>(() => [...(a.stop ? [{ price: a.stop, label: "Stop", tone: "down" as const }] : []),
    ...(a.target ? [{ price: a.target, label: "Target", tone: "up" as const }] : [])], [a.stop, a.target]);
  const s = snap.strategy;
  const studies = useMemo(() => strategyStudies([...s.entry, ...s.exit, ...(s.shortEntry ?? []), ...(s.shortExit ?? [])]), [s]);
  return <PriceChart symbol={snap.instrument.symbol} storageKey={(snap.instrument.id || snap.instrument.symbol).slice(0, 40)} currency={cur}
    bars={bars} tf={s.tf as Tf} timeframes={[s.tf as Tf]} markers={markers} levels={levels} pageStudies={studies} height={340} note={note} />;
}

/** A session's snapshot with every list it draws present: an older or other kind of session may leave one out (R7T-011: an
 * options session's snapshot has no candles, and `bars.length` crashed the page). */
export function withLists(s: LiveSnapshot): LiveSnapshot {
  return { ...s, bars: s.bars ?? [], events: s.events ?? [], equity_curve: s.equity_curve ?? [] };
}

function SessionView({ sid, onStopped, onDeleted }: { sid: string; onStopped: () => void; onDeleted: () => void }) {
  const { fail, refreshMe, markets } = useApp();
  const nav = useNavigate();
  const [snap, setSnap] = useState<LiveSnapshot | null>(null);
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);
  // one stop or delete at a time: a second click while it is in flight is dropped
  const acting = useRef(false);
  const once = async (f: () => Promise<void>) => {
    if (acting.current) return;
    acting.current = true;
    try { await f(); } finally { acting.current = false; }
  };

  const [error, setError] = useState<string | null>(null);
  const [missing, setMissing] = useState(false);
  const told = useRef(false);          // a failing poll is said once, not every 3 seconds
  const poll = useRef<number>(undefined);

  // `live` is false once the effect is cleaned up (another session, or the page left): a late answer is dropped
  const load = useCallback(async (live: () => boolean = () => true) => {
    try {
      const s = withLists(await api<LiveSnapshot>(`/live/sessions/${sid}`));
      if (live()) { setSnap(s); setError(null); told.current = false; }
    } catch (e) {
      if (!live()) return;
      setError((e as Error)?.message || "Something went wrong. Try again.");
      // no session at this address: nothing will come back, so the polling stops and the page says so
      if (e instanceof ApiError && (e.status === 404 || e.status === 400 || e.status === 422)) { setMissing(true); window.clearInterval(poll.current); return; }
      if (!told.current) { told.current = true; fail(e); }
    }
  }, [sid, fail]);

  useEffect(() => {
    let live = true;
    const on = () => live;
    setSnap(null);
    setError(null);
    setMissing(false);
    told.current = false;
    void load(on);
    poll.current = window.setInterval(() => { if (!document.hidden) void load(on); }, 3000);
    return () => { live = false; window.clearInterval(poll.current); };
  }, [load]);

  // an options or signal session's id here opens its own page (R7T-011)
  const own = snap ? sessionPath({ id: sid, kind: (snap as unknown as { kind?: string }).kind, instrument: snap.instrument as { type?: string; signal?: boolean } }) : null;
  useEffect(() => { if (own && own !== `/paper/${sid}`) nav(own, { replace: true }); }, [own, sid, nav]);

  if (!snap && missing) return <Card><EmptyState title="Session not found" action={{ label: "See your sessions", to: "/paper" }}>There's no paper session at this address. It may have been deleted, or the link may be from another account.</EmptyState></Card>;
  if (!snap && error) return <Card><ErrorState title="The session didn't load" action={{ label: "Try again", onClick: () => { void load(); } }}>{error}</ErrorState></Card>;
  if (!snap || (own && own !== `/paper/${sid}`)) return <Card><Skeleton label="Connecting to the session" /></Card>;
  if ((snap as unknown as GroupSnapshot).kind === "group") {
    const g = snap as unknown as GroupSnapshot;
    return <GroupSession snap={g}
      onStop={() => once(async () => { try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); } })}
      onDelete={() => once(async () => { try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); } })} />;
  }
  const running = snap.status === "running";
  const cur = snap.instrument.currency || (snap.instrument.market === "IN" || !snap.instrument.market ? "INR" : "");
  const tz = tzOf(snap.instrument);
  const intraday = snap.strategy.tf !== "1d";
  const a = snap.account;
  const alwaysOpen = snap.instrument.market === "CRYPTO";
  const marketClose = markets.find((m) => m.id === snap.instrument.market)?.hours?.close ?? null;
  // orders: today's in view, the earlier ones open under them
  const orders: PaperOrder[] = snap.events.map((e) => ({ ...e, sym: snap.instrument.symbol }));
  const { today, earlier } = splitToday(orders, (e) => e.t, tz);
  const closedPnl = earlier.reduce((n, e) => n + (e.pnl ?? 0), 0);
  // the market's own hours first: after the close it's "Market closed · opens …", not a lost connection (lib/marketHours)
  const feed = sessionFeed({ feedConnected: snap.feed_connected, lastTickAt: snap.last_tick_at, alwaysOpen,
    market: markets.find((m) => m.id === snap.instrument.market) });

  const stop = () => {
    setAsk(null);
    return once(async () => { try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); onStopped(); } catch (e) { fail(e); } });
  };

  const remove = () => {
    setAsk(null);
    return once(async () => { try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onDeleted(); } catch (e) { fail(e); } });
  };

  // every money figure to the cent, as the replay's are (DB-022: "$10" and "$9,985" beside "$0.00")
  const rows: [string, string, number | null, string | null][] = [
    ["Equity", money(a.equity, cur, 2), null, HELP.equityLive],
    ["Return", pct((a.equity / a.capital - 1) * 100, 2), a.equity - a.capital, null],
    ["Cash", money(a.cash, cur, 2), null, HELP.cash],
    ["Open position", a.qty ? `${qtyShort(a.qty, snap.instrument.market)} at ${price(a.entry ?? 0, cur)}` : "None", null, null],
    ["Unrealised P&L", money(a.unrealised, cur, 2), a.unrealised, `${HELP.unrealised} It already counts the costs of the entry.`],
    ["Realised P&L", money(a.realised, cur, 2), a.realised, HELP.realised],
    ["Closed trades", a.trades ? `${a.trades} (${a.wins} won)` : "0", null, null],
  ];

  // one "now" price (DB-020): the header's is the latest trade, the chart's candles are closed ones unless one is forming,
  // and the chart says which; a stopped session's price is the last before the stop, with its time
  const lastBar = snap.bars[snap.bars.length - 1];
  // (said from what the chart draws: a forming candle is drawn whenever the snapshot has one, so the caption never calls it closed, RC1-008)
  const chartNote = snap.forming ? `${TF_NAME[snap.strategy.tf]} candles. The last one is still forming: it moves with each price until it closes.`
    : lastBar ? `${TF_NAME[snap.strategy.tf]} candles, closed ones only: the last closed ${when(lastBar.t, tz, intraday, true)}.${running && snap.last_price != null ? " The latest price is above the chart." : ""}` : undefined;
  const priceHead = snap.last_price == null ? undefined : running
    ? `${snap.instrument.symbol} ${price(snap.last_price, cur)}, latest price${snap.last_tick_at ? `, ${when(snap.last_tick_at, tz, true, true)}` : ""}`
    : `${snap.instrument.symbol} ${price(snap.last_price, cur)}, the last price before the stop${snap.last_tick_at ? ` (${when(snap.last_tick_at, tz, true, true)})` : ""}`;
  // the equity curve from the starting capital (DB-022: it began at the first candle, with no $10,000 point)
  const curve = snap.equity_curve.length && snap.equity_curve[0].t > snap.started_at ? [{ t: snap.started_at, eq: a.capital }, ...snap.equity_curve] : snap.equity_curve;
  const span = curve.length ? Math.max(...curve.map((p) => p.eq), a.capital) - Math.min(...curve.map((p) => p.eq), a.capital) : 0;
  // a few dollars of movement on $10,000 reads as one "$10k" label: whole amounts then
  const axis = (x: number) => (span < a.capital * 0.05 ? money(x, cur, 0) : moneyCompact(x, cur ?? "INR"));
  const market = markets.find((m) => m.id === snap.instrument.market);
  const s = snap.strategy;
  const cond = (c: (typeof s.entry)[number]) => `${refName(c.l)} ${opSay(c.op)} ${refName(c.r)}`;
  const closedTrades = orders.filter((e) => e.side && e.pnl != null);

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
      {snap.notice && <Notice tone="warn">{snap.notice}</Notice>}
      {a.emptied_on && <Notice tone="warn"><b>Account emptied on {fmtDate(a.emptied_on)}.</b> The account reached zero, so the position was closed and nothing opens again; the loss stops at −100%.</Notice>}
      {!running && a.qty > 0 && (
        <Notice className="stopped-open">
          {stoppedOpenLine(a.side, a.qty, price(a.entry ?? 0, cur), a.valued_at != null ? price(a.valued_at, cur) : null)}
        </Notice>
      )}

      <div className="nb-grid">
        <div className="k-page">
          <Card label="Live chart" className="sess-chart">
            <CardHead level={3} title={running ? "Live chart" : "Chart"} info={<span data-testid="sess-fills">{fillsLine(s.risk, market?.costs, money(s.risk.brokerage, cur, 2))}</span>} infoLabel="How orders fill and what they pay" actions={priceHead ? <span className="k-small" data-testid="sess-price">{priceHead}</span> : undefined} />
            {snap.bars.length ? <LiveChart snap={snap} cur={cur} note={chartNote} /> : <p className="k-small k-muted">The chart fills in as candles close.</p>}
          </Card>
          <ChartFrame title="Paper equity" info={HELP.equityLive}>
            {curve.length > 1 ? (
              <LineChart ariaLabel="Paper account value" labels={curve.map((p) => when(p.t, tz, intraday))} times={curve.map((p) => p.t)} tz={tz} height={160}
                format={(x) => money(x, cur, 2)} axisFormat={axis} baseline={a.capital} lines={[{ label: "Equity", values: curve.map((p) => p.eq), color: "var(--series-1)", width: 2 }]} />
            ) : <ChartEmpty height={72}>Your equity curve starts after the first closed candle.</ChartEmpty>}{/* VR1-092: a 160px box for one line */}
            {curve.length > 1 && <p className="k-note">From the starting {money(a.capital, cur, 0)} (the grey line), after each closed candle.</p>}
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
          {/* nothing to list until a trade has closed: the Account card above already says "Closed trades 0" (RC2A-033: a full-width card of "None yet") */}
          {closedTrades.length > 0 && <Card label="Closed trades">
            <CardHead level={3} title={`Closed trades (${a.trades})`} />
            <OrderList events={closedTrades} cur={cur} tz={tz} newest tf={snap.strategy.tf} close={marketClose} />
          </Card>}
          <Card label="Orders">
            <CardHead level={3} title="Orders" />
            {today.length ? <OrderList events={today} cur={cur} tz={tz} newest tf={snap.strategy.tf} close={marketClose} />
              : <p className="k-small k-muted">{!snap.events.length ? "No orders yet. They appear when your rules fire on a closed candle." : "No orders today."}</p>}
            <Earlier label="Earlier orders" count={earlier.length} className="in-card" open
              note={<><span className={upDown(closedPnl)}>{money(closedPnl, cur)}</span> on closed trades</>}>
              <OrderList events={earlier} cur={cur} tz={tz} newest tf={snap.strategy.tf} close={marketClose} />
            </Earlier>
          </Card>
          {/* the rules last in the column: on a phone the account and the orders come before three lines of rules (RC2A-033) */}
          <Card label="Rules">
            <CardHead level={3} title="Rules" />
            <ul className="k-list" data-testid="sess-rules">
              {rulesLines(s, cond).map((x) => <li key={x}>{x}</li>)}
              <li>{s.risk.sl ? `A ${stopWords(s.risk.sl, s.risk.stopType)}` : "No stop"}{s.risk.tgt ? `, a ${s.risk.tgt}${s.risk.tgtType === "points" ? "-point" : s.risk.tgtType === "r" ? "R" : "%"} target` : ", no target"}; {money(s.risk.capital, cur, 0)} of fake money.</li>
            </ul>
          </Card>
        </div>
      </div>
      {ask === "stop" && <ConfirmDialog title="Stop this session?" confirmLabel="Stop session" onConfirm={stop} onClose={() => setAsk(null)}>
        {STOP_DIALOG}</ConfirmDialog>}
      {ask === "delete" && <ConfirmDialog title={`Delete "${snap.name}"?`} confirmLabel="Delete session" onConfirm={remove} onClose={() => setAsk(null)}>
        Its orders go with it. This can't be undone.</ConfirmDialog>}
    </div>
  );
}

/** Sessions as a row of cards, the open one outlined. */
function SessionCards({ rows, sid, open }: { rows: LiveRow[]; sid?: string; open: (r: LiveRow) => void }) {
  const { markets } = useApp();
  // a running session whose market is shut says so, as its page does (R90-011: "running" on a Saturday, nothing else)
  const shut = (r: LiveRow) => { const m = markets.find((x) => x.id === r.instrument.market) ?? optionsMarket(markets, r.instrument.exchange); return !!m && !marketState(m).open; };
  return (
    <div className="k-sessions">
      {rows.map((r) => (
        <button type="button" key={r.id} className="k-sess" onClick={() => open(r)} aria-current={r.id === sid}>
          <b>{r.name}</b>
          <span className="k-note">{r.instrument.symbol} · started {fmtDateTime(r.started_at, { tz: tzOf(r.instrument), year: false, zone: true })}</span>
          <SurvBadges region={survRegion(r.instrument)} symbol={r.instrument.symbol} plain />
          <FoBadges region={survRegion(r.instrument)} symbol={foSymbol(r.instrument)} plain />
          <Badge tone={statusTone(r.status)}>{r.status}</Badge>
          {r.status === "running" && shut(r) && <span className="k-note" data-testid="sess-market-shut">Market closed</span>}
          {r.cap_hit && <Badge tone="warn">Loss cap hit today</Badge>}
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
  const open = (r: LiveRow) => nav(sessionPath({ id: r.id, instrument: r.instrument as { type?: string; signal?: boolean } | null }));
  // an options or signal session's id at /paper/<id> opens its own page (R7T-011)
  useEffect(() => {
    const r = sid ? (rows ?? []).find((x) => x.id === sid) : null;
    const to = r ? sessionPath({ id: r.id, instrument: r.instrument as { type?: string; signal?: boolean } | null }) : null;
    if (to && to !== `/paper/${sid}`) nav(to, { replace: true });
  }, [rows, sid, nav]);
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
      // the trial's last day in India's calendar, where it is counted, not "30 Oct, 18:30 UTC" (DP1-013)
      : me.trial.active && me.trial.ends_at ? `Free trial until the end of ${trialLastDay(me.trial.ends_at)} (India time)`
        : viewedFreeKeepsSessions(me) ? "Viewing as Free: your sessions keep running here; on a real Free plan they stop when the free trial ends"
          : "Free trial ended · sessions are stopped; upgrade to keep paper trading";
  }

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Practise" title="Paper trading"
        lede="Your rules on live prices, with fake money. Each market runs in its own hours; crypto never closes."
        // the (i) follows the plan pill, as "Data up to" badges are followed by theirs, not dangling in front of it (VR1-091)
        actions={<>{sub && <Badge tone="plain" dot={false}>{sub}</Badge>}<Info label="About paper trading">{HELP.paper}</Info></>} />
      {rows === null ? <Card><Skeleton label="Opening your sessions" /></Card>
        : failed ? <ErrorState title="Your sessions couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>Nothing was changed.</ErrorState>
        : rows.length === 0 ? (
          <EmptyState title="No paper trades yet" action={{ label: "Go to your notebooks", to: "/notebooks" }}>
            Open a notebook and choose Paper trade, or <Link className="link" to="/options">build an options strategy</Link> and paper trade it. A session runs its rules on live prices with fake money.
          </EmptyState>
        ) : (
          <Card label="Your sessions">
            {/* a second session starts from here: a notebook's rules or an options strategy built in the builder (owner, 28 Oct) */}
            <CardHead title="Your sessions" actions={<NewSessionButtons />} />
            {current.length ? <SessionCards rows={current} sid={sid} open={open} />
              : <p className="k-small k-muted">None running. {stopped.length === 1 ? "The stopped one is" : "Stopped ones are"} below.</p>}
            <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
              <SessionCards rows={stopped} sid={sid} open={open} />
              <button type="button" className="btn quiet sm k-btn-end" onClick={() => setClearing(true)}>Clear stopped sessions</button>
            </Earlier>
          </Card>
        )}
      {!sid && rows && rows.length > 0 && <p className="k-small k-muted">Pick a session above to see its chart, account and orders.</p>}
      {!sid && rows && rows.some((r) => r.status === "running") && (
        <RiskOverview onOpen={(id, kind) => nav(sessionPath({ id, kind }))} />
      )}
      {sid && <SessionView sid={sid} onStopped={load} onDeleted={() => { nav("/paper"); load(); }} />}
      {clearing && (
        <ConfirmDialog title={`Delete ${stopped.length} stopped session${stopped.length === 1 ? "" : "s"}?`} confirmLabel="Delete stopped sessions" onConfirm={clearStopped} onClose={() => setClearing(false)}>
          Their orders go with them. Running ones stay. This can't be undone.
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Start another session from the paper trading page: a notebook's rules, or an options strategy from the builder. */
function NewSessionButtons() {
  return (
    <span className="k-row">
      <Link className="btn sm" to="/options">Build an options strategy</Link>
      <Link className="btn quiet sm" to="/notebooks">Paper trade a notebook</Link>
    </span>
  );
}
