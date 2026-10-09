import { useState } from "react";
import { STOP_DIALOG } from "../lib/paperText";
import { useApp } from "../lib/app";
import { money, price, qty, TF_NAME, tzOf, when } from "../lib/format";
import { HELP } from "../lib/help";
import { upDown } from "../lib/tradeUi";
import { ChartEmpty, LineChart } from "./Charts";
import { ChartFrame, Badge, Card, CardHead, ConfirmDialog, DataTable, Disclosure, Notice, Stat, StatRow, type Column } from "./kit";
import { moneyCompact } from "../lib/chartFormat";
import { Info } from "./ui";
import { Earlier, splitToday } from "./Earlier";
import { OrderList } from "./OrderList";
import "../pages/trade/trade.css";
import "../pages/trade/paper.css";
import { sessionFeed } from "../lib/marketHours";

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
type Member = GroupSnapshot["members"][number];
const tone = (n: number | null) => (n == null || n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));

export function GroupSession({ snap, onStop, onDelete }: { snap: GroupSnapshot; onStop: () => void; onDelete: () => void }) {
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);
  const running = snap.status === "running";
  const cur = snap.instrument.currency || (snap.instrument.market === "IN" ? "INR" : "");
  const tz = tzOf(snap.instrument as never);
  const a = snap.account;
  const holding = snap.members.filter((m) => m.position);
  const { today, earlier } = splitToday(snap.events, (e) => e.t, tz);     // today's orders in view, the earlier ones folded
  const closedPnl = earlier.reduce((n, e) => n + (e.pnl ?? 0), 0);
  const { markets } = useApp();
  const feed = sessionFeed({ feedConnected: snap.feed_connected, lastTickAt: snap.last_tick_at, market: markets.find((m) => m.id === snap.instrument.market) });
  const holdCols: Column<Member>[] = [
    { key: "sym", header: "Symbol", rowHeader: true, cell: (m) => <b>{m.symbol}</b> },
    { key: "side", header: "Side", cell: (m) => (m.position!.side === "short" ? "Short" : "Long") },
    { key: "qty", header: "Qty", numeric: true, cell: (m) => qty(m.position!.qty) },
    { key: "entry", header: "Entry", numeric: true, cell: (m) => price(m.position!.entry, cur) },
    { key: "now", header: "Now", numeric: true, cell: (m) => price(m.price, cur) },
    { key: "stop", header: "Stop", numeric: true, cell: (m) => (m.position!.stop ? price(m.position!.stop, cur) : "–") },
    { key: "tgt", header: "Target", numeric: true, cell: (m) => (m.position!.target ? price(m.position!.target, cur) : "–") },
    { key: "pnl", header: "P&L", numeric: true, cell: (m) => <span className={upDown(m.position!.unrealised)}>{money(m.position!.unrealised, cur)}</span> },
  ];
  const allCols: Column<Member>[] = [
    { key: "sym", header: "Symbol", rowHeader: true, cell: (m) => <b>{m.symbol}</b> },
    { key: "price", header: "Price", numeric: true, cell: (m) => price(m.price, cur) },
    ...(snap.fast?.maxSpreadPct ? [{ key: "spread", header: "Spread", numeric: true, cell: (m: Member) => (m.spread == null ? "–" : `${m.spread.toFixed(2)}%`) }] : []),
    { key: "trades", header: "Trades", numeric: true, cell: (m) => m.trades },
    { key: "skipped", header: "Skipped", numeric: true, cell: (m) => m.skipped || "–" },
    { key: "pnl", header: "Closed P&L", numeric: true, cell: (m) => <span className={upDown(m.pnl)}>{money(m.pnl, cur)}</span> },
  ];
  const f = snap.fast || {}, sk = a.skipped || { spread: 0, price: 0 };
  const on = [f.ticks && "faster entries on the live price", f.maxSpreadPct && `spread limit ${f.maxSpreadPct}%`, f.minPrice && `nothing under ${price(f.minPrice, cur)}`].filter(Boolean);
  const skipped = [sk.spread && `${sk.spread} for a wide or unknown spread`, sk.price && `${sk.price} for price`].filter(Boolean);
  return (
    <div className="k-page">
      <div className="k-spread k-session-head">
        <div className="k-stack k-tight">
          <span className="k-eyebrow">{snap.instrument.symbol} · {TF_NAME[snap.strategy.tf]} candles · started {when(snap.started_at, tz, true, true)}</span>
          <h2 className="k-session-name">{snap.name}</h2>
        </div>
        <div className="k-row">
          {running && <span className="k-row"><Badge tone={feed.tone}>{feed.text}</Badge><Info>{HELP.feed}</Info></span>}
          {running ? <button type="button" className="btn danger" onClick={() => setAsk("stop")}>Stop session</button>
            : <><Badge tone="plain">{snap.status}</Badge><button type="button" className="btn danger sm" onClick={() => setAsk("delete")}>Delete</button></>}
        </div>
      </div>
      {!running && snap.stop_reason && <Notice>Stopped: {snap.stop_reason}</Notice>}
      {!running && a.open > 0 && <Notice className="stopped-open">{a.open === 1 ? "1 position was" : `${a.open} positions were`} open at the stop and stay open, each valued at its last price before the stop. Nothing more is traded.</Notice>}
      {running && a.halted && <Notice tone="warn">The group's daily loss cap was hit: everything was closed and nothing new opens until tomorrow.</Notice>}
      {snap.skipped.length > 0 && <p className="k-note">Left out (not enough live history): {snap.skipped.join(" · ")}</p>}
      {on.length > 0 && <p className="k-note">On: {on.join(" · ")}.{skipped.length ? ` Entries skipped: ${skipped.join(", ")}.` : ""}</p>}
      <Card label="The account">
        <StatRow label="Group account">
          <Stat item label="Open positions" value={`${a.open} of ${a.max_open}`} />
          <Stat item label="Today" value={money(a.today, cur)} tone={tone(a.today)} />
          <Stat item label="Closed trades" value={money(a.realised, cur)} tone={tone(a.realised)} note={`${a.trades} trade${a.trades === 1 ? "" : "s"}`} />
          <Stat item label="Paper account" value={money(a.equity, cur)} tone={tone(a.equity - a.capital)} note="Fake money" />
        </StatRow>
      </Card>
      <div className="nb-grid">
        <div className="k-page">
          <Card label="Open positions">
            <CardHead level={3} title="Open positions" />
            {holding.length === 0 ? <p className="k-small k-muted">{running ? "None right now. Positions open as the rules fire, up to " + a.max_open + " at once." : "None."}</p>
              : <DataTable label="Open positions" columns={holdCols} rows={holding} rowKey={(m) => m.id} />}
          </Card>
          <ChartFrame title="Paper equity">
            {snap.equity_curve.length > 1 ? (
              <LineChart ariaLabel="Paper account value" labels={snap.equity_curve.map((p) => when(p.t, tz, true))} height={170} times={snap.equity_curve.map((p) => p.t)} tz={tz}
                format={(v) => money(v, cur)} axisFormat={(v) => moneyCompact(v, cur ?? "INR")} baseline={a.capital}
                lines={[{ label: "Account", values: snap.equity_curve.map((p) => p.eq), color: "var(--series-1)", width: 2 }]} />
            ) : <ChartEmpty height={170}>Fills in as candles close.</ChartEmpty>}
          </ChartFrame>
          {snap.members.length > 0 && (
            <Card label="Every member">
              <Disclosure summary={`Every member (${snap.members.length})`}>
                <DataTable label="Every member" columns={allCols} rows={snap.members} rowKey={(m) => m.id} />
              </Disclosure>
            </Card>
          )}
        </div>
        <Card label="Orders today">
          <CardHead level={3} title="Orders today" />
          {today.length ? <OrderList events={today} cur={cur} tz={tz} newest tf={snap.strategy.tf} close={markets.find((m) => m.id === snap.instrument.market)?.hours?.close ?? null} />
            : <p className="k-small k-muted">{snap.events.length ? "No orders today." : "None yet."}</p>}
          <Earlier label="Earlier orders" count={earlier.length} className="in-card" open
            note={<><span className={upDown(closedPnl)}>{money(closedPnl, cur)}</span> on closed trades</>}>
            <OrderList events={earlier} cur={cur} tz={tz} newest tf={snap.strategy.tf} close={markets.find((m) => m.id === snap.instrument.market)?.hours?.close ?? null} />
          </Earlier>
        </Card>
      </div>
      {ask === "stop" && <ConfirmDialog title="Stop this session?" confirmLabel="Stop session" onConfirm={() => { setAsk(null); onStop(); }} onClose={() => setAsk(null)}>
        {STOP_DIALOG}</ConfirmDialog>}
      {ask === "delete" && <ConfirmDialog title={`Delete "${snap.name}"?`} confirmLabel="Delete session" onConfirm={() => { setAsk(null); onDelete(); }} onClose={() => setAsk(null)}>
        Its orders go with it. This can't be undone.</ConfirmDialog>}
    </div>
  );
}
