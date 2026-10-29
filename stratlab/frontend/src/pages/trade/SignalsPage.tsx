import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money, price, fmtDateTime, tzOf } from "../../lib/format";
import type { Instrument } from "../../lib/types";
import { InstrumentSearch } from "../../components/InstrumentSearch";
import { STATUS_NAME } from "../../components/ui";
import { Earlier } from "../../components/Earlier";
import { capitalField, stoppable, testQty, testSignalId, upDown } from "../../lib/tradeUi";
import { Badge, Card, CardHead, CheckField, ConfirmDialog, DataTable, EmptyState, ErrorState, Field, FormActions, FormGrid, Notice, PageHeader, Select, Skeleton, Stat, StatRow, type Column } from "../../components/kit";
import { LockedPreview } from "../../components/LockedPreview";
import { INDIA_FEED, offlineLine } from "../../lib/dataBack";
import "./trade.css";
import "./paper.css";

/* /trade/signals: forward-test outside signals (Trade, Pro). A secret webhook URL for TradingView or Chartink alerts;
 * each signal moves one of the user's own paper sessions, filled at StratLab's live price (not the alert's) with the
 * usual charges. Every signal is logged with its arrival time and what happened to it, and after 30 closed trades the
 * verdict's luck checks run on the forward test. Paper only: no real orders. Facts, not advice. */

type Hook = { created: string; hint: string; last_used: string | null } | null;
type Row = { id: string; name: string; symbol: string; status: string; started_at: string; stopped_at: string | null; market?: string | null; tz?: string | null };
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
/** When a signal or hook event happened: the reader's own time, labelled with its zone. */
const at = (iso: string) => fmtDateTime(iso, { year: false, seconds: true, zone: true });
const signed = (v: number, cur: string) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${money(Math.abs(v), cur, 2)}`;
const curOf = (i: Instrument) => i.currency || "INR";

const tone = (n: number) => (n === 0 ? undefined : n > 0 ? ("up" as const) : ("down" as const));
const statusTone = (s: string) => (s === "running" ? "ok" : s === "paused" ? "warn" : "plain") as "ok" | "warn" | "plain";

function UrlCard({ ov, reload }: { ov: Overview; reload: () => void }) {
  const { fail, notify } = useApp();
  const [fresh, setFresh] = useState<string | null>(null);
  const [ask, setAsk] = useState<"first" | "new" | "off" | null>(null);
  const make = async () => {
    setAsk(null);
    try {
      const r = await api<{ path: string }>("/trade/signals/hook", { method: "POST" });
      setFresh(CFG.API_BASE + r.path); reload();
      if (!ov.hook) notify("Your URL is on.", { label: "Turn it off", run: () => void off() });
    } catch (e) { fail(e); }
  };
  const off = async () => {
    setAsk(null);
    try { await api("/trade/signals/hook", { method: "DELETE" }); setFresh(null); reload(); notify("The URL is off."); } catch (e) { fail(e); }
  };
  const copy = () => { if (fresh) navigator.clipboard?.writeText(fresh).then(() => notify("Copied."), () => {}); };
  return (
    <Card label="Your webhook URL">
      <CardHead level={2} title="Your webhook URL" info="Paste it into a TradingView alert's Webhook URL (or a Chartink alert's webhook). Anyone who has it can move your signal sessions' paper positions, so keep it private. It's stored only as a fingerprint, so it can be shown once only." infoLabel="About the webhook URL" />
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
        <button type="button" className="btn sm" onClick={() => setAsk(ov.hook || fresh ? "new" : "first")}>{ov.hook || fresh ? "Make a new URL" : "Make my URL"}</button>
        {(ov.hook || fresh) && <button type="button" className="btn sm quiet danger" onClick={() => setAsk("off")}>Turn off</button>}
      </div>
      <p className="k-note">At most {ov.limits.per_minute} signals a minute and {ov.limits.per_day.toLocaleString("en-IN")} a day, each up to {ov.limits.bytes.toLocaleString("en-IN")} bytes.</p>
      {ask === "first" && <ConfirmDialog title="Make your URL?" confirmLabel="Make my URL" onConfirm={make} onClose={() => setAsk(null)} danger={false}>Anyone who has it can move your signal sessions' paper positions. It is shown once only, and can be turned off at any time.</ConfirmDialog>}
      {ask === "new" && <ConfirmDialog title="Make a new URL?" confirmLabel="Make a new URL" onConfirm={make} onClose={() => setAsk(null)}>The old one stops working at once, so alerts using it must be updated.</ConfirmDialog>}
      {ask === "off" && <ConfirmDialog title="Turn the URL off?" confirmLabel="Turn it off" onConfirm={off} onClose={() => setAsk(null)}>Every signal sent to it is refused from now on.</ConfirmDialog>}
    </Card>
  );
}

function NewSession({ onStarted }: { onStarted: (id: string) => void }) {
  const { markets, fail, me } = useApp();
  // every market that has data, offline ones too (named so): India went missing from the list on a weekend while the
  // notes below spoke of F&O lots (DA-039); an offline one says when its data is back instead of searching
  const live = markets.filter((m) => (m.status === "live" || m.status === "offline") && m.id !== "CSV");
  const [mid, setMid] = useState("IN");
  const market = live.find((m) => m.id === mid) ?? live[0];
  const offline = market?.status === "offline";
  const [inst, setInst] = useState<Instrument | null>(null);
  const [name, setName] = useState("");
  const [capital, setCapital] = useState("");
  const [short, setShort] = useState(false);
  const [busy, setBusy] = useState(false);
  // the instrument's own currency, the market's until one is picked: never rupees on a US or crypto session
  const cap = capitalField(inst?.currency || market?.currency);
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
      <CardHead level={2} title="New signal session" />
      <div className="k-stack">
        {live.length > 1 && (
          <FormGrid label="Pick the instrument">
            <Field label="Market">{(id) => <Select id={id} value={market?.id ?? ""} onChange={(v) => { setMid(v); setInst(null); }} options={live.map((m) => ({ value: m.id, label: `${m.name}${m.status === "offline" ? " (offline)" : ""}` }))} />}</Field>
          </FormGrid>
        )}
        {inst ? (
          <div className="k-row"><Badge tone="ok">{inst.symbol}</Badge><button type="button" className="btn quiet sm" onClick={() => setInst(null)}>Pick another</button></div>
        ) : market && offline ? (
          <Notice tone="warn">{INDIA_FEED.has(market.id) ? offlineLine(market.name, me?.data_note) : `Market data for ${market.name} is offline right now. Try again later.`}</Notice>
        ) : market ? <InstrumentSearch market={market} compact onPick={setInst} /> : <p className="k-small k-muted">Market data is offline right now.</p>}
        <FormGrid label="Session settings" onSubmit={(e) => { e.preventDefault(); void start(); }}>
          <Field label="Name" value={name} maxLength={60} onChange={(e) => setName(e.target.value)} placeholder="My breakout alert" />
          <Field label="Paper capital" inputMode="decimal" value={capital} onChange={(e) => setCapital(e.target.value)} placeholder={cap.placeholder} unit={cap.unit} />
          {/* the option is a box of the form and the button has a row of its own with its caption under it: all three in one row made the primary action look like one more control (LIVE1A-025) */}
          <div className="k-field wide"><CheckField label="Allow short positions" checked={short} onChange={setShort} /></div>
          <FormActions>
            <span className="k-stack k-tight">
              <button type="submit" className="btn" disabled={!inst || busy}>{busy ? "Starting…" : "Start session"}</button>
              {!inst && !busy && <span className="k-note">Pick an instrument first.</span>}
            </span>
          </FormActions>
        </FormGrid>
        <p className="k-note">Each session counts toward your plan's paper sessions. For F&amp;O and Indian commodity or currency futures, a signal's qty counts lots.</p>
      </div>
    </Card>
  );
}

/** The steps for a TradingView alert, in order (DA-039: the page never said what to do with the URL, outside its lock note). */
function HowTo() {
  return (
    <Card label="Connect a TradingView alert">
      <CardHead level={3} title="Connect a TradingView alert" />
      <ol className="k-list">
        <li>Make your URL above and copy it. Start a session for the instrument the alert is on.</li>
        <li>In TradingView, create an alert on that chart. Under Notifications, tick Webhook URL and paste your URL.</li>
        <li>In the alert's Message box, put the message below with your session's id, and <code>buy</code>, <code>sell</code> or <code>exit</code> as the action.</li>
        <li>When the alert fires, the signal shows in the session's log with its fill. Chartink alerts work the same way, with the URL as their webhook.</li>
      </ol>
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
  const { fail, notify, refreshMe } = useApp();
  const [snap, setSnap] = useState<Snap | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [qty, setQty] = useState("1");
  const [qtyNote, setQtyNote] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const inFlight = useRef(false);    // a second click before the buttons are drawn disabled is dropped too
  const [ask, setAsk] = useState<"stop" | "delete" | null>(null);
  // the parent's "gone" handler changes on every render of the page (a toast, a reload): held in a ref, so the polling
  // below doesn't start over, and the snapshot isn't blanked, each time it does
  const gone = useRef(onGone);
  gone.current = onGone;
  const told = useRef(false);        // a failing poll is said once, not every 5 seconds
  const load = useCallback(() => api<Snap>(`/trade/signals/sessions/${sid}`).then((x) => { setSnap(x); setProblem(null); told.current = false; }).catch((e) => {
    // only a session that isn't there any more leaves the page; any other error keeps what is shown and tries again
    if (e instanceof ApiError && e.status === 404) { fail(e); gone.current(); return; }
    setProblem((e as Error)?.message || "The session couldn't be read.");
    if (!told.current) { told.current = true; fail(e); }
  }), [sid, fail]);
  useEffect(() => {
    load();
    const t = window.setInterval(() => { if (!document.hidden) load(); }, 5000);
    return () => window.clearInterval(t);
  }, [load]);
  if (!snap && problem) return <Card><ErrorState title="The session couldn't be opened" action={{ label: "Try again", onClick: () => { void load(); } }}>{problem}</ErrorState></Card>;
  if (!snap) return <Card><Skeleton label="Opening the session" /></Card>;
  const cur = curOf(snap.instrument);
  const a = snap.account;
  const running = snap.status === "running";
  const test = async (action: string) => {
    if (inFlight.current) return;
    let body: Record<string, unknown> = { action, id: testSignalId() };
    if (action !== "exit") {
      const q = testQty(qty);
      if ("error" in q) { setQtyNote(q.error); return; }
      body = { ...body, qty: q.qty };
    }
    setQtyNote(null);
    inFlight.current = true;
    setSending(true);
    try {
      await api(`/trade/signals/sessions/${sid}/test`, { method: "POST", body });
      await load();
    } catch (e) { fail(e); await load(); } finally { inFlight.current = false; setSending(false); }
  };
  const stop = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}/stop`, { method: "POST" }); refreshMe(); await load(); notify("Stopped. It can be deleted now."); } catch (e) { fail(e); }
  };
  const remove = async () => {
    setAsk(null);
    try { await api(`/live/sessions/${sid}`, { method: "DELETE" }); gone.current(); } catch (e) { fail(e); }
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
        {/* a paused session (saved as running, not attached anywhere right now) is stopped like a running one, then deleted */}
        {stoppable(snap.status)
          ? <div className="k-row">{!running && <Badge tone={statusTone(snap.status)}>{STATUS_NAME?.[snap.status as keyof typeof STATUS_NAME] ?? snap.status}</Badge>}<button type="button" className="btn danger sm" onClick={() => setAsk("stop")}>Stop session</button></div>
          : <div className="k-row"><Badge tone={statusTone(snap.status)}>{STATUS_NAME?.[snap.status as keyof typeof STATUS_NAME] ?? snap.status}</Badge><button type="button" className="btn danger sm" onClick={() => setAsk("delete")}>Delete</button></div>}
      </div>
      {!running && snap.stop_reason && <Notice>Stopped: {snap.stop_reason}</Notice>}
      {snap.status === "paused" && <Notice tone="warn" role="status">Paused: the session is saved as running, but nothing is running it right now, so signals sent to it are refused. Stop it to delete it.</Notice>}
      {problem && <Notice tone="warn" role="status">{problem} Showing the last figures read; trying again.</Notice>}
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
            <Field label="Test qty" aria-label="Test quantity" inputMode="decimal" value={qty} onChange={(e) => { setQty(e.target.value); setQtyNote(null); }}
              error={qtyNote ?? undefined}
              info="A test signal goes through every check a real alert does, and fills on paper the same way. It's marked as a test in the log." />
            <FormActions>
              {["buy", "sell", "exit"].map((x) => <button type="button" key={x} className="btn outline sm" disabled={sending} onClick={() => void test(x)} aria-label={`Send a test ${x} signal`}>Test <code>{x}</code></button>)}
              {sending && <span className="k-note" role="status">Sending…</span>}
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
  const onGone = useCallback(() => { void load(); nav("/trade/signals"); }, [load, nav]);
  const current = (ov?.sessions ?? []).filter((r) => r.status === "running" || r.status === "paused");
  const stopped = (ov?.sessions ?? []).filter((r) => !current.includes(r));
  const card = (r: Row) => (
    <Link key={r.id} to={`/trade/signals/${r.id}`} className="k-sess-link" aria-current={r.id === sid ? "page" : undefined}>
      <b>{r.name}</b><span className="k-note">{r.symbol}{r.started_at ? ` · started ${fmtDateTime(r.started_at, { tz: tzOf({ market: r.market ?? undefined, tz: r.tz ?? undefined }), year: false, zone: true })}` : ""}</span><Badge tone={statusTone(r.status)}>{r.status}</Badge>
    </Link>
  );
  return (
    <div className="k-page">
      <PageHeader eyebrow="Trade · Practise" title="Forward test"
        // what it is for, in the line itself and not only in the lock note (DA-039)
        lede="A forward test tries a strategy on days that have not happened yet: connect your TradingView or Chartink alerts, and each one is filled on paper at StratLab's live price, with charges, and logged."
        infoLabel="How this works"
        info="Point your TradingView or Chartink alerts at a secret URL. Each signal fills at StratLab's own live price with charges, every signal is logged, and the verdict's checks run once there are enough trades. Paper only: no real orders. Facts, not advice." />
      {failed && !ov ? <ErrorState title="Your signal sessions couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>Nothing was changed.</ErrorState>
        : !ov ? <Card><Skeleton label="Opening signal sessions" /></Card> : !ov.allowed ? (
        // the lock note above already offers the plans: one "See plans", not two (DA-040)
        <LockedPreview title="Forward test" actions={false} points={[
          "A secret webhook address for your TradingView or Chartink alerts.",
          "Each alert fills on paper at StratLab's own live price, with charges, never as a real order.",
          "Every signal is logged with what was filled and why one was skipped.",
          "Once there are enough trades, the verdict's honesty checks run on the results.",
        ]} />
      ) : (
        <>
          {(current.length > 0 || stopped.length > 0) && (
            <Card label="Your signal sessions">
              <CardHead level={2} title="Your signal sessions" />
              <div className="k-sessions">{current.map(card)}</div>
              {!current.length && <p className="k-small k-muted">None running.</p>}
              <Earlier label="Stopped sessions" count={stopped.length} open={!!sid && stopped.some((r) => r.id === sid)}>
                <div className="k-sessions">{stopped.map(card)}</div>
              </Earlier>
            </Card>
          )}
          {sid ? <SessionView key={sid} sid={sid} onGone={onGone} /> : (
            <>
              {/* the short webhook card and the how-to share the left column beside the tall new-session form, so neither
                  column leaves a gap under it (MO-4b) */}
              <div className="k-two">
                <div className="k-page">
                  <UrlCard ov={ov} reload={load} />
                  <HowTo />
                </div>
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
