import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { CHANNEL_NAME, alertsApi, type AlertsPage as Page, type StockAlert } from "../lib/alerts";
import { AlertForm } from "../components/AlertForm";
import { Bell, Pencil, Trash } from "../components/Icons";
import { Empty, Info, Loading, Modal } from "../components/ui";
import { Earlier, LOCAL_TZ, splitToday } from "../components/Earlier";

/** The alerts the user set on stocks: the ones on, the ones that fired, and a form for a new one. */
export function AlertsPage() {
  const { fail, notify } = useApp();
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<StockAlert | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => alertsApi.list().then((p) => { setPage(p); setError(null); }).catch((e) => setError((e as Error).message)), []);
  useEffect(() => { load(); }, [load]);

  const remove = async (a: StockAlert) => {
    setBusy(a.id);
    try { setPage(await alertsApi.remove(a.id)); notify(`Alert on ${a.symbol} deleted.`); } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const clear = async () => {
    setBusy("clear");
    try { setPage(await alertsApi.clearTriggered()); } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const full = !!page && page.count >= page.limit;
  // fired today in view; the ones that fired before today folded under one line (one with no time counts as earlier)
  const fired = splitToday(page?.triggered ?? [], (a) => a.triggered_at || "", LOCAL_TZ);

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Watch · Alerts</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Your stock alerts</h1>
        <p className="page-sub">A message when a stock crosses a price, an average or an RSI level, moves a lot in a day, or makes a 52-week high or low. Checked every minute while its market is open.</p>
      </div>
      {error && <div className="card"><p className="muted">{error}</p></div>}
      {!page && !error && <Loading label="Opening your alerts" />}
      {page && <>
        <section className="card stack" style={{ gap: 12 }}>
          <div className="spread" style={{ gap: 12, flexWrap: "wrap" }}>
            <span className="small"><b>{page.count}</b> of {page.limit} alerts on<Info>{"Your plan's limit counts the alerts that are on. Ones that already fired don't count, and repeating ones count once."}</Info></span>
            {!adding && <button className="btn sm" disabled={full} onClick={() => setAdding(true)}><Bell size={17} />New alert</button>}
          </div>
          {full && <p className="small muted">That's all your plan has. Delete one to add another, or <Link className="link" to="/plans">see plans</Link> for more.</p>}
          <p className="small muted">{page.channels.length
            ? `Sent by ${page.channels.map((c) => CHANNEL_NAME[c] ?? c).join(", ")}. At most a few messages an hour: alerts that fire faster wait and go out together.`
            : "Nothing reaches you yet: alerts only show here until you turn on phone notifications or Telegram, or confirm your email."}
            {" "}<Link className="link" to="/account">Account settings</Link></p>
          {page.email && !page.email_confirmed && <p className="hint">Email goes out once you've confirmed {page.email} in Account (Newsletters).</p>}
          {adding && <div className="card dashed"><AlertForm onSaved={(r) => { setPage(r); setAdding(false); }} />
            <button className="btn quiet sm" style={{ marginTop: 10 }} onClick={() => setAdding(false)}>Cancel</button></div>}
        </section>

        <section className="stack" style={{ gap: 10 }}>
          <h2 className="h2">On</h2>
          {page.active.length === 0
            ? <Empty title="No alerts on"><p className="small muted">Set one here, or with Set alert on any company page or your watchlist.</p></Empty>
            : page.active.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => remove(a)} />)}
        </section>

        {page.triggered.length > 0 && (
          <section className="stack" style={{ gap: 10 }} aria-labelledby="a-fired">
            <div className="spread" style={{ gap: 10 }}>
              <h2 id="a-fired" className="h2">Fired today</h2>
              <button className="btn quiet sm" disabled={busy === "clear"} onClick={clear}>Clear the list</button>
            </div>
            {fired.today.length === 0 ? <p className="small muted">None today.</p>
              : fired.today.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => remove(a)} />)}
            <Earlier label="Fired earlier" count={fired.earlier.length}>
              {fired.earlier.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => remove(a)} />)}
            </Earlier>
          </section>
        )}
      </>}
      {editing && (
        <Modal title={`Edit alert on ${editing.symbol}`} onClose={() => setEditing(null)}>
          <AlertForm editing={editing} onSaved={(r) => { setPage(r); setEditing(null); }} />
          {editing.status === "triggered" && <p className="hint" style={{ marginTop: 10 }}>Saving turns it back on.</p>}
        </Modal>
      )}
    </div>
  );
}

function AlertRow({ a, busy, onEdit, onDelete }: { a: StockAlert; busy: boolean; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="card alert-row">
      <div className="stack" style={{ gap: 4, minWidth: 0 }}>
        <span className="row wrap" style={{ gap: 8 }}>
          <Link className="link" to={`/research/${a.region}/${encodeURIComponent(a.symbol)}`}><b>{a.symbol}</b></Link>
          <span className="badge skip">{a.region === "IN" ? "India" : "US"}</span>
          {a.repeat && <span className="badge next">Repeats</span>}
          {a.status === "triggered" && <span className="badge pass">Fired</span>}
        </span>
        <span>{a.text}</span>
        {a.last_text && <span className="small">{a.status === "triggered" ? "" : "Last: "}{a.last_text}{a.triggered_at ? <span className="muted"> · {ago(a.triggered_at)}</span> : null}</span>}
        {a.note && <span className="small muted" style={{ overflowWrap: "anywhere" }}>{a.note}</span>}
      </div>
      <div className="row" style={{ gap: 8 }}>
        <button className="btn quiet sm" onClick={onEdit} aria-label={`Edit the alert on ${a.symbol}`}><Pencil size={16} />Edit</button>
        <button className="btn danger sm" disabled={busy} onClick={onDelete} aria-label={`Delete the alert on ${a.symbol}`}><Trash size={16} />Delete</button>
      </div>
    </div>
  );
}
