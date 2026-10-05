import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, price } from "../../lib/format";
import type { Instrument } from "../../lib/types";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { Empty, Info, Loading, STATUS_NAME } from "../../components/ui";
import { Earlier } from "../../components/Earlier";

/* /trade/signals: forward-test outside signals (Trade, Pro). A secret webhook URL for TradingView or Chartink alerts;
 * each signal moves one of the user's own paper sessions, filled at StratLab's live price (not the alert's) with the
 * usual charges. Every signal is logged with its arrival time and what happened to it, and after 30 closed trades the
 * verdict's luck checks run on the forward test. Paper only: no real orders. Facts, not advice. */

type Hook = { created: string; hint: string; last_used: string | null } | null;
type Row = { id: string; name: string; symbol: string; status: string; started_at: string; stopped_at: string | null };
type Miss = { at: string; status: string; reason: string; action?: string; session?: string };
type Overview = {
  allowed: boolean; plan: string; hook: Hook; sessions: Row[]; misses: Miss[]; format: Record<string, unknown>;
  limits: { per_minute: number; per_day: number; bytes: number; late_s: number; stale_s: number }; verdict_after: number;
};
type Sig = { at: string; action: string; qty?: number | null; status: string; reason?: string | null; px?: number; alert_px?: number | null;
  delay_s?: number; id?: string | null; note?: string | null; pnl?: number | null };
type Check = { id: string; title: string; status: string; detail: string };
type Snap = {
  id: string; name: string; status: string; stop_reason?: string; instrument: Instrument & { signal?: boolean }; started_at: string;
  settings: { capital: number; allow_short: boolean; leverage: number; slippage: number; brokerage: number; product: string };
  last_price: number | null; market_open: boolean; signals: Sig[];
  trade_list: { entry_t: string | null; exit_t: string; entry: number; exit: number; qty: number; pnl: number; costs: number; side: string }[];
  account: { capital: number; equity: number; cash: number; qty: number; entry: number | null; side: string; unrealised: number; realised: number; trades: number; wins: number };
  costs: { label: string; amount: number }[];
  verdict: { ready: boolean; trades: number; need: number; headline?: string; summary?: string; checks?: Check[] };
  format: Record<string, unknown>;
};

const STATUS: Record<string, string> = { filled: "Filled", late: "Filled late", rejected: "Refused", duplicate: "Repeat", ignored: "Nothing to do" };
const at = (iso: string) => new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit" });
const signed = (v: number, cur: string) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v), cur, 2)}`;
const curOf = (i: Instrument) => i.currency || "INR";

function UrlCard({ ov, reload }: { ov: Overview; reload: () => void }) {
  const { fail, notify } = useApp();
  const [fresh, setFresh] = useState<string | null>(null);
  const make = async () => {
    if (ov.hook && !confirm("Make a new URL? The old one stops working at once, so alerts using it must be updated.")) return;
    try { const r = await api<{ path: string }>("/trade/signals/hook", { method: "POST" }); setFresh(CFG.API_BASE + r.path); reload(); } catch (e) { fail(e); }
  };
  const off = async () => {
    if (!confirm("Turn the URL off? Every signal sent to it is refused from now on.")) return;
    try { await api("/trade/signals/hook", { method: "DELETE" }); setFresh(null); reload(); notify("The URL is off."); } catch (e) { fail(e); }
  };
  const copy = () => { if (fresh) navigator.clipboard?.writeText(fresh).then(() => notify("Copied."), () => {}); };
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-url">
      <h2 id="sg-url" className="h3">Your webhook URL<Info>{"Paste it into a TradingView alert's Webhook URL (or a Chartink alert's webhook). Anyone who has it can move your signal sessions' paper positions, so keep it private. It's stored only as a fingerprint, so it can be shown once only."}</Info></h2>
      {fresh ? (
        <div className="stack" style={{ gap: 6 }}>
          <div className="row" style={{ gap: 8 }}>
            <input className="input mono" readOnly value={fresh} aria-label="Webhook URL" onFocus={(e) => e.currentTarget.select()} style={{ flex: 1, minWidth: 0 }} />
            <button className="btn sm" onClick={copy}>Copy</button>
          </div>
          <p className="tiny muted" style={{ margin: 0 }} role="status">Copy it now: it isn't shown again. Make a new one any time.</p>
        </div>
      ) : ov.hook ? (
        <p className="small" style={{ margin: 0 }} data-testid="sg-hook">A URL starting <code>…/hooks/signal/{ov.hook.hint}</code> is on, made {at(ov.hook.created)}. {ov.hook.last_used ? `Last signal ${at(ov.hook.last_used)}.` : "No signal yet."}</p>
      ) : <p className="small muted" style={{ margin: 0 }}>No URL yet.</p>}
      <div className="row wrap" style={{ gap: 8 }}>
        <button className="btn sm" onClick={make}>{ov.hook || fresh ? "Make a new URL" : "Make my URL"}</button>
        {(ov.hook || fresh) && <button className="btn sm quiet danger" onClick={off}>Turn off</button>}
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>At most {ov.limits.per_minute} signals a minute and {ov.limits.per_day.toLocaleString("en-IN")} a day, each up to {ov.limits.bytes.toLocaleString("en-IN")} bytes.</p>
    </section>
  );
}

function NewSession({ onStarted }: { onStarted: (id: string) => void }) {
  const { markets, fail } = useApp();
  const live = markets.filter((m) => m.status === "live" && m.id !== "CSV");
  const [mid, setMid] = useState("IN");
  const market = live.find((m) => m.id === mid) ?? live[0];
  const [inst, setInst] = useState<Instrument | null>(null);
  const [name, setName] = useState("");
  const [capital, setCapital] = useState("");
  const [short, setShort] = useState(false);
  const [busy, setBusy] = useState(false);
  const start = async () => {
    if (!inst) return;
    setBusy(true);
    try {
      const cap = Number(capital.replace(/,/g, ""));
      const r = await api<Snap>("/trade/signals/sessions", { method: "POST", body: { instrument: inst.id, name, allow_short: short, ...(capital.trim() && cap > 0 ? { capital: cap } : {}) } });
      onStarted(r.id);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-new">
      <h2 id="sg-new" className="h3">New signal session</h2>
      {live.length > 1 && (
        <label className="field" style={{ maxWidth: 260 }}>Market
          <select value={market?.id ?? ""} onChange={(e) => { setMid(e.target.value); setInst(null); }} aria-label="Market">
            {live.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
          </select>
        </label>
      )}
      {inst ? (
        <div className="row wrap" style={{ gap: 10 }}><span className="pill">{inst.symbol}</span><button className="link" onClick={() => setInst(null)}>Pick another</button></div>
      ) : market ? <InstrumentSearch market={market} compact onPick={setInst} /> : <p className="small muted">Market data is offline right now.</p>}
      <div className="row wrap" style={{ gap: 12, alignItems: "flex-end" }}>
        <label className="field">Name<input value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="My breakout alert" /></label>
        <label className="field" style={{ width: 160 }}>Paper capital<input inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} placeholder="10,00,000" aria-label="Paper capital" /></label>
        <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={short} onChange={(e) => setShort(e.target.checked)} />Allow short positions</label>
        <button className="btn" disabled={!inst || busy} onClick={start}>{busy ? "Starting…" : "Start session"}</button>
      </div>
      <p className="tiny muted" style={{ margin: 0 }}>Each session counts toward your plan's paper sessions. For F&amp;O and Indian commodity or currency futures, a signal's qty counts lots.</p>
    </section>
  );
}

function Format({ format, ov }: { format: Record<string, unknown>; ov?: Overview }) {
  return (
    <section className="card stack" style={{ gap: 8 }} aria-labelledby="sg-format">
      <h2 id="sg-format" className="h3">The alert's message</h2>
      <pre className="sg-code"><code>{JSON.stringify(format, null, 2)}</code></pre>
      <ul className="small muted" style={{ margin: 0, paddingLeft: 18 }}>
        <li><code>action</code> is <code>buy</code>, <code>sell</code> or <code>exit</code> (closes the whole position, with no <code>qty</code>).</li>
        <li><code>symbol</code>, if sent, must match the session's: a guard against pasting the URL into the wrong alert.</li>
        <li><code>id</code> stops a repeated alert from filling twice; <code>price</code> and <code>time</code> are kept to compare with StratLab's fill and arrival time.</li>
        <li>Fills are at StratLab's live price when the signal arrives, in market hours only. {ov ? `A signal more than ${ov.limits.late_s} seconds after its own time is marked late; over ${ov.limits.stale_s / 60} minutes it's refused.` : ""}</li>
        <li>Any other field, or anything that isn't plain JSON, refuses the whole signal. Nothing in a signal is ever run.</li>
      </ul>
    </section>
  );
}

function SignalLog({ rows, cur }: { rows: Sig[]; cur: string }) {
  if (!rows.length) return <p className="small muted">No signals yet. Send a test one above, or fire your alert.</p>;
  return (
    <div className="table-wrap" style={{ margin: 0 }}>
      <table className="nums sg-log" aria-label="Signal log">
        <thead><tr><th>Arrived</th><th>Signal</th><th>What happened</th><th>Fill</th><th>Alert's price</th></tr></thead>
        <tbody>{rows.slice().reverse().map((s, i) => (
          <tr key={i} data-status={s.status}>
            <td className="small">{at(s.at)}{s.delay_s != null && <div className="tiny muted">{Math.round(s.delay_s)} s after the alert</div>}</td>
            <td><code>{s.action}</code>{s.qty != null && ` ${s.qty}`}{s.note && <div className="tiny muted">{s.note}</div>}</td>
            <td className="small">{STATUS[s.status] ?? s.status}{s.reason && <div className="tiny muted">{s.reason}</div>}</td>
            <td>{s.px != null ? price(s.px, cur) : "–"}</td>
            <td>{s.alert_px != null ? price(s.alert_px, cur) : "–"}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

function SessionView({ sid, onGone }: { sid: string; onGone: () => void }) {
  const { fail, refreshMe } = useApp();
  const [snap, setSnap] = useState<Snap | null>(null);
  const [qty, setQty] = useState("1");
  const load = useCallback(() => api<Snap>(`/trade/signals/sessions/${sid}`).then(setSnap).catch((e) => { fail(e); onGone(); }), [sid, fail, onGone]);
  useEffect(() => {
    setSnap(null); load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => window.clearInterval(t);
  }, [load]);
  if (!snap) return <Loading label="Opening the session" />;
  const cur = curOf(snap.instrument);
  const a = snap.account;
  const running = snap.status === "running";
  const test = async (action: string) => {
    try {
      await api(`/trade/signals/sessions/${sid}/test`, { method: "POST", body: action === "exit" ? { action } : { action, qty: Number(qty) || 1 } });
      load();
    } catch (e) { fail(e); load(); }
  };
  const stop = async () => {
    if (!confirm("Stop this session? Signals sent to it are refused from now on.")) return;
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); refreshMe(); load(); } catch (e) { fail(e); }
  };
  const remove = async () => {
    if (!confirm(`Delete "${snap.name}" and its signal log? This can't be undone.`)) return;
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onGone(); } catch (e) { fail(e); }
  };
  const v = snap.verdict;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 4 }}>
          <span className="eyebrow">{snap.instrument.symbol} · signal session · {running ? (snap.market_open ? "market open" : "market closed") : snap.status}</span>
          <h2 className="h2" data-testid="sg-name">{snap.name}</h2>
          <span className="tiny muted">Session id <code data-testid="sg-id">{snap.id}</code></span>
        </div>
        {running ? <button className="btn danger sm" onClick={stop}>Stop session</button>
          : <div className="row" style={{ gap: 8 }}><span className={`badge ${snap.status}`}>{STATUS_NAME?.[snap.status as keyof typeof STATUS_NAME] ?? snap.status}</span><button className="btn danger sm" onClick={remove}>Delete</button></div>}
      </div>
      {!running && snap.stop_reason && <div className="banner">Stopped: {snap.stop_reason}</div>}
      <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-acct">
        <div className="spread"><h3 id="sg-acct" className="h3">Paper account</h3><span className="small muted">Fake money</span></div>
        <div className="stat-row">
          <div className="stat"><span className="tiny muted">Equity</span><b className="num" data-testid="sg-equity">{money(a.equity, cur, 2)}</b></div>
          <div className="stat"><span className="tiny muted">Position</span><b className="num" data-testid="sg-position">{a.qty ? `${a.side === "short" ? "Short" : "Long"} ${a.qty.toLocaleString("en-IN", { maximumFractionDigits: 6 })} at ${price(a.entry ?? 0, cur)}` : "None"}</b></div>
          <div className="stat"><span className="tiny muted">Open P&amp;L</span><b className="num">{signed(a.unrealised, cur)}</b></div>
          <div className="stat"><span className="tiny muted">Closed P&amp;L after charges</span><b className="num">{signed(a.realised, cur)}</b></div>
          <div className="stat"><span className="tiny muted">Closed trades</span><b className="num">{a.trades} ({a.wins} won)</b></div>
          <div className="stat"><span className="tiny muted">Last price</span><b className="num">{snap.last_price != null ? price(snap.last_price, cur) : "–"}</b></div>
        </div>
        {running && (
          <div className="row wrap" style={{ gap: 8, alignItems: "flex-end" }}>
            <label className="field" style={{ width: 110 }}>Test qty<input inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)} aria-label="Test quantity" /></label>
            {["buy", "sell", "exit"].map((x) => <button key={x} className="btn outline sm" onClick={() => test(x)} aria-label={`Send a test ${x} signal`}>Test <code>{x}</code></button>)}
            <Info>{"A test signal goes through every check a real alert does, and fills on paper the same way. It's marked as a test in the log."}</Info>
          </div>
        )}
      </section>
      <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-verdict">
        <h3 id="sg-verdict" className="h3">The verdict's checks on this forward test</h3>
        {!v.ready ? <p className="small muted" data-testid="sg-verdict-wait" style={{ margin: 0 }}>{v.trades} of {v.need} closed trades: the luck checks run once there are {v.need}.</p> : (
          <div className="stack" style={{ gap: 8 }}>
            <p style={{ margin: 0 }}><b>{v.headline}</b> {v.summary}</p>
            <ul className="stack" style={{ gap: 6, margin: 0, paddingLeft: 18 }}>
              {v.checks?.map((c) => <li key={c.id} className="small" data-check={c.id}><b>{c.title}</b> ({STATUS_NAME?.[c.status as keyof typeof STATUS_NAME] ?? c.status}): {c.detail}</li>)}
            </ul>
          </div>
        )}
      </section>
      <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-log">
        <h3 id="sg-log" className="h3">Signal log</h3>
        <SignalLog rows={snap.signals} cur={cur} />
      </section>
      <section className="card stack" style={{ gap: 10 }} aria-labelledby="sg-trades">
        <h3 id="sg-trades" className="h3">Closed trades</h3>
        {snap.trade_list.length ? (
          <div className="table-wrap" style={{ margin: 0 }}>
            <table className="nums" aria-label="Closed trades">
              <thead><tr><th>Closed</th><th>Side</th><th>Qty</th><th>Entry → exit</th><th>Charges</th><th>Net</th></tr></thead>
              <tbody>{snap.trade_list.slice().reverse().map((t, i) => (
                <tr key={i}><td className="small">{at(t.exit_t)}</td><td>{t.side === "short" ? "Short" : "Long"}</td><td>{t.qty.toLocaleString("en-IN", { maximumFractionDigits: 6 })}</td>
                  <td className="small">{price(t.entry, cur)} → {price(t.exit, cur)}</td><td>{money(t.costs, cur, 2)}</td><td>{signed(t.pnl, cur)}</td></tr>
              ))}</tbody>
            </table>
          </div>
        ) : <p className="small muted" style={{ margin: 0 }}>None yet.</p>}
      </section>
      <Format format={snap.format} />
    </div>
  );
}

export function SignalsPage() {
  const { sid } = useParams();
  const nav = useNavigate();
  const { fail, refreshMe } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);
  const load = useCallback(() => api<Overview>("/trade/signals").then(setOv).catch(fail), [fail]);
  useEffect(() => { load(); }, [load, sid]);
  const gone = useCallback(() => { nav("/trade/signals"); }, [nav]);
  const current = (ov?.sessions ?? []).filter((r) => r.status === "running" || r.status === "paused");
  const stopped = (ov?.sessions ?? []).filter((r) => !current.includes(r));
  const card = (r: Row) => (
    <Link key={r.id} to={`/trade/signals/${r.id}`} className="card sg-card" aria-current={r.id === sid ? "page" : undefined}>
      <b>{r.name}</b><span className="small muted">{r.symbol}</span><span className={`badge ${r.status}`} style={{ alignSelf: "flex-start" }}>{r.status}</span>
    </Link>
  );
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Trade · paper trading</span>
        <h1 className="page-title">Signal forward test</h1>
        <p className="page-sub" style={{ maxWidth: "70ch" }}>Point your TradingView or Chartink alerts at a secret URL and forward-test them on paper: each signal fills at StratLab's own live price with charges, every signal is logged, and the verdict's checks run once there are enough trades. Paper only: no real orders. Facts, not advice.</p>
      </div>
      {!ov ? <Loading label="Opening signal sessions" /> : !ov.allowed ? (
        <section className="card dashed stack" style={{ gap: 8 }}>
          <p className="small" style={{ margin: 0 }}><b>Forward-testing outside signals</b> is on the {ov.plan} plan.</p>
          <Link to="/plans" className="btn sm" style={{ alignSelf: "flex-start" }}>See plans</Link>
        </section>
      ) : (
        <>
          {(current.length > 0 || stopped.length > 0) && (
            <div className="stack" style={{ gap: 10 }}>
              <div className="sg-cards">{current.map(card)}</div>
              {!current.length && <p className="small muted">None running.</p>}
              <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
                <div className="sg-cards">{stopped.map(card)}</div>
              </Earlier>
            </div>
          )}
          {sid ? <SessionView key={sid} sid={sid} onGone={() => { load(); gone(); }} /> : (
            <>
              <div className="grid2" style={{ alignItems: "start" }}>
                <UrlCard ov={ov} reload={load} />
                <NewSession onStarted={(id) => { refreshMe(); load(); nav(`/trade/signals/${id}`); }} />
              </div>
              {!ov.sessions.length && <Empty title="No signal sessions yet">Start one above, then put its session id and your URL into an alert.</Empty>}
              <Format format={ov.format} ov={ov} />
              <Earlier label="Signals that reached no session" count={ov.misses.length}>
                <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                  {ov.misses.map((m, i) => <li key={i}>{at(m.at)}: {m.reason}</li>)}
                </ul>
              </Earlier>
            </>
          )}
        </>
      )}
    </div>
  );
}
