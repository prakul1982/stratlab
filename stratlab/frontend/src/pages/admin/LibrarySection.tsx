import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { fmtDate, fmtDateTime, IST } from "../../lib/format";
import { bytesText, hoursText } from "../../lib/usageText";
import { Card, CardHead, ConfirmDialog, DataTable, EmptyState, Field, Select, Skeleton, Working, type Column } from "../../components/kit";

/* Admin → Library (R19, owner 7 Nov: "make a tab in admin too where i can see all the data"): everything kept once for every user.
 * The shared store's kinds with their counts, sizes, hits, refreshes and the work the hits saved; the theme library row by row with
 * Refresh now and Remove; the other shared data the app keeps (company pages, deep dives, results ...); people's saved searches as counts. */

type Store = { kind: string; label: string; entries: number; bytes: number; hits: number; misses: number; hit_rate: number | null; refreshes: number;
  by: Record<string, number>; oldest: string | null; newest: string | null; saved_seconds: number; saved_ai_calls: number };
type Theme = { id: string; label: string; q: string; region: string; aliases: string[]; members: number | null; size: number; hits: number;
  searched: number; refreshes: number; at: string | null; last: string | null; refreshing: boolean };
type Stored = { prefix: string; label: string; entries: number | null; bytes: number | null; oldest: string | null; newest: string | null };
type View = { stores: Store[]; themes: Theme[]; stored: Stored[]; saved: { kind: string; count: number }[] | null };

const REGION_WORD: Record<string, string> = { IN: "India", US: "US" };

const when = (iso: string | null | undefined) => (iso ? fmtDateTime(iso, { tz: IST, zone: false, year: false }) : "–");
const day = (iso: string) => fmtDate(iso.slice(0, 10), { year: false });
/** "28 Oct" or "2 Oct – 28 Oct": the oldest and newest entry of a store, by day. */
const span = (a: string | null, b: string | null) => (!a || !b ? "–" : day(a) === day(b) ? day(a) : `${day(a)} – ${day(b)}`);
const byText = (by: Record<string, number>) => Object.entries(by).filter(([, n]) => n > 0).map(([p, n]) => `${p[0].toUpperCase()}${p.slice(1)} ${n}`).join(", ");

export function LibrarySection() {
  const { fail } = useApp();
  const [view, setView] = useState<View | null>(null);
  const [q, setQ] = useState("");
  const [region, setRegion] = useState("");
  const [again, setAgain] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Theme | null>(null);
  useEffect(() => {
    let live = true;
    const t = setTimeout(() => {
      api<View>(`/admin/stored?${new URLSearchParams({ q, region })}`).then((v) => live && setView(v))
        .catch((e) => { if (live) { setView({ stores: [], themes: [], stored: [], saved: null }); fail(e); } });
    }, 200);
    return () => { live = false; clearTimeout(t); };
  }, [q, region, again, fail]);
  // a theme being written again shows "Refreshing" until it's in: asked again every 10 s while one is
  useEffect(() => {
    if (!view?.themes.some((t) => t.refreshing)) return;
    const t = setTimeout(() => setAgain((n) => n + 1), 10_000);
    return () => clearTimeout(t);
  }, [view]);
  const act = async (what: "refresh" | "remove", kind: string, id: string) => {
    setBusy(id);
    try { await api(`/admin/stored/${what}`, { method: "POST", body: { kind, id } }); setAgain((n) => n + 1); }
    catch (e) { fail(e); }
    finally { setBusy(null); }
  };
  const total = view ? view.stores.reduce((a, s) => ({ hits: a.hits + s.hits, sec: a.sec + s.saved_seconds, calls: a.calls + s.saved_ai_calls, bytes: a.bytes + s.bytes }), { hits: 0, sec: 0, calls: 0, bytes: 0 }) : null;

  const storeCols: Column<Store>[] = [
    { key: "l", header: "What", rowHeader: true, wrap: true, lead: true, cell: (s) => (
      <span className="k-stack k-tight">{s.label}{s.entries > 0 && <span className="k-note">Kept {span(s.oldest, s.newest)}</span>}</span>) },
    { key: "n", header: "Kept", numeric: true, cell: (s) => s.entries.toLocaleString("en-IN") },
    { key: "b", header: "Size", numeric: true, cell: (s) => bytesText(s.bytes) },
    { key: "h", header: "Served (hit rate)", numeric: true, wrap: true, cell: (s) => `${s.hits.toLocaleString("en-IN")}${s.hit_rate == null ? "" : ` (${s.hit_rate}%)`}` },
    { key: "f", header: "Refreshes", wrap: true, cell: (s) => (s.refreshes ? `${s.refreshes.toLocaleString("en-IN")} (${byText(s.by)})` : "0") },
    { key: "s", header: "Work saved", wrap: true, cell: (s) => (s.hits ? `${hoursText(s.saved_seconds)}${s.saved_ai_calls ? `, ${s.saved_ai_calls.toLocaleString("en-IN")} AI calls` : ""}` : "–") },
  ];
  const themeCols: Column<Theme>[] = [
    { key: "n", header: "Theme", rowHeader: true, wrap: true, lead: true, cell: (t) => (
      <span className="k-stack k-tight"><Link className="link" to={`/research/themes?q=${encodeURIComponent(t.label)}&region=${t.region}`}><b>{t.label}</b></Link>
        <span className="k-note">{REGION_WORD[t.region] ?? t.region}{t.aliases.length > 0 ? ` · also ${t.aliases.filter((a) => a !== t.q).join(", ") || t.q}` : ""}</span></span>) },
    { key: "m", header: "Companies", numeric: true, cell: (t) => (t.members ?? "–") },
    { key: "a", header: "Last read", cell: (t) => (t.refreshing ? <Working label="Refreshing" inline /> : when(t.at)) },
    { key: "s", header: "Searched", numeric: true, cell: (t) => t.searched.toLocaleString("en-IN") },
    { key: "f", header: "Refreshes", numeric: true, cell: (t) => t.refreshes },
    { key: "z", header: "Size", numeric: true, cell: (t) => bytesText(t.size) },
    { key: "x", header: "", action: true, cell: (t) => (
      <span className="k-row">
        <button type="button" className="btn quiet sm" disabled={busy === t.id || t.refreshing} onClick={() => { void act("refresh", "theme", t.id); }}>{t.refreshing ? "Refreshing…" : "Refresh now"}</button>
        <button type="button" className="btn quiet sm" disabled={busy === t.id} onClick={() => setRemoving(t)}>Remove</button>
      </span>) },
  ];
  const prefixCols: Column<Stored>[] = [
    { key: "l", header: "What", rowHeader: true, wrap: true, cell: (s) => s.label },
    { key: "n", header: "Kept", numeric: true, cell: (s) => (s.entries == null ? "–" : s.entries.toLocaleString("en-IN")) },
    { key: "b", header: "Size", numeric: true, cell: (s) => bytesText(s.bytes) },
    { key: "o", header: "Kept between", wrap: true, cell: (s) => span(s.oldest, s.newest) },
  ];
  return (
    <>
      <Card label="Kept for everyone">
        <CardHead title="Kept for everyone" info="Results worked out once and served to every user until someone presses Refresh (or you refresh or remove them here). Work saved is an estimate: each time one was served instead of worked out again, the time and AI calls that read usually takes." />
        {!view || !total ? <Skeleton label="Reading the library" lines={4} /> : (
          <>
            <p className="k-small k-muted" data-testid="library-total">Served {total.hits.toLocaleString("en-IN")} times from the library: about {hoursText(total.sec)} of work and {total.calls.toLocaleString("en-IN")} AI calls saved. {bytesText(total.bytes)} kept.</p>
            <DataTable label="Shared stores" rows={view.stores} rowKey={(s) => s.kind} columns={storeCols} stack />
          </>
        )}
      </Card>
      <Card label="Theme library">
        <CardHead title={`Theme library${view ? ` (${view.themes.length})` : ""}`} info="Every theme read kept for everyone: the AI map, its checked companies and descriptions. A search for the same theme, however it's written, is served from here at once." />
        <div className="k-toolbar">
          <Field label="Search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Theme or alias" />
          <Select label="Market" value={region} onChange={setRegion} options={[{ value: "", label: "Both markets" }, { value: "IN", label: "India" }, { value: "US", label: "US" }]} />
        </div>
        {!view ? <Skeleton label="Reading the themes" lines={3} />
          : !view.themes.length ? <EmptyState title={q || region ? "No theme matches" : "No theme kept yet"}>A theme is kept here once its read is finished: its map written and every company checked.</EmptyState>
            : <DataTable label="Themes in the library" rows={view.themes} rowKey={(t) => t.id} columns={themeCols} stack />}
      </Card>
      <Card label="Other shared data">
        <CardHead title="Other shared data" info="What the app already keeps in the database for every user: company pages, deep dives, results and the rest, worked out by its own jobs." />
        {!view ? <Skeleton label="Counting" lines={3} /> : <DataTable label="Other shared data" rows={view.stored} rowKey={(s) => s.prefix} columns={prefixCols} stack />}
      </Card>
      <Card label="Saved searches">
        <CardHead title="Saved searches" info="How many searches people have saved, by kind. Counts only: nobody's saved searches are listed." />
        {!view ? <Skeleton label="Counting" lines={2} />
          : !view.saved ? <p className="k-small k-muted">No saved searches are counted yet.</p>
            : <DataTable label="Saved searches by kind" rows={view.saved} rowKey={(s) => s.kind} columns={[
              { key: "k", header: "Kind", rowHeader: true, cell: (s: { kind: string; count: number }) => s.kind[0].toUpperCase() + s.kind.slice(1) },
              { key: "n", header: "Saved", numeric: true, cell: (s) => s.count.toLocaleString("en-IN") }]} />}
      </Card>
      {removing && (
        <ConfirmDialog title={`Remove ${removing.label}?`} confirmLabel="Remove" onClose={() => setRemoving(null)}
          onConfirm={() => { const t = removing; setRemoving(null); void act("remove", "theme", t.id); }}>
          The next person who searches for it gets it worked out afresh, and it is kept again.
        </ConfirmDialog>
      )}
    </>
  );
}
