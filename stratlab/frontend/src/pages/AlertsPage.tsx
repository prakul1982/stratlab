import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { CHANNEL_NAME, alertsApi, type AlertsPage as Page, type StockAlert } from "../lib/alerts";
import { AlertForm } from "../components/AlertForm";
import { Bell, Pencil, Trash } from "../components/Icons";
import { Modal } from "../components/ui";
import { Earlier, LOCAL_TZ, splitToday } from "../components/Earlier";
import { Badge, Card, CardHead, ConfirmDialog, EmptyState, ErrorState, PageHeader, PlanNote, Skeleton, Stat, StatRow } from "../components/kit";

/** The alerts the user set on stocks: the ones on, the ones that fired, and a form for a new one. */
export function AlertsPage() {
  const { fail, notify } = useApp();
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<StockAlert | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [asking, setAsking] = useState<StockAlert | null>(null);       // the alert waiting for "Delete alert"

  const load = useCallback(() => { setError(null); return alertsApi.list().then((p) => { setPage(p); }).catch((e) => setError((e as Error).message)); }, []);
  useEffect(() => { load(); }, [load]);

  const remove = async (a: StockAlert) => {
    setAsking(null);
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
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/alerts")} title="Your stock alerts"
        lede="A message when a stock crosses a price, an average or an RSI level, moves a lot in a day, or makes a 52-week high or low. Checked every minute while its market is open." />
      {error && <ErrorState title="Your alerts couldn't be opened" action={{ label: "Try again", onClick: load }}>{error}</ErrorState>}
      {!page && !error && <Card><Skeleton label="Opening your alerts" lines={3} /></Card>}
      {page && <>
        <Card>
          <CardHead title="Your alerts" info="Your plan's limit counts the alerts that are on. Ones that already fired don't count, and repeating ones count once."
            actions={!adding ? <button className="btn sm" disabled={full} onClick={() => setAdding(true)}><Bell size={17} />New alert</button> : undefined} />
          <StatRow>
            <Stat label="Alerts on" value={`${page.count} of ${page.limit}`} />
            <Stat label="Sent by" value={page.channels.length ? page.channels.map((c) => CHANNEL_NAME[c] ?? c).join(", ") : "Nowhere yet"}
              note={page.channels.length ? "At most a few messages an hour: alerts that fire faster wait and go out together." : "Alerts only show here until you turn on phone notifications or Telegram, or confirm your email."} />
          </StatRow>
          {full && <PlanNote>That's all your plan has. Delete one to add another, or see plans for more.</PlanNote>}
          <p className="k-small"><Link className="link" to="/settings#notifications">Where alerts go and what to send</Link></p>
          {page.email && !page.email_confirmed && <p className="k-note">Email goes out once you've confirmed {page.email} in Settings (Notifications).</p>}
        </Card>

        {adding && (
          <Card>
            <CardHead title="New alert" actions={<button className="btn quiet sm" onClick={() => setAdding(false)}>Cancel</button>} />
            <AlertForm nowhere={!page.channels.length} link={false} onSaved={(r) => { setPage(r); setAdding(false); }} />
          </Card>
        )}

        <Card>
          <CardHead title="Alerts that are on" />
          {page.active.length === 0
            ? <EmptyState title="No alerts on">Set one here, or with Set alert on any company page or your watchlist.</EmptyState>
            : <div className="inv-rows">{page.active.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => setAsking(a)} />)}</div>}
        </Card>

        {page.triggered.length > 0 && (
          <Card label="Fired today">
            <CardHead title="Fired today" actions={<button className="btn quiet sm" disabled={busy === "clear"} onClick={clear}>Clear the list</button>} />
            {fired.today.length === 0 ? <p className="k-small k-muted">None today.</p>
              : <div className="inv-rows">{fired.today.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => setAsking(a)} />)}</div>}
            <Earlier label="Fired earlier" count={fired.earlier.length}>
              <div className="inv-rows">{fired.earlier.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => setAsking(a)} />)}</div>
            </Earlier>
          </Card>
        )}
      </>}
      {asking && (
        <ConfirmDialog title={`Delete the alert on ${asking.symbol}?`} confirmLabel="Delete alert" onConfirm={() => void remove(asking)} onClose={() => setAsking(null)}>
          {asking.text}. It stops watching the stock and is removed from this list.
        </ConfirmDialog>
      )}
      {editing && (
        <Modal title={`Edit alert on ${editing.symbol}`} onClose={() => setEditing(null)}>
          <div className="k-stack">
            <AlertForm editing={editing} link={false} onSaved={(r) => { setPage(r); setEditing(null); }} />
            {editing.status === "triggered" && <p className="k-note">Saving turns it back on.</p>}
          </div>
        </Modal>
      )}
    </div>
  );
}

function AlertRow({ a, busy, onEdit, onDelete }: { a: StockAlert; busy: boolean; onEdit: () => void; onDelete: () => void }) {
  return (
    <div className="alert-row inv-alert">
      <div className="k-stack">
        <span className="k-row">
          <Link className="link" to={`/research/${a.region}/${encodeURIComponent(a.symbol)}`}><b>{a.symbol}</b></Link>
          <Badge tone="plain" dot={false}>{a.region === "IN" ? "India" : "US"}</Badge>
          {a.repeat && <Badge tone="ok" dot={false}>Repeats</Badge>}
          {a.status === "triggered" && <Badge tone="plain">Fired</Badge>}
        </span>
        <span>{a.text}</span>
        {a.last_text && <span className="k-small">{a.status === "triggered" ? "" : "Last: "}{a.last_text}{a.triggered_at ? <span className="k-muted"> · {ago(a.triggered_at)}</span> : null}</span>}
        {a.note && <span className="k-small k-muted k-any">{a.note}</span>}
      </div>
      <div className="k-row">
        <button className="btn quiet sm" onClick={onEdit} aria-label={`Edit the alert on ${a.symbol}`}><Pencil size={16} />Edit</button>
        <button className="btn danger sm" disabled={busy} onClick={onDelete} aria-label={`Delete the alert on ${a.symbol}`}><Trash size={16} />Delete</button>
      </div>
    </div>
  );
}
