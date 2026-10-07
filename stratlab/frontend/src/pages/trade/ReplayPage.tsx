import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, price, TF_NAME } from "../../lib/format";
import { upDown } from "../../lib/tradeUi";
import { CANDLE_LIMITS, CANDLE_SIZES, CANDLE_UNITS, candleCheck } from "../../lib/intervals";
import type { Instrument } from "../../lib/types";
import { simulate, type Action, type RBar, type ROrder, type Rates } from "../../lib/replay";
import { PriceChart, type Tf } from "../../charts/price/lazy";
import type { PriceLevel } from "../../charts/price/engine";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { Badge, Card, CardHead, ChipBar, ConfirmDialog, DataTable, Disclosure, EmptyState, ErrorState, Field, FieldGroup, FormActions, FormGrid, PageHeader, Seg, Select, Skeleton, Stat, StatRow, type Column } from "../../components/kit";
import "./trade.css";
import "./paper.css";
import { Info } from "../../components/ui";

/* /trade/replay: chart replay practice (Trade, Basic). A past stretch of candles on StratLab's own price chart, the
 * future hidden: step or play, go long or short with a stop and a target, and see the result after charges. The page
 * runs the same fill rules as the server (lib/replay.ts); finishing sends the orders back, the server fills them again
 * against the real candles, reveals a hidden symbol and date, and saves the trades to the journal as practice. A
 * historical simulation: facts, not advice. */

type Session = {
  id: string; tf: Tf; hidden: boolean; label: string; symbol: string | null; name: string | null; currency: string; market: string;
  bars: RBar[]; first: number; step: number; fno: boolean; kind: string; rates: Rates; brokerage: number; index: boolean; created: string; note: string;
};
type Overview = {
  allowed: boolean; plan: string; note: string; tfs: string[];
  sessions: { id: string; label: string; tf: string; created: string; hidden: boolean }[];
  practice: { n: number; wins: number; net: number; charges: number; last: string | null };
};
type Finished = {
  trades: { side: string; qty: number; entry: number; exit: number; entry_t: string; exit_t: string; why: string; gross: number; charges: number; net: number }[];
  summary: { n: number; wins: number; gross: number; charges: number; net: number };
  reveal: { symbol: string; name: string; start: string; from: string; to: string; candles: number };
  saved: number; why_not_saved: string | null; currency: string; skipped: { why: string }[];
};

const SPEEDS = [1, 5, 20];
const KEY = (id: string) => `stratlab.replay.${id}`;

function saved(id: string): { cursor: number; orders: ROrder[] } | null {
  try {
    const v = JSON.parse(localStorage.getItem(KEY(id)) ?? "null");
    return v && Number.isInteger(v.cursor) && Array.isArray(v.orders) ? v : null;
  } catch { return null; }
}
function keep(id: string, v: { cursor: number; orders: ROrder[] } | null) {
  try { if (v) localStorage.setItem(KEY(id), JSON.stringify(v)); else localStorage.removeItem(KEY(id)); } catch { /* not kept in this browser */ }
}
const signed = (v: number, cur: string) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v), cur, 2)}`;
const dayText = (iso: string) => new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

const tone = (n: number) => (n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));

function Setup({ ov, onStart }: { ov: Overview; onStart: (s: Session) => void }) {
  const { markets, fail, me } = useApp();
  const live = markets.filter((m) => m.status === "live" && m.id !== "CSV");
  const [mid, setMid] = useState("IN");
  const market = live.find((m) => m.id === mid) ?? live[0];
  const [inst, setInst] = useState<Instrument | null>(null);
  const [tf, setTf] = useState("1d");
  const [start, setStart] = useState(() => new Date(Date.now() - 400 * 86400_000).toISOString().slice(0, 10));
  const [busy, setBusy] = useState(false);
  const go = async (random: boolean) => {
    setBusy(true);
    try {
      onStart(await api<Session>("/trade/replay", { method: "POST", body: random ? { random: true, tf } : { instrument: inst?.id, tf, start } }));
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const sizes = CANDLE_SIZES.filter((c) => ov.tfs.includes(c.value));
  return (
    <Card label="New replay">
      <CardHead title="New replay" />
      <div className="k-stack">
        <FieldGroup label="Candle size" info={`Smaller candles go back only a few months (5-minute about four), daily candles years. ${CANDLE_LIMITS}`} infoLabel="About candle sizes">
          <ChipBar label="Candle size" value={tf} onChange={setTf} options={sizes.map((c) => ({ value: c.value, label: TF_NAME[c.value] ?? c.label }))}
            custom={{ storageKey: `stratlab.chips.replay.${me?.id ?? "anon"}`, units: CANDLE_UNITS, defaultUnit: "min", validate: candleCheck(ov.tfs) }} />
        </FieldGroup>
        <div className="k-row">
          <button type="button" className="btn outline" disabled={busy} onClick={() => go(true)}>Random stock and date</button>
          <Info>A NIFTY 50 stock on a random past date. The symbol and the dates stay hidden until you finish, so you can't remember what happened next.</Info>
        </div>
        <span className="k-small k-muted">Or pick one yourself</span>
        <FormGrid label="Pick a stock and a date" onSubmit={(e) => { e.preventDefault(); void go(false); }}>
          {live.length > 1 && (
            <Field label="Market">{(id) => <Select id={id} value={market?.id ?? ""} onChange={(v) => { setMid(v); setInst(null); }} options={live.map((m) => ({ value: m.id, label: m.name }))} />}</Field>
          )}
          <FieldGroup label="Instrument" wide>
            {inst ? (
              <div className="k-row"><Badge tone="ok">{inst.symbol}</Badge><button type="button" className="btn quiet sm" onClick={() => setInst(null)}>Pick another</button></div>
            ) : market ? <InstrumentSearch market={market} compact onPick={setInst} /> : <p className="k-small k-muted">Market data is offline right now.</p>}
          </FieldGroup>
          <Field label="Start date" type="date" value={start} max={new Date(Date.now() - 86400_000).toISOString().slice(0, 10)} onChange={(e) => setStart(e.target.value)} />
          <FormActions><button type="submit" className="btn" disabled={busy || !inst || !start}>{busy ? "Loading candles…" : "Start replay"}</button></FormActions>
        </FormGrid>
        <p className="k-note">Daily candles go back years; smaller candles only a few months (5-minute about four).</p>
      </div>
    </Card>
  );
}

function Player({ s, onDone, onDiscard }: { s: Session; onDone: (f: Finished) => void; onDiscard: () => void }) {
  const { fail, notify } = useApp();
  const was = useMemo(() => saved(s.id), [s.id]);
  const last = s.bars.length - 1;
  const [cursor, setCursor] = useState(() => Math.min(Math.max(was?.cursor ?? s.first - 1, s.first - 1), last));
  const [orders, setOrders] = useState<ROrder[]>(() => was?.orders ?? []);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [qty, setQty] = useState(String(s.step >= 1 ? s.step : 1));
  const [picking, setPicking] = useState<"stop" | "target" | null>(null);
  const [level, setLevel] = useState("");
  const [busy, setBusy] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const cur = s.currency;

  useEffect(() => { keep(s.id, { cursor, orders }); }, [s.id, cursor, orders]);
  useEffect(() => {
    if (!playing) return;
    const t = window.setInterval(() => setCursor((c) => { if (c >= last) { setPlaying(false); return c; } return c + 1; }), 1000 / speed);
    return () => window.clearInterval(t);
  }, [playing, speed, last]);

  const sim = useMemo(() => simulate(s.bars, orders, s.first, cursor, s.kind, s.rates, s.step, false), [s, orders, cursor]);
  const shown = useMemo(() => s.bars.slice(0, cursor + 1), [s.bars, cursor]);
  const markers = useMemo(() => sim.fills.map((f) => ({ t: f.t, side: f.side })), [sim.fills]);
  const pos = sim.position;
  const levels = useMemo<PriceLevel[]>(() => pos ? [
    { price: pos.avg, label: "Entry", tone: "muted" as const },
    ...(pos.stop != null ? [{ price: pos.stop, label: "Stop", tone: "down" as const }] : []),
    ...(pos.target != null ? [{ price: pos.target, label: "Target", tone: "up" as const }] : []),
  ] : [], [pos]);
  const closedNet = sim.trades.reduce((n, t) => n + t.net, 0);
  const closePx = s.bars[cursor].c;
  const atEnd = cursor >= last;

  const act = (action: Action, extra: Partial<ROrder> = {}) => setOrders((o) => [...o, { i: cursor, action, ...extra }]);
  const trade = (action: "long" | "short") => {
    const q = Number(qty.replace(/,/g, ""));
    if (!Number.isFinite(q) || q <= 0) { notify("Enter a quantity above 0."); return; }
    act(action, { qty: q });
  };
  const setLine = (kind: "stop" | "target", p: number) => {
    if (!pos) { notify("There's no open position to protect."); return; }
    const long = pos.side === "long";
    const ok = kind === "stop" ? (long ? p < closePx : p > closePx) : (long ? p > closePx : p < closePx);
    if (!ok) { notify(`A ${pos.side}'s ${kind} goes ${(kind === "stop") === long ? "below" : "above"} the last close (${price(closePx, cur)}).`); return; }
    act(kind, { price: Math.round(p * 100) / 100 });
    setPicking(null); setLevel("");
  };
  const finish = async (save: boolean) => {
    setPlaying(false); setBusy(true);
    try {
      const f = await api<Finished>(`/trade/replay/${s.id}/finish`, { method: "POST", body: { cursor, orders, save } });
      keep(s.id, null);
      onDone(f);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const discard = async () => {
    setDiscarding(false);
    try { await api(`/trade/replay/${s.id}`, { method: "DELETE" }); } catch { /* already gone */ }
    keep(s.id, null);
    onDiscard();
  };

  return (
    <div className="k-page">
      <div className="k-spread k-session-head">
        <div className="k-stack k-tight">
          <span className="k-eyebrow">{TF_NAME[s.tf]} candles{s.hidden ? " · dates hidden until the end" : ""}</span>
          <h2 className="k-session-name" data-testid="rp-label">{s.hidden ? "Hidden symbol" : s.symbol}</h2>
        </div>
        <span className="k-small k-muted" data-testid="rp-progress">Candle {Math.max(0, cursor - s.first + 1)} of {last - s.first + 1}</span>
      </div>
      <PriceChart symbol={s.hidden ? "Hidden" : s.symbol ?? ""} storageKey={`REPLAY-${s.id}`.slice(0, 40)} currency={cur} bars={shown} tf={s.tf} replay
        timeframes={[s.tf]} markers={markers} levels={levels} height={380}
        onPickPrice={picking ? (p) => setLine(picking, p) : null}
        note={picking ? `Click the chart at the ${picking} price, or type it below.` : "Future candles are hidden. Orders fill at the last close shown."} />

      <Card label="Replay controls">
        <CardHead level={3} title="Replay controls" actions={<Seg label="Speed" options={SPEEDS.map((x) => ({ value: String(x), label: `${x}×` }))} value={String(speed)} onChange={(v) => setSpeed(Number(v))} />} />
        <div className="k-row">
          <button type="button" className="btn" onClick={() => setPlaying(!playing)} disabled={atEnd} aria-pressed={playing}>{playing ? "Pause" : "Play"}</button>
          <button type="button" className="btn outline" onClick={() => setCursor((c) => Math.min(c + 1, last))} disabled={atEnd || playing}>Next candle</button>
        </div>
        <FormGrid label="Practice order" onSubmit={(e) => e.preventDefault()}>
          <Field label={s.fno ? "Quantity (units)" : "Quantity"} aria-label="Quantity" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} />
          <FormActions>
            <button type="button" className="btn outline" onClick={() => trade("long")}>Long</button>
            <button type="button" className="btn outline" onClick={() => trade("short")}>Short</button>
            <button type="button" className="btn outline" onClick={() => act("flat")} disabled={!pos}>Flat</button>
          </FormActions>
          <Field label="Stop or target" aria-label="Stop or target price" inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} placeholder={price(closePx, cur)} />
          <FormActions>
            <button type="button" className="btn quiet" disabled={!pos} onClick={() => level.trim() ? setLine("stop", Number(level.replace(/,/g, ""))) : setPicking(picking === "stop" ? null : "stop")}
              aria-pressed={picking === "stop"}>{level.trim() ? "Set stop" : "Stop on chart"}</button>
            <button type="button" className="btn quiet" disabled={!pos} onClick={() => level.trim() ? setLine("target", Number(level.replace(/,/g, ""))) : setPicking(picking === "target" ? null : "target")}
              aria-pressed={picking === "target"}>{level.trim() ? "Set target" : "Target on chart"}</button>
            {pos?.stop != null && <button type="button" className="btn quiet sm" onClick={() => act("cancel_stop")}>Remove stop</button>}
            {pos?.target != null && <button type="button" className="btn quiet sm" onClick={() => act("cancel_target")}>Remove target</button>}
          </FormActions>
        </FormGrid>
      </Card>

      <Card label="Practice account">
        <CardHead level={3} title="Practice account" />
        <StatRow label="Practice account">
          <Stat item label="Position" value={<span data-testid="rp-position">{pos ? `${pos.side === "long" ? "Long" : "Short"} ${pos.qty.toLocaleString("en-IN", { maximumFractionDigits: 4 })} at ${price(pos.avg, cur)}` : "None"}</span>} />
          <Stat item label={<>Open P&amp;L<Info>The open position at the last close, before the charges to close it.</Info></>} value={pos ? signed(pos.unrealised, cur) : "–"} tone={pos ? tone(pos.unrealised) : undefined} />
          <Stat item label="Closed trades" value={<span data-testid="rp-closed">{sim.trades.length} ({sim.trades.filter((t) => t.net > 0).length} won)</span>} />
          <Stat item label="Closed P&L after charges" value={signed(closedNet, cur)} tone={tone(closedNet)} />
        </StatRow>
        {s.index && <p className="k-note">An index can't be traded itself, so no charges are counted on it.</p>}
        {sim.skipped.length > 0 && <p className="k-note">{sim.skipped.length} order{sim.skipped.length === 1 ? "" : "s"} did nothing ({sim.skipped[sim.skipped.length - 1].why.toLowerCase()}).</p>}
        <div className="k-row">
          <button type="button" className="btn" disabled={busy} onClick={() => finish(true)}>{busy ? "Finishing…" : "Finish and save to journal"}</button>
          <button type="button" className="btn quiet" disabled={busy} onClick={() => finish(false)}>Finish without saving</button>
          <button type="button" className="btn quiet danger" disabled={busy} onClick={() => setDiscarding(true)}>Discard</button>
        </div>
      </Card>
      {discarding && <ConfirmDialog title="Throw this replay away?" confirmLabel="Throw it away" onConfirm={discard} onClose={() => setDiscarding(false)}>Nothing is saved.</ConfirmDialog>}
    </div>
  );
}

function Result({ f, onNew }: { f: Finished; onNew: () => void }) {
  const cur = f.currency;
  const r = f.reveal;
  type T = Finished["trades"][number];
  const cols: Column<T>[] = [
    { key: "side", header: "Side", cell: (t) => (t.side === "long" ? "Long" : "Short") },
    { key: "qty", header: "Qty", numeric: true, cell: (t) => t.qty.toLocaleString("en-IN", { maximumFractionDigits: 4 }) },
    { key: "px", header: "Entry → exit", numeric: true, cell: (t) => `${price(t.entry, cur)} → ${price(t.exit, cur)}` },
    { key: "why", header: "Closed by", wrap: true, cell: (t) => t.why },
    { key: "ch", header: "Charges", numeric: true, cell: (t) => money(t.charges, cur, 2) },
    { key: "net", header: "Net", numeric: true, cell: (t) => <span className={upDown(t.net)}>{signed(t.net, cur)}</span> },
  ];
  return (
    <Card label="Replay finished">
      <CardHead title={`Replay finished: ${r.symbol}`} />
      <p className="k-small" data-testid="rp-reveal">{r.name && r.name !== r.symbol ? `${r.name}, ` : ""}{r.candles} candle{r.candles === 1 ? "" : "s"} played from {dayText(r.from)} to {dayText(r.to)}.</p>
      <StatRow label="Result">
        <Stat item label="Trades" value={`${f.summary.n} (${f.summary.wins} won)`} />
        <Stat item label="Before charges" value={signed(f.summary.gross, cur)} tone={tone(f.summary.gross)} />
        <Stat item label="Charges" value={money(f.summary.charges, cur, 2)} />
        <Stat item label="After charges" value={signed(f.summary.net, cur)} tone={tone(f.summary.net)} />
      </StatRow>
      {f.trades.length > 0 && <DataTable label="Practice trades" columns={cols} rows={f.trades} rowKey={(t) => `${t.entry_t}${t.exit_t}${t.qty}`} />}
      <p className="k-small" role="status">
        {f.saved ? <>{f.saved} practice trade{f.saved === 1 ? "" : "s"} saved to your <Link className="link" to="/trade/journal">trade journal</Link>, marked as practice.</>
          : f.why_not_saved ?? (f.trades.length ? "Not saved to the journal." : "No trades to save.")}
      </p>
      <button type="button" className="btn k-btn-end" onClick={onNew}>Another replay</button>
    </Card>
  );
}

export function ReplayPage() {
  const { fail } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
  const [s, setS] = useState<Session | null>(null);
  const [done, setDone] = useState<Finished | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const load = useCallback(() => api<Overview>("/trade/replay").then((o) => { setOv(o); setFailed(false); }).catch((e) => { fail(e); setFailed(true); }), [fail]);
  useEffect(() => { load(); }, [load]);
  const open = async (id: string) => {
    try { setS(await api<Session>(`/trade/replay/${id}`)); setDone(null); } catch (e) { fail(e); load(); }
  };

  return (
    <div className="k-page" ref={top}>
      <PageHeader eyebrow="Trade · Practise" title="Chart replay"
        lede="Step through a past chart one candle at a time with the future hidden, place practice orders, and see the result after charges. Finished sessions go to your journal as practice. A historical simulation: facts, not advice." />
      {failed && !ov ? <ErrorState title="Chart replay couldn't be opened" action={{ label: "Try again", onClick: () => { void load(); } }}>Nothing was changed.</ErrorState>
        : !ov ? <Card><Skeleton label="Opening chart replay" /></Card> : !ov.allowed ? (
        <EmptyState title="Chart replay practice" action={{ label: "See plans", to: "/plans" }}>It is on the {ov.plan} plan.</EmptyState>
      ) : done ? <Result f={done} onNew={() => { setDone(null); setS(null); load(); }} />
        : s ? <Player key={s.id} s={s} onDone={(f) => { setDone(f); setS(null); load(); }} onDiscard={() => { setS(null); load(); }} />
        : (
          <>
            {ov.sessions.length > 0 && (
              <Card label="Unfinished">
                <CardHead level={3} title="Unfinished" />
                <ul className="k-list plain">
                  {ov.sessions.map((x) => (
                    <li key={x.id} className="k-spread">
                      <span className="k-small">{x.label} · {TF_NAME[x.tf] ?? x.tf} candles</span>
                      <button type="button" className="btn sm outline" onClick={() => open(x.id)}>Continue</button>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            <Setup ov={ov} onStart={(x) => { setS(x); setDone(null); top.current?.scrollIntoView({ block: "start" }); }} />
            {ov.practice.n > 0 ? (
              <p className="k-small k-muted" data-testid="rp-practice">{ov.practice.n} practice trade{ov.practice.n === 1 ? "" : "s"} in your <Link className="link" to="/trade/journal">journal</Link>, {signed(ov.practice.net, "INR")} after charges{ov.practice.last ? `, the latest closed ${dayText(ov.practice.last)}` : ""}.</p>
            ) : <EmptyState title="No practice trades yet">Finish a replay and its trades show in your journal, where the verdict's checks can run on them.</EmptyState>}
            <Disclosure summary="How practice orders fill">
              <p className="k-small k-muted">{ov.note} A long's stop fills when a candle's low reaches it (at the open if it opened below), its target when the high does; when one candle reaches both, the stop counts first. What's open when you finish closes at the last candle shown.</p>
            </Disclosure>
          </>
        )}
    </div>
  );
}
