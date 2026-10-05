import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, price } from "../../lib/format";
import type { Instrument } from "../../lib/types";
import { simulate, type Action, type RBar, type ROrder, type Rates } from "../../lib/replay";
import { PriceChart, type Tf } from "../../charts/price/lazy";
import type { PriceLevel } from "../../charts/price/engine";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { Empty, Info, Loading } from "../../components/ui";

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

const TF_NAME: Record<string, string> = { "1d": "Daily", "1h": "1-hour", "15m": "15-minute", "5m": "5-minute" };
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

function Setup({ ov, onStart }: { ov: Overview; onStart: (s: Session) => void }) {
  const { markets, fail } = useApp();
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
  return (
    <section className="card stack" style={{ gap: 14 }} aria-labelledby="rp-new">
      <h2 id="rp-new" className="h2">New replay</h2>
      <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
        <label className="field">Candles
          <select value={tf} onChange={(e) => setTf(e.target.value)} aria-label="Candle size">
            {ov.tfs.map((t) => <option key={t} value={t}>{TF_NAME[t] ?? t}</option>)}
          </select>
        </label>
        <button className="btn outline" disabled={busy} onClick={() => go(true)}>Random stock and date</button>
        <Info>{"A NIFTY 50 stock on a random past date. The symbol and the dates stay hidden until you finish, so you can't remember what happened next."}</Info>
      </div>
      <div className="stack" style={{ gap: 10 }}>
        <span className="small muted">Or pick one yourself</span>
        {live.length > 1 && (
          <label className="field" style={{ maxWidth: 260 }}>Market
            <select value={market?.id ?? ""} onChange={(e) => { setMid(e.target.value); setInst(null); }} aria-label="Market">
              {live.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
          </label>
        )}
        {inst ? (
          <div className="row wrap" style={{ gap: 10 }}>
            <span className="pill">{inst.symbol}</span>
            <button className="link" onClick={() => setInst(null)}>Pick another</button>
          </div>
        ) : market ? <InstrumentSearch market={market} compact onPick={setInst} /> : <p className="small muted">Market data is offline right now.</p>}
        <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
          <label className="field">Start date
            <input type="date" value={start} max={new Date(Date.now() - 86400_000).toISOString().slice(0, 10)} onChange={(e) => setStart(e.target.value)} aria-label="Start date" />
          </label>
          <button className="btn" disabled={busy || !inst || !start} onClick={() => go(false)}>{busy ? "Loading candles…" : "Start replay"}</button>
        </div>
        <p className="tiny muted" style={{ margin: 0 }}>Daily candles go back years; smaller candles only a few months (5-minute about four).</p>
      </div>
    </section>
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
    if (!confirm("Throw this replay away? Nothing is saved.")) return;
    try { await api(`/trade/replay/${s.id}`, { method: "DELETE" }); } catch { /* already gone */ }
    keep(s.id, null);
    onDiscard();
  };

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
        <div className="stack" style={{ gap: 2 }}>
          <span className="eyebrow">{TF_NAME[s.tf]} candles{s.hidden ? " · dates hidden until the end" : ""}</span>
          <h2 className="h2" data-testid="rp-label">{s.hidden ? "Hidden symbol" : s.symbol}</h2>
        </div>
        <span className="small muted" data-testid="rp-progress">Candle {Math.max(0, cursor - s.first + 1)} of {last - s.first + 1}</span>
      </div>
      <PriceChart symbol={s.hidden ? "Hidden" : s.symbol ?? ""} storageKey={`REPLAY-${s.id}`.slice(0, 40)} currency={cur} bars={shown} tf={s.tf}
        timeframes={[s.tf]} markers={markers} levels={levels} height={380}
        onPickPrice={picking ? (p) => setLine(picking, p) : null}
        note={picking ? `Click the chart at the ${picking} price, or type it below.` : "Future candles are hidden. Orders fill at the last close shown."} />

      <section className="card stack rp-controls" style={{ gap: 12 }} aria-label="Replay controls">
        <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
          <button className="btn" onClick={() => setPlaying(!playing)} disabled={atEnd} aria-pressed={playing}>{playing ? "Pause" : "Play"}</button>
          <button className="btn outline" onClick={() => setCursor((c) => Math.min(c + 1, last))} disabled={atEnd || playing}>Next candle</button>
          <div className="seg" role="group" aria-label="Speed">
            {SPEEDS.map((x) => <button key={x} type="button" aria-pressed={speed === x} onClick={() => setSpeed(x)}>{x}×</button>)}
          </div>
        </div>
        <div className="row wrap" style={{ gap: 8, alignItems: "flex-end" }}>
          <label className="field" style={{ width: 130 }}>{s.fno ? "Quantity (units)" : "Quantity"}
            <input inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} aria-label="Quantity" />
          </label>
          <button className="btn outline" onClick={() => trade("long")}>Long</button>
          <button className="btn outline" onClick={() => trade("short")}>Short</button>
          <button className="btn outline" onClick={() => act("flat")} disabled={!pos}>Flat</button>
        </div>
        <div className="row wrap" style={{ gap: 8, alignItems: "flex-end" }}>
          <label className="field" style={{ width: 130 }}>Stop or target
            <input inputMode="decimal" value={level} onChange={(e) => setLevel(e.target.value)} placeholder={price(closePx, cur)} aria-label="Stop or target price" />
          </label>
          <button className="btn quiet" disabled={!pos} onClick={() => level.trim() ? setLine("stop", Number(level.replace(/,/g, ""))) : setPicking(picking === "stop" ? null : "stop")}
            aria-pressed={picking === "stop"}>{level.trim() ? "Set stop" : "Stop on chart"}</button>
          <button className="btn quiet" disabled={!pos} onClick={() => level.trim() ? setLine("target", Number(level.replace(/,/g, ""))) : setPicking(picking === "target" ? null : "target")}
            aria-pressed={picking === "target"}>{level.trim() ? "Set target" : "Target on chart"}</button>
          {pos?.stop != null && <button className="btn quiet sm" onClick={() => act("cancel_stop")}>Remove stop</button>}
          {pos?.target != null && <button className="btn quiet sm" onClick={() => act("cancel_target")}>Remove target</button>}
        </div>
      </section>

      <section className="card stack" style={{ gap: 10 }} aria-labelledby="rp-acct">
        <h3 id="rp-acct" className="h3">Practice account</h3>
        <div className="stat-row">
          <div className="stat"><span className="tiny muted">Position</span><b className="num" data-testid="rp-position">{pos ? `${pos.side === "long" ? "Long" : "Short"} ${pos.qty.toLocaleString("en-IN", { maximumFractionDigits: 4 })} at ${price(pos.avg, cur)}` : "None"}</b></div>
          <div className="stat"><span className="tiny muted">Open P&amp;L<Info>{"The open position at the last close, before the charges to close it."}</Info></span><b className="num">{pos ? signed(pos.unrealised, cur) : "–"}</b></div>
          <div className="stat"><span className="tiny muted">Closed trades</span><b className="num" data-testid="rp-closed">{sim.trades.length} ({sim.trades.filter((t) => t.net > 0).length} won)</b></div>
          <div className="stat"><span className="tiny muted">Closed P&amp;L after charges</span><b className="num">{signed(closedNet, cur)}</b></div>
        </div>
        {s.index && <p className="tiny muted" style={{ margin: 0 }}>An index can't be traded itself, so no charges are counted on it.</p>}
        {sim.skipped.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>{sim.skipped.length} order{sim.skipped.length === 1 ? "" : "s"} did nothing ({sim.skipped[sim.skipped.length - 1].why.toLowerCase()}).</p>}
        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn" disabled={busy} onClick={() => finish(true)}>{busy ? "Finishing…" : "Finish and save to journal"}</button>
          <button className="btn quiet" disabled={busy} onClick={() => finish(false)}>Finish without saving</button>
          <button className="btn quiet danger" disabled={busy} onClick={discard}>Discard</button>
        </div>
      </section>
    </div>
  );
}

function Result({ f, onNew }: { f: Finished; onNew: () => void }) {
  const cur = f.currency;
  const r = f.reveal;
  return (
    <section className="card stack" style={{ gap: 14 }} aria-labelledby="rp-result">
      <h2 id="rp-result" className="h2">Replay finished: {r.symbol}</h2>
      <p className="small" style={{ margin: 0 }} data-testid="rp-reveal">{r.name && r.name !== r.symbol ? `${r.name}, ` : ""}{r.candles} candle{r.candles === 1 ? "" : "s"} played from {dayText(r.from)} to {dayText(r.to)}.</p>
      <div className="stat-row">
        <div className="stat"><span className="tiny muted">Trades</span><b className="num">{f.summary.n} ({f.summary.wins} won)</b></div>
        <div className="stat"><span className="tiny muted">Before charges</span><b className="num">{signed(f.summary.gross, cur)}</b></div>
        <div className="stat"><span className="tiny muted">Charges</span><b className="num">{money(f.summary.charges, cur, 2)}</b></div>
        <div className="stat"><span className="tiny muted">After charges</span><b className="num">{signed(f.summary.net, cur)}</b></div>
      </div>
      {f.trades.length > 0 && (
        <div className="table-wrap" style={{ margin: 0 }}>
          <table className="nums" aria-label="Practice trades">
            <thead><tr><th>Side</th><th>Qty</th><th>Entry → exit</th><th>Closed by</th><th>Charges</th><th>Net</th></tr></thead>
            <tbody>{f.trades.map((t, i) => (
              <tr key={i}><td>{t.side === "long" ? "Long" : "Short"}</td><td>{t.qty.toLocaleString("en-IN", { maximumFractionDigits: 4 })}</td>
                <td className="small">{price(t.entry, cur)} → {price(t.exit, cur)}</td><td className="small">{t.why}</td>
                <td>{money(t.charges, cur, 2)}</td><td>{signed(t.net, cur)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      )}
      <p className="small" style={{ margin: 0 }} role="status">
        {f.saved ? <>{f.saved} practice trade{f.saved === 1 ? "" : "s"} saved to your <Link className="link" to="/trade/journal">trade journal</Link>, marked as practice.</>
          : f.why_not_saved ?? (f.trades.length ? "Not saved to the journal." : "No trades to save.")}
      </p>
      <button className="btn" style={{ alignSelf: "flex-start" }} onClick={onNew}>Another replay</button>
    </section>
  );
}

export function ReplayPage() {
  const { fail } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);
  const [s, setS] = useState<Session | null>(null);
  const [done, setDone] = useState<Finished | null>(null);
  const top = useRef<HTMLDivElement>(null);
  const load = useCallback(() => api<Overview>("/trade/replay").then(setOv).catch((e) => { fail(e); }), [fail]);
  useEffect(() => { load(); }, [load]);
  const open = async (id: string) => {
    try { setS(await api<Session>(`/trade/replay/${id}`)); setDone(null); } catch (e) { fail(e); load(); }
  };

  return (
    <div className="stack" style={{ gap: 20 }} ref={top}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Trade · practice</span>
        <h1 className="page-title">Chart replay</h1>
        <p className="page-sub" style={{ maxWidth: "68ch" }}>Step through a past chart one candle at a time with the future hidden, place practice orders, and see the result after charges. Finished sessions go to your journal as practice. A historical simulation: facts, not advice.</p>
      </div>
      {!ov ? <Loading label="Opening chart replay" /> : !ov.allowed ? (
        <section className="card dashed stack" style={{ gap: 8 }}>
          <p className="small" style={{ margin: 0 }}><b>Chart replay practice</b> is on the {ov.plan} plan.</p>
          <Link to="/plans" className="btn sm" style={{ alignSelf: "flex-start" }}>See plans</Link>
        </section>
      ) : done ? <Result f={done} onNew={() => { setDone(null); setS(null); load(); }} />
        : s ? <Player key={s.id} s={s} onDone={(f) => { setDone(f); setS(null); load(); }} onDiscard={() => { setS(null); load(); }} />
        : (
          <>
            {ov.sessions.length > 0 && (
              <section className="card stack" style={{ gap: 10 }} aria-labelledby="rp-open">
                <h2 id="rp-open" className="h3">Unfinished</h2>
                <ul className="stack" style={{ gap: 8, listStyle: "none", padding: 0, margin: 0 }}>
                  {ov.sessions.map((x) => (
                    <li key={x.id} className="spread" style={{ gap: 8, flexWrap: "wrap" }}>
                      <span className="small">{x.label} · {TF_NAME[x.tf] ?? x.tf} candles</span>
                      <button className="btn sm outline" onClick={() => open(x.id)}>Continue</button>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            <Setup ov={ov} onStart={(x) => { setS(x); setDone(null); top.current?.scrollIntoView({ block: "start" }); }} />
            {ov.practice.n > 0 ? (
              <p className="small muted" data-testid="rp-practice">{ov.practice.n} practice trade{ov.practice.n === 1 ? "" : "s"} in your <Link className="link" to="/trade/journal">journal</Link>, {signed(ov.practice.net, "INR")} after charges{ov.practice.last ? `, the latest closed ${dayText(ov.practice.last)}` : ""}.</p>
            ) : <Empty title="No practice trades yet">Finish a replay and its trades show in your journal, where the verdict's checks can run on them.</Empty>}
            <details className="small">
              <summary>How practice orders fill</summary>
              <p className="small muted">{ov.note} A long's stop fills when a candle's low reaches it (at the open if it opened below), its target when the high does; when one candle reaches both, the stop counts first. What's open when you finish closes at the last candle shown.</p>
            </details>
          </>
        )}
    </div>
  );
}
