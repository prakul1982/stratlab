import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, price } from "../../lib/format";
import type { Instrument } from "../../lib/types";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { STATUS_NAME } from "../../components/ui";
import { Earlier } from "../../components/Earlier";
import { upDown } from "../../lib/tradeUi";
import { Badge, Card, CardHead, CheckField, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, Select, Skeleton, Stat, StatRow, type Column } from "../../components/kit";
import "./trade.css";
import "./paper.css";

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

const tone = (n: number) => (n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));
const statusTone = (s: string) => (s === "running" ? "ok" : s === "paused" ? "warn" : "plain") as "ok" | "warn" | "plain";

function UrlCard({ ov, reload }: { ov: Overview; reload: () => void }) {
  const { fail, notify } = useApp();
  const [fresh, setFresh] = useState<string | null>(null);
  const [ask, setAsk] = useState<"new" | "off" | null>(null);
  const make = async () => {
    setAsk(null);
    try { const r = await api<{ path: string }>("/trade/signals/hook", { method: "POST" }); setFresh(CFG.API_BASE + r.path); reload(); } catch (e) { fail(e); }
  };
  const off = async () => {
    setAsk(null);
    try { await api("/trade/signals/hook", { method: "DELETE" }); setFresh(null); reload(); notify("The URL is off."); } catch (e) { fail(e); }
  };
  const copy = () => { if (fresh) navigator.clipboard?.writeText(fresh).then(() => notify("Copied."), () => {}); };
  return (
    <Card label="Your webhook URL">
      <CardHead level={3} title="Your webhook URL" info="Paste it into a TradingView alert's Webhook URL (or a Chartink alert's webhook). Anyone who has it can move your signal sessions' paper positions, so keep it private. It's stored only as a fingerprint, so it can be shown once only." infoLabel="About the webhook URL" />
      {fresh ? (
        <div className="k-stack k-tight">
          <div className="k-row">
            <input className="k-input k-grow" readOnly value={fresh} aria-label="Webhook URL" onFocus={(e) => e.currentTarget.select()} />
            <button type="button" className="btn sm" onClick={copy}>Copy</button>
          </div>
          <p className="k-note" role="status">Copy it now: it isn't shown again. Make a new one any time.</p>
        </div>
      ) : ov.hook ? (
        <p className="k-small" data-testid="sg-hook">A URL starting <code>…/hooks/signal/{ov.hook.hint}</code> is on, made {at(ov.hook.created)}. {ov.hook.last_used ? `Last signal ${at(ov.hook.last_used)}.` : "No signal yet."}</p>
      ) : <p className="k-small k-muted">No URL yet.</p>}
      <div className="k-row">
        <button type="button" className="btn sm" onClick={() => (ov.hook ? setAsk("new") : void make())}>{ov.hook || fresh ? "Make a new URL" : "Make my URL"}</button>
        {(ov.hook || fresh) && <button type="button" className="btn sm quiet danger" onClick={() => setAsk("off")}>Turn off</button>}
      </div>
      <p className="k-note">At most {ov.limits.per_minute} signals a minute and {ov.limits.per_day.toLocaleString("en-IN")} a day, each up to {ov.limits.bytes.toLocaleString("en-IN")} bytes.</p>
      {ask === "new" && <ConfirmDialog title="Make a new URL?" confirmLabel="Make a new URL" onConfirm={make} onClose={() => setAsk(null)}>The old one stops working at once, so alerts using it must be updated.</ConfirmDialog>}
      {ask === "off" && <ConfirmDialog title="Turn the URL off?" confirmLabel="Turn it off" onConfirm={off} onClose={() => setAsk(null)}>Every signal sent to it is refused from now on.</ConfirmDialog>}
    </Card>
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
    <Card label="New signal session">
      <CardHead level={3} title="New signal session" />
      <div className="k-stack">
        {live.length > 1 && (
          <FormGrid label="Pick the instrument">
            <Field label="Market">{(id) => <Select id={id} value={market?.id ?? ""} onChange={(v) => { setMid(v); setInst(null); }} options={live.map((m) => ({ value: m.id, label: m.name }))} />}</Field>
          </FormGrid>
        )}
        {inst ? (
          <div className="k-row"><Badge tone="ok">{inst.symbol}</Badge><button type="button" className="btn quiet sm" onClick={() => setInst(null)}>Pick another</button></div>
        ) : market ? <InstrumentSearch market={market} compact onPick={setInst} /> : <p className="k-small k-muted">Market data is offline right now.</p>}
        <FormGrid label="Session settings" onSubmit={(e) => { e.preventDefault(); void start(); }}>
          <Field label="Name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="My breakout alert" />
          <Field label="Paper capital" inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} placeholder="10,00,000" unit="₹" />
          <div className="k-field wide"><CheckField label="Allow short positions" checked={short} onChange={setShort} /></div>
          <FormActions><button type="submit" className="btn" disabled={!inst || busy}>{busy ? "Starting…" : "Start session"}</button></FormActions>
        </FormGrid>
        <p className="k-note">Each session counts toward your plan's paper sessions. For F&amp;O and Indian commodity or currency futures, a signal's qty counts lots.</p>
      </div>
    </Card>
  );
}

function Format({ format, ov }: { format: Record<string, unknown>; ov?: Overview }) {
  return (
    <Card label="The alert's message">
      <CardHead level={3} title="The alert's message" />
      <pre className="sg-code"><code>{JSON.stringify(format, null, 2)}</code></pre>
      <ul className="k-list muted">
        <li><code>action</code> is <code>buy</code>, <code>sell</code> or <code>exit</code> (closes the whole position, with no <code>qty</code>).</li>
        <li><code>symbol</code>, if sent, must match the session's: a guard against pasting the URL into the wrong alert.</li>
        <li><code>id</code> stops a repeated alert from filling twice; <code>price</code> and <code>time</code> are kept to compare with StratLab's fill and arrival time.</li>
        <li>Fills are at StratLab's live price when the signal arrives, in market hours only. {ov ? `A signal more than ${ov.limits.late_s} seconds after its own time is marked late; over ${ov.limits.stale_s / 60} minutes it's refused.` : ""}</li>
        <li>Any other field, or anything that isn't plain JSON, refuses the whole signal. Nothing in a signal is ever run.</li>
      </ul>
    </Card>
  );
}

function SignalLog({ rows, cur }: { rows: Sig[]; cur: string }) {
  const cols: Column<Sig>[] = [
    { key: "at", header: "Arrived", cell: (s) => <>{at(s.at)}{s.delay_s != null && <span className="k-sub-line">{Math.round(s.delay_s)} s after the alert</span>}</> },
    { key: "sig", header: "Signal", wrap: true, cell: (s) => <><code>{s.action}</code>{s.qty != null && ` ${s.qty}`}{s.note && <span className="k-sub-line">{s.note}</span>}</> },
    { key: "what", header: "What happened", wrap: true, cell: (s) => <>{STATUS[s.status] ?? s.status}{s.reason && <span className="k-sub-line">{s.reason}</span>}</> },
    { key: "fill", header: "Fill", numeric: true, cell: (s) => (s.px != null ? price(s.px, cur) : "–") },
    { key: "alert", header: "Alert's price", numeric: true, cell: (s) => (s.alert_px != null ? price(s.alert_px, cur) : "–") },
  ];
  if (!rows.length) return <p className="k-small k-muted">No signals yet. Send a test one above, or fire your alert.</p>;
  return <DataTable label="Signal log" columns={cols} rows={rows.slice().reverse()} rowKey={(s) => `${s.at}${s.action}${s.id ?? ""}`} rowAttrs={(s) => ({ "data-status": s.status })} />;
}

function SessionView({ sid, onGone }: { sid: string; onGone: () => void }) {
  const { fail, refreshMe } = useApp();
  const [snap, setSnap] = useState<Snap | null>(null);
  const [qty, setQty] = useState("1");
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);
  const load = useCallback(() => api<Snap>(`/trade/signals/sessions/${sid}`).then(setSnap).catch((e) => { fail(e); onGone(); }), [sid, fail, onGone]);
  useEffect(() => {
    setSnap(null); load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => window.clearInterval(t);
  }, [load]);
  if (!snap) return <Card><Skeleton label="Opening the session" /></Card>;
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
    setAsk(null);
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); refreshMe(); load(); } catch (e) { fail(e); }
  };
  const remove = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); onGone(); } catch (e) { fail(e); }
  };
  const v = snap.verdict;
  type Tr = Snap["trade_list"][number];
  const tradeCols: Column<Tr>[] = [
    { key: "closed", header: "Closed", cell: (t) => at(t.exit_t) },
    { key: "side", header: "Side", cell: (t) => (t.side === "short" ? "Short" : "Long") },
    { key: "qty", header: "Qty", numeric: true, cell: (t) => t.qty.toLocaleString("en-IN", { maximumFractionDigits: 6 }) },
    { key: "px", header: "Entry → exit", numeric: true, cell: (t) => `${price(t.entry, cur)} → ${price(t.exit, cur)}` },
    { key: "ch", header: "Charges", numeric: true, cell: (t) => money(t.costs, cur, 2) },
    { key: "net", header: "Net", numeric: true, cell: (t) => <span className={upDown(t.pnl)}>{signed(t.pnl, cur)}</span> },
  ];
  return (
    <div className="k-page">
      <div className="k-spread k-session-head">
        <div className="k-stack k-tight">
          <span className="k-eyebrow">{snap.instrument.symbol} · signal session · {running ? (snap.market_open ? "market open" : "market closed") : snap.status}</span>
          <h2 className="k-session-name" data-testid="sg-name">{snap.name}</h2>
          <span className="k-note">Session id <code data-testid="sg-id">{snap.id}</code></span>
        </div>
        {running ? <button type="button" className="btn danger sm" onClick={() => setAsk("stop")}>Stop session</button>
          : <div className="k-row"><Badge tone={statusTone(snap.status)}>{STATUS_NAME?.[snap.status as keyof typeof STATUS_NAME] ?? snap.status}</Badge><button type="button" className="btn danger sm" onClick={() => setAsk("delete")}>Delete</button></div>}
      </div>
      {!running && snap.stop_reason && <Notice>Stopped: {snap.stop_reason}</Notice>}
      <Card label="Paper account">
        <CardHead level={3} title="Paper account" actions={<span className="k-note">Fake money</span>} />
        <StatRow label="Paper account">
          <Stat item label="Equity" value={<span data-testid="sg-equity">{money(a.equity, cur, 2)}</span>} />
          <Stat item label="Position" value={<span data-testid="sg-position">{a.qty ? `${a.side === "short" ? "Short" : "Long"} ${a.qty.toLocaleString("en-IN", { maximumFractionDigits: 6 })} at ${price(a.entry ?? 0, cur)}` : "None"}</span>} />
          <Stat item label="Open P&L" value={signed(a.unrealised, cur)} tone={tone(a.unrealised)} />
          <Stat item label="Closed P&L after charges" value={signed(a.realised, cur)} tone={tone(a.realised)} />
          <Stat item label="Closed trades" value={`${a.trades} (${a.wins} won)`} />
          <Stat item label="Last price" value={snap.last_price != null ? price(snap.last_price, cur) : "–"} />
        </StatRow>
        {running && (
          <FormGrid label="Send a test signal">
            <Field label="Test qty" aria-label="Test quantity" inputMode="decimal" value={qty} onChange={(e) => setQty(e.target.value)}
              info="A test signal goes through every check a real alert does, and fills on paper the same way. It's marked as a test in the log." />
            <FormActions>
              {["buy", "sell", "exit"].map((x) => <button type="button" key={x} className="btn outline sm" onClick={() => test(x)} aria-label={`Send a test ${x} signal`}>Test <code>{x}</code></button>)}
            </FormActions>
          </FormGrid>
        )}
      </Card>
      <Card label="The verdict's checks on this forward test">
        <CardHead level={3} title="The verdict's checks on this forward test" />
        {!v.ready ? <p className="k-small k-muted" data-testid="sg-verdict-wait">{v.trades} of {v.need} closed trades: the luck checks run once there are {v.need}.</p> : (
          <div className="k-stack">
            <p><b>{v.headline}</b> {v.summary}</p>
            <ul className="k-list">
              {v.checks?.map((c) => <li key={c.id} data-check={c.id}><b>{c.title}</b> ({STATUS_NAME?.[c.status as keyof typeof STATUS_NAME] ?? c.status}): {c.detail}</li>)}
            </ul>
          </div>
        )}
      </Card>
      <Card label="Signal log">
        <CardHead level={3} title="Signal log" />
        <SignalLog rows={snap.signals} cur={cur} />
      </Card>
      <Card label="Closed trades">
        <CardHead level={3} title="Closed trades" />
        {snap.trade_list.length ? <DataTable label="Closed trades" columns={tradeCols} rows={snap.trade_list.slice().reverse()} rowKey={(t) => `${t.exit_t}${t.qty}${t.entry}`} />
          : <p className="k-small k-muted">None yet.</p>}
      </Card>
      <Format format={snap.format} />
      {ask === "stop" && <ConfirmDialog title="Stop this session?" confirmLabel="Stop session" onConfirm={stop} onClose={() => setAsk(null)}>Signals sent to it are refused from now on.</ConfirmDialog>}
      {ask === "delete" && <ConfirmDialog title={`Delete "${snap.name}"?`} confirmLabel="Delete session" onConfirm={remove} onClose={() => setAsk(null)}>Its signal log goes with it. This can't be undone.</ConfirmDialog>}
    </div>
  );
}

export function SignalsPage() {
  const { sid } = useParams();
  const nav = useNavigate();
  const { fail, refreshMe } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);
  const [failed, setFailed] = useState(false);
  const load = useCallback(() => api<Overview>("/trade/signals").then((o) => { setOv(o); setFailed(false); }).catch((e) => { fail(e); setFailed(true); }), [fail]);
  useEffect(() => { load(); }, [load, sid]);
  const gone = useCallback(() => { nav("/trade/signals"); }, [nav]);
  const current = (ov?.sessions ?? []).filter((r) => r.status === "running" || r.status === "paused");
  const stopped = (ov?.sessions ?? []).filter((r) => !current.includes(r));
  const card = (r: Row) => (
    <Link key={r.id} to={`/trade/signals/${r.id}`} className="k-sess-link" aria-current={r.id === sid ? "page" : undefined}>
      <b>{r.name}</b><span className="k-note">{r.symbol}</span><Badge tone={statusTone(r.status)}>{r.status}</Badge>
    </Link>
  );
  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Build and test" title="Forward test"
        lede="A forward test tries a strategy on days that have not happened yet: your alerts are filled on paper at live prices, and every one is logged."
        infoLabel="How this works"
        info="Point your TradingView or Chartink alerts at a secret URL. Each signal fills at StratLab's own live price with charges, every signal is logged, and the verdict's checks run once there are enough trades. Paper only: no real orders. Facts, not advice." />
      {failed && !ov ? <ErrorState title="Your signal sessions couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>Nothing was changed.</ErrorState>
        : !ov ? <Card><Skeleton label="Opening signal sessions" /></Card> : !ov.allowed ? (
        <EmptyState title="Forward-testing outside signals" action={{ label: "See plans", to: "/plans" }}>It is on the {ov.plan} plan.</EmptyState>
      ) : (
        <>
          {(current.length > 0 || stopped.length > 0) && (
            <Card label="Your signal sessions">
              <CardHead level={3} title="Your signal sessions" />
              <div className="k-sessions">{current.map(card)}</div>
              {!current.length && <p className="k-small k-muted">None running.</p>}
              <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
                <div className="k-sessions">{stopped.map(card)}</div>
              </Earlier>
            </Card>
          )}
          {sid ? <SessionView key={sid} sid={sid} onGone={() => { load(); gone(); }} /> : (
            <>
              <div className="k-two">
                <UrlCard ov={ov} reload={load} />
                <NewSession onStarted={(id) => { refreshMe(); load(); nav(`/trade/signals/${id}`); }} />
              </div>
              {!ov.sessions.length && <EmptyState title="No signal sessions yet">Start one above, then put its session id and your URL into an alert.</EmptyState>}
              <Format format={ov.format} ov={ov} />
              <Earlier label="Signals that reached no session" count={ov.misses.length}>
                <ul className="k-list">
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
