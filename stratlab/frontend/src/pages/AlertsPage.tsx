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
import { Badge, Card, CardHead, ConfirmDialog, EmptyState, ErrorState, Notice, PageHeader, PlanNote, Select, Skeleton, Stat, StatRow } from "../components/kit";
import { limitLine, planIdOf } from "../lib/lockText";

/** Above this many alerts on, the list gets a search box and a sort (DP2-023: 25 alerts in one unsorted list). */
const FIND_FROM = 8;
type Sort = "new" | "az" | "old";

/** The alerts the user set on stocks: the ones on, the ones that fired, and a form for a new one. */
export function AlertsPage() {
  const { fail, notify, me } = useApp();
  const [page, setPage] = useState<Page | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<StockAlert | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [asking, setAsking] = useState<StockAlert | null>(null);       // the alert waiting for "Delete alert"
  const [find, setFind] = useState("");
  const [sort, setSort] = useState<Sort>("new");

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
  // the one lock wording (DP2-022, DP1-018): the plan and its count, what the next plan gives; the note adds the price
  const plan = planIdOf(me?.plan);
  const limit = page ? limitLine(plan, "stock_alerts", `Your ${me?.plan_info.name ?? "plan"} plan has ${page.limit} alert${page.limit === 1 ? "" : "s"} on at a time. Delete one to add another`, "alerts") : null;
  const q = find.trim().toUpperCase();
  const active = (page?.active ?? []).filter((a) => !q || a.symbol.includes(q) || a.text.toUpperCase().includes(q) || (a.note ?? "").toUpperCase().includes(q))
    .sort((a, b) => (sort === "az" ? a.symbol.localeCompare(b.symbol) : sort === "old" ? a.created_at.localeCompare(b.created_at) : b.created_at.localeCompare(a.created_at)));
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
          {/* the button stays on at the limit and opens the limit's note, as Net worth's does (DP2-022: one pattern) */}
          <CardHead title="Your alerts" info="Your plan's limit counts the alerts that are on. Ones that already fired don't count, and repeating ones count once."
            actions={<button className="btn sm" onClick={() => setAdding(true)}><Bell size={17} />New alert</button>} />
          <StatRow>
            <Stat label="Alerts on" value={`${page.count} of ${page.limit}`} />
            {/* where a fired alert goes, in plain words (DP2-023, DP1-023: "Sent by: Nowhere yet") */}
            <Stat label="Sent by" value={page.channels.length ? page.channels.map((c) => CHANNEL_NAME[c] ?? c).join(", ") : "This page only"}
              note={page.channels.length ? "At most a few messages an hour: alerts that fire faster wait and go out together."
                : "No phone, Telegram or confirmed email is set up, so a fired alert is listed here and nowhere else."} />
          </StatRow>
          {full && limit && (limit.next ? <PlanNote plan={limit.next}>{limit.text}</PlanNote> : <Notice>{limit.text}</Notice>)}
          <p className="k-small"><Link className="link" to="/settings#notifications">Where alerts go and what to send</Link></p>
          {/* the address itself stays in Settings, not printed on this page (DP1-023) */}
          {page.email && !page.email_confirmed && <p className="k-note">Alerts go to your email once you've confirmed the address in Settings (Notifications).</p>}
        </Card>

        <Card>
          <CardHead title="Alerts that are on" actions={page.active.length > FIND_FROM ? (
            <span className="k-row">
              <input className="k-input sm" type="search" aria-label="Find an alert" placeholder="Find a stock" value={find} onChange={(e) => setFind(e.target.value)} />
              <Select small label="Sort alerts" value={sort} onChange={(v) => setSort(v as Sort)} options={[{ value: "new", label: "Newest first" }, { value: "old", label: "Oldest first" }, { value: "az", label: "Stock A to Z" }]} />
            </span>) : undefined} />
          {page.active.length === 0
            ? <EmptyState title="No alerts on">Set one here, or with Set alert on any company page or your watchlist.</EmptyState>
            : active.length === 0 ? <p className="k-small k-muted">No alert on matches "{find.trim()}".</p>
            : <div className="inv-rows">{active.map((a) => <AlertRow key={a.id} a={a} busy={busy === a.id} onEdit={() => setEditing(a)} onDelete={() => setAsking(a)} />)}</div>}
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
      {/* the new alert in a pop-up, like editing one, not a long block pushed into the page (DP2-023) */}
      {adding && page && (
        <Modal title={full ? "Your alerts are full" : "New alert"} onClose={() => setAdding(false)}>
          {full && limit
            ? (limit.next ? <PlanNote plan={limit.next}>{limit.text}</PlanNote> : <Notice>{limit.text}</Notice>)
            : <AlertForm nowhere={!page.channels.length} link={false} onSaved={(r) => { setPage(r); setAdding(false); }} />}
        </Modal>
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
