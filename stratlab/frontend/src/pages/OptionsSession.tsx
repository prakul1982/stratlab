import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, type ApiError } from "../lib/api";
import { useApp } from "../lib/app";
import { money, price, tzLabel, when } from "../lib/format";
import { upDown } from "../lib/tradeUi";
import { HELP } from "../lib/help";
import type { HeldGreeks, OptionSnapshot } from "../lib/types";
import { atExpiry, legName, legRule, priceGrid, type HeldLeg } from "../lib/options";
import { ModelPanel, RollPreview, type ModelRow } from "../components/OptionModel";
import { ChartEmpty, LineChart } from "../components/Charts";
import { Info } from "../components/ui";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, Disclosure, Notice, PageHeader, Skeleton, Stat, StatRow, type Column } from "../components/kit";
import { Earlier, splitToday } from "../components/Earlier";
import { contract, OrderList, ordersBetween, ordersSince } from "../components/OrderList";
import { moneyCompact } from "../lib/chartFormat";
import "./trade/trade.css";
import "./trade/options.css";
import "./trade/paper.css";
import { sessionFeed } from "../lib/marketHours";

const TZ = "Asia/Kolkata";
const inr = (v: number | null | undefined) => money(v, "INR");
const t = (iso: string) => when(iso, TZ, true);
const tone = (n: number | null) => (n == null || n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));

/* /options/s/:sid: one options paper session: its rules, the open trade, today's closed trades, the earlier ones, the model's
 * Greeks and payoff for what is open, and the account's curve. Built from the kit (components/kit). */

export function OptionsSession() {
  const { sid = "" } = useParams();
  const { fail, refreshMe, markets } = useApp();
  const nav = useNavigate();
  const [snap, setSnap] = useState<OptionSnapshot | null>(null);
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);
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

  if (!snap) return <div className="k-page"><PageHeader eyebrow="Trade · Practise" title="Options session" /><Card><Skeleton label="Connecting to the session" /></Card></div>;
  const running = snap.status === "running";
  const a = snap.account, p = snap.position, s = snap.strategy;
  const { today, earlier } = splitToday(snap.trades, (x) => x.closed, TZ);
  // the order log also keeps a line when the India VIX filter held an entry back; those aren't orders
  const orders = snap.events.filter((e) => e.kind !== "skip");
  const skips = snap.events.filter((e) => e.kind === "skip").slice(-5).reverse();
  const openOrders = p ? ordersSince(orders, p.opened) : [];
  // the exchange's hours first (lib/marketHours): after the close it says so and when it opens, not "Reconnecting"
  const closed = sessionFeed({ feedConnected: snap.feed_connected, lastTickAt: null, market: markets.find((m) => m.id === "IN") });
  const feed = closed.text.startsWith("Market closed") ? closed
    : !snap.feed_connected ? { text: "Reconnecting to prices", tone: "plain" as const } : snap.fresh ? { text: "Live option prices", tone: "live" as const } : { text: "Waiting for the first prices", tone: "plain" as const };

  const stop = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); await load(); refreshMe(); } catch (e) { fail(e); }
  };
  const remove = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); nav("/options"); } catch (e) { fail(e); }
  };

  type Leg = OptionSnapshot["legs"][number];
  const legCols: Column<Leg>[] = [
    { key: "leg", header: "Leg", rowHeader: true, cell: (l) => <span title={l.sym}>{contract(l)}{!l.open && " (closed)"}</span> },
    { key: "side", header: "Side", cell: (l) => (l.side === "sell" ? "Sold" : "Bought") },
    { key: "qty", header: "Qty", numeric: true, cell: (l) => l.qty.toLocaleString("en-IN") },
    { key: "entry", header: "Entry", numeric: true, cell: (l) => price(l.entry, "INR") },
    { key: "now", header: "Now", info: HELP.optMark, numeric: true, cell: (l) => price(l.mark, "INR") },
    { key: "pnl", header: "P&L", numeric: true, cell: (l) => <span className={upDown(l.pnl)}>{inr(l.pnl)}</span> },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Practise" title={snap.name}
        lede={<><Link to="/options" className="link">← Options builder</Link> · {snap.instrument.underlying} options · {snap.instrument.exchange}{snap.expiry ? ` · expiry ${snap.expiry}` : ""} · started {when(snap.started_at, TZ, true, true)}</>}
        actions={<>
          {running && <span className="k-row"><Badge tone={feed.tone}>{feed.text}</Badge><Info>{HELP.optFeed}</Info></span>}
          {running ? <button type="button" className="btn danger" onClick={() => setAsk("stop")}>Stop session</button>
            : <><Badge tone={snap.status === "paused" ? "warn" : "plain"}>{snap.status}</Badge><button type="button" className="btn danger sm" onClick={() => setAsk("delete")}>Delete</button></>}
        </>} />
      {!running && snap.stop_reason && <Notice>Stopped: {snap.stop_reason}</Notice>}
      {running && a.halted && <Notice tone="warn">The daily loss cap was hit. No more trades today; it starts again tomorrow.</Notice>}
      {running && snap.note && !p && <Notice>{snap.note}</Notice>}
      {snap.signal && (
        <Card label="Signal">
          <div className="k-row">
            <span className="k-eyebrow">Signal</span>
            <span><b>{snap.signal.name}</b> on {snap.instrument.underlying} {snap.signal.tf} candles</span>
            <Badge tone={snap.signal.position === "long" ? "ok" : snap.signal.position === "short" ? "warn" : "plain"}>
              {snap.signal.position === "long" ? "Rules long" : snap.signal.position === "short" ? "Rules short" : "Rules flat"}</Badge>
            {snap.signal.last_candle && <span className="k-note">last candle {new Date(snap.signal.last_candle).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST{snap.signal.price != null ? ` · ${price(snap.signal.price, "INR")}` : ""}</span>}
            {!snap.signal.ok && <span className="k-note k-down">Couldn't fetch the latest candles; retrying.</span>}
          </div>
        </Card>
      )}

      <Card label="The account">
        <StatRow label="Session results">
          <Stat item label="Open trade, after costs" value={p ? inr(p.net) : "No open trade"} tone={tone(p ? p.net : null)} />
          <Stat item label="Today" value={inr(a.today + (p ? p.net : 0))} tone={tone(a.today + (p ? p.net : 0))} />
          <Stat item label="All closed trades" value={inr(a.realised)} tone={tone(a.realised)} />
          <Stat item label="Paper account" value={inr(a.equity)} tone={tone(a.equity - a.capital)} />
        </StatRow>
      </Card>

      <section className="k-card rules-strip" aria-label="Rules">
        <CardHead title="Rules" level={3} />
        <ul className="k-list">
          <li>{s.legs.map((l) => `${l.side === "sell" ? "Sell" : "Buy"} ${legRule(l, s.offsetUnit)} ${l.opt}${l.lots > 1 ? ` × ${l.lots}` : ""}`).join(", ")}</li>
          {s.vix && <li data-testid="rule-vix">Enter only while India VIX is {s.vix.min && s.vix.max ? `between ${s.vix.min} and ${s.vix.max}` : s.vix.max ? `at or below ${s.vix.max}` : `at or above ${s.vix.min}`}</li>}
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

      <Card label="Today">
        <CardHead level={3} title="Today" actions={snap.spot != null ? <span className="k-small">{snap.instrument.underlying} {price(snap.spot, "INR")}</span> : undefined} />
        {!p ? <p className="k-small k-muted">{flatLine(snap, today.length)}</p> : (
          <>
            <p className="k-small k-muted">Open since {when(p.opened, TZ, true, true)} with {snap.instrument.underlying} at {p.spot_in.toLocaleString("en-IN")} (centre {p.center}). {p.credit >= 0 ? "Premium collected" : "Premium paid"} {inr(Math.abs(p.credit))}.
              {" "}Best {inr(p.best)}, worst {inr(p.worst)} so far.{p.rolls ? ` Re-centred ${p.rolls} time${p.rolls === 1 ? "" : "s"}.` : ""} Costs so far {inr(p.costs)} over {p.orders} orders.</p>
            <DataTable label="Open legs" columns={legCols} rows={snap.legs} rowKey={(l) => l.sym + l.side + l.entry} rowAttrs={(l): Record<string, string> => (l.open ? {} : { "data-closed": "1" })} />
            <Earlier label="Orders in this trade" count={openOrders.length} className="in-card">
              <OrderList events={openOrders} cur="INR" tz={TZ} />
            </Earlier>
          </>
        )}
        {today.length > 0 && (
          <div className="k-stack k-tight">
            {p && <span className="k-eyebrow">Closed today</span>}
            <TradeList rows={today} events={orders} shown={shown} toggle={toggle} />
          </div>
        )}
        {skips.length > 0 && (
          <Earlier label="Entries the India VIX filter held back" count={skips.length} className="in-card">
            <ul className="k-list muted" data-testid="vix-skips">
              {skips.map((e) => <li key={e.t}>{when(e.t, TZ, true, true)}: {e.why}</li>)}
            </ul>
          </Earlier>
        )}
      </Card>

      {running && p && snap.legs.some((l) => l.open) && <SessionModel snap={snap} />}

      {earlier.length > 0 && (
        <Card label="Earlier trades">
          <Earlier label="Earlier trades" count={earlier.length} open note={<Totals rows={earlier} />}>
            <TradeList rows={earlier} events={orders} shown={shown} toggle={toggle} />
          </Earlier>
        </Card>
      )}

      <Card label="Paper equity">
        <CardHead level={3} title="Paper equity" />
        {snap.equity_curve.length > 1 ? (
          <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((x) => t(x.t))} height={170} times={snap.equity_curve.map((x) => x.t)} tz={TZ}
            format={(v) => inr(v)} axisFormat={(v) => moneyCompact(v, "INR")} baseline={a.capital}
            lines={[{ label: "Account", values: snap.equity_curve.map((x) => x.eq), color: "var(--series-1)", width: 2 }]} />
        ) : <ChartEmpty height={170}>Fills in minute by minute while the market is open.</ChartEmpty>}
      </Card>
      {ask === "stop" && <ConfirmDialog title="Stop this session?" confirmLabel="Stop session" onConfirm={stop} onClose={() => setAsk(null)}>
        Any open paper position is left as it is, and it can't be restarted.</ConfirmDialog>}
      {ask === "delete" && <ConfirmDialog title={`Delete "${snap.name}"?`} confirmLabel="Delete session" onConfirm={remove} onClose={() => setAsk(null)}>
        Its orders go with it. This can't be undone.</ConfirmDialog>}
    </div>
  );
}

/** The open trade through the pricing model: its Greeks, its payoff today beside the one at expiry, and (on Pro) the
 * what-if sliders and the roll preview. Refreshed every 30 seconds from the live quotes; model estimates. */
function SessionModel({ snap }: { snap: OptionSnapshot }) {
  const { me } = useApp();
  const p = snap.position!, s = snap.strategy, inst = snap.instrument;
  const open = snap.legs.filter((l) => l.open);
  const held: HeldLeg[] = open.map((l) => ({ side: l.side, opt: l.opt, strike: l.strike, qty: l.qty, fill: l.entry }));
  const key = JSON.stringify(held);
  const booked = snap.legs.filter((l) => !l.open).reduce((n, l) => n + l.pnl, 0);     // legs closed earlier in this trade
  const [g, setG] = useState<HeldGreeks | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rollOpen, setRollOpen] = useState(false);
  useEffect(() => {
    let alive = true;
    const load = () => api<HeldGreeks>("/options/greeks", { method: "POST", body: { exchange: inst.exchange, underlying: inst.underlying, expiry: p.expiry,
      legs: JSON.parse(key), brokerage: s.costs.brokerage, freeze: s.costs.freeze } })
      .then((x) => { if (alive) { setG(x); setErr(null); } }).catch((e: ApiError) => { if (alive) setErr(e.message); });
    load();
    const h = window.setInterval(() => { if (!document.hidden) load(); }, 30_000);
    return () => { alive = false; window.clearInterval(h); };
  }, [key, inst.exchange, inst.underlying, p.expiry, s.costs.brokerage, s.costs.freeze]);
  const view = useMemo(() => {
    if (!g) return null;
    let m = 0;
    const rows: ModelRow[] = held.map((h, i) => ({ label: legName(h.side, h.strike, h.opt), held: h, g: g.legs[i], m: g.legs[i]?.iv ? g.model_legs[m++] ?? null : null }));
    const xs = priceGrid(g.spot, held.map((h) => h.strike));
    const ys = xs.map((x) => booked + atExpiry(held, x));
    return { rows, xs, ys };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [g, key, booked]);
  const charges = g?.close_charges ? p.costs + g.close_charges.total : null;
  return (
    <Card label="Open trade: Greeks and payoff" testId="session-model">
      <CardHead level={3} title="Open trade: Greeks and payoff" actions={<span className="k-note">model estimates</span>} />
      {!g || !view ? <p className="k-small k-muted">{err ?? "Pricing the open legs…"}</p> : (
        <>
          <ModelPanel model={g.model} rows={view.rows} xs={view.xs} base={booked} charges={charges} chargesLabel="the charges paid and to close"
            whatif={!!me?.plan_info?.features?.options_whatif} plan="Pro" name={inst.underlying} testId="session-model-panel"
            ariaLabel="The open trade's profit or loss at expiry and today across prices"
            expiry={[{ id: "expiry", label: "At expiry", values: view.ys },
              ...(charges != null ? [{ id: "after", label: "After charges", values: view.ys.map((y) => y - charges), dash: "4 4", width: 1.4 }] : [])]}
            markers={[{ x: g.spot, label: `Spot ${Math.round(g.spot).toLocaleString("en-IN")}`, kind: "spot" }]} />
          <p className="k-note">From the fills of the open legs{booked ? ", plus the legs already closed in this trade" : ""}. After charges takes off {inr(p.costs)} paid so far
            {g.close_charges ? ` and about ${inr(g.close_charges.total)} to close what's open` : ""}. The session itself squares off at {s.timing.squareoff}.</p>
          {me?.plan_info?.features?.options_whatif && (
            <Disclosure className="opt-charge-lines" testId="roll-fold" summary="Roll a leg: preview" onToggle={setRollOpen}>
              {rollOpen && <RollPreview legs={view.rows.map(({ label, held: h }) => ({ label, held: h }))} exchange={inst.exchange} underlying={inst.underlying}
                expiry={p.expiry} brokerage={s.costs.brokerage} freeze={s.costs.freeze} />}
              <p className="k-note">A preview only: the session keeps trading its own rules.</p>
            </Disclosure>
          )}
        </>
      )}
    </Card>
  );
}

type Trade = OptionSnapshot["trades"][number];
type OrderEvent = OptionSnapshot["events"][number];

/** "5 Oct, 09:30–11:30 IST", or both dates when a trade was held overnight. */
function span(x: Trade): string {
  const a = t(x.opened), b = t(x.closed), [da] = a.split(", "), [db, tb] = b.split(", ");
  return `${da === db ? `${a}–${tb}` : `${a} → ${b}`} ${tzLabel(TZ)}`;
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
              <span className="k-note">{x.why}{x.rolls ? `, ${x.rolls} roll${x.rolls === 1 ? "" : "s"}` : ""} · premium {inr(x.credit)} · before costs {inr(x.gross)} · costs {inr(x.costs)}</span>
            </span>
            <b className={`trade-pnl ${upDown(x.pnl)}`}>{inr(x.pnl)}</b>
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
  return <><span className={upDown(pnl)}>{inr(pnl)}</span> after costs · {won} won</>;
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
