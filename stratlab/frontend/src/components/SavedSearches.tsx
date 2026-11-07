import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useApp } from "../lib/app";
import { amount } from "../lib/themeFormat";
import { readSaved, sameSearch, savedApi, useSaved, type Changes, type SavedItem, type SavedKind, type Snap } from "../lib/saved";
import { changeLine, figureName, figureText, lastUpdated, savedUrl, savedWhat, type Row } from "../lib/savedSnap";
import { Card, CardHead, ConfirmDialog, DataTable, Dialog, Field, FormActions, FormGrid, Notice, Working, type Column } from "./kit";

/* ================= Saved searches and AI reads (R19) =================
 * One Save button and one list for every page that has a search or an AI read worth keeping (themes, red-flag filters, a company's AI read,
 * a comparison, a deep dive). Save is one click; the list says when each was last updated and has Open, Update, Rename and Remove. Update
 * reads the search again through its page's own endpoint and says what changed since the saved read, facts only. */

const fold = (p: Record<string, string | null | undefined>) => {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(p)) { const t = String(v ?? "").replace(/\s+/g, " ").trim(); if (t) out[k] = t; }
  return out;
};
const problemOf = (e: unknown) => ((e as { code?: string }).code === "saved_limit" || (e as { code?: string }).code === "slow_down"
  ? (e as Error).message : "It couldn't be saved just now. Try again in a moment.");

/** One click keeps the search (or the AI read) on the account; already kept, it says so. `snap`: what the page shows now, so a later
 * Update can say what changed (null when the read isn't finished: the first Update keeps it). */
export function SaveButton({ kind, name, params, snap, label = "Save" }: {
  kind: SavedKind; name: string; params: Record<string, string | null | undefined>; snap?: () => Snap | null | Promise<Snap | null>; label?: string;
}) {
  const { me } = useApp();
  const { items, count, limit } = useSaved(undefined, !!me);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  if (!me) return null;
  const p = fold(params);
  const kept = items?.find((x) => x.kind === kind && sameSearch(x.params, p));
  if (kept) return <span className="k-small k-muted saved-mark" data-testid="saved-mark">✓ Saved</span>;
  // the list is full: say so on the button, never a refusal after the click (owner, 7 Nov: people see their quotas)
  if (items && count >= limit) return <button type="button" className="btn quiet sm" data-testid="save-search" disabled>Saved list full ({limit}): remove one to save</button>;
  const save = async () => {
    setBusy(true); setProblem(null);
    try {
      let s: Snap | null = null;
      try { s = snap ? await snap() : null; } catch { s = null; }          // a read that isn't in: the first Update keeps it
      await savedApi.save(kind, name.trim() || label, p, s);
    } catch (e) { setProblem(problemOf(e)); }
    finally { setBusy(false); }
  };
  return (
    <>
      <button type="button" className="btn quiet sm" data-testid="save-search" disabled={busy || items === null} onClick={save}>{busy ? "Saving…" : label}</button>
      {problem && <span className="k-note" role="status">{problem}</span>}
    </>
  );
}

interface Result { id: string; name: string; kind: SavedKind; region: string; changes: Changes | null; note?: string }

/** The account's saved searches and reads (of one kind, or all), as a table with Open, Update, Rename and Remove, and what the last Update
 * found. Nothing is shown while there are none (`empty` says what to show instead, when given). */
export function SavedList({ kind, title, info, empty, id = "saved-searches" }: { kind?: SavedKind; title: string; info?: string; empty?: string; id?: string }) {
  const { me } = useApp();
  const { items, count, limit } = useSaved(kind, !!me);
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [renaming, setRenaming] = useState<SavedItem | null>(null);
  const [removing, setRemoving] = useState<SavedItem | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  if (!me || !items || (items.length === 0 && !empty)) return null;

  const update = async (x: SavedItem) => {
    if (x.open_only) { nav(savedUrl(x)); return; }
    setBusy(x.id); setResult(null); setProblem(null);
    try {
      const s = await readSaved(x);
      if (!s) { setResult({ id: x.id, name: x.name, kind: x.kind, region: x.params.region, changes: null, note: "This read is still being written. Press Update again in a minute." }); return; }
      const r = await savedApi.update(x.id, s);
      setResult({ id: x.id, name: r.item.name, kind: x.kind, region: x.params.region, changes: r.changes });
    } catch { setProblem(`“${x.name}” couldn't be read again just now. Try Update again in a moment.`); }
    finally { setBusy(null); }
  };
  const remove = async (x: SavedItem) => {
    try { await savedApi.remove(x.id); if (result?.id === x.id) setResult(null); }
    catch { setProblem("It couldn't be removed just now. Try again in a moment."); }
    finally { setRemoving(null); }
  };
  const working = items.find((x) => x.id === busy);
  const cols: Column<SavedItem>[] = [
    { key: "n", header: "Name", rowHeader: true, wrap: true, cell: (x) => <><Link className="link" to={savedUrl(x)}><b>{x.name}</b></Link><span className="k-sub-line k-muted">{savedWhat(x)}</span></> },
    ...(kind ? [] : [{ key: "k", header: "Kind", cell: (x: SavedItem) => x.kind_label }]),
    { key: "u", header: "Last updated", cell: (x) => lastUpdated(x) },
    { key: "a", header: "Actions", action: true, cell: (x) => (
      <span className="k-row tight saved-actions">
        <Link className="btn quiet sm" to={savedUrl(x)} aria-label={`Open ${x.name}`}>Open</Link>
        <button type="button" className="btn quiet sm" disabled={busy !== null} aria-label={`Update ${x.name}`} onClick={() => update(x)}>{busy === x.id ? "Updating…" : "Update"}</button>
        <button type="button" className="btn quiet sm" aria-label={`Rename ${x.name}`} onClick={() => setRenaming(x)}>Rename</button>
        <button type="button" className="btn quiet sm" aria-label={`Remove ${x.name}`} onClick={() => setRemoving(x)}>Remove</button>
      </span>) },
  ];
  return (
    <Card id={id} label={title}>
      <CardHead title={title} info={info ?? `Kept on your account, up to ${limit} in all. Update reads each one again now and says what changed since it was last read; Open shows the page.`}
        actions={<span className="k-note" data-testid="saved-count">{count} of {limit} saved</span>} />
      <DataTable stack label={title} rows={items} rowKey={(x) => x.id} columns={cols} empty={empty} />
      {working && <Working label={`Updating “${working.name}”: reading it again…`} />}
      {problem && <Notice tone="warn">{problem}</Notice>}
      {result && <WhatChanged r={result} />}
      {renaming && <RenameDialog item={renaming} onClose={() => setRenaming(null)} />}
      {removing && (
        <ConfirmDialog title={`Remove “${removing.name}”?`} confirmLabel="Remove" onConfirm={() => remove(removing)} onClose={() => setRemoving(null)}>
          It comes off your saved list. The page itself stays as it is.
        </ConfirmDialog>
      )}
    </Card>
  );
}

function RenameDialog({ item, onClose }: { item: SavedItem; onClose: () => void }) {
  const [name, setName] = useState(item.name);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const save = async () => {
    if (!name.trim()) { setProblem("Give it a name."); return; }
    setBusy(true);
    try { await savedApi.rename(item.id, name); onClose(); }
    catch { setProblem("The name couldn't be saved just now. Try again in a moment."); setBusy(false); }
  };
  return (
    <Dialog title="Rename" onClose={onClose}>
      <FormGrid label="Rename" onSubmit={(e) => { e.preventDefault(); save(); }}>
        <Field label="Name" wide value={name} maxLength={80} autoFocus onChange={(e) => setName(e.target.value)} error={problem ?? undefined} />
        <FormActions>
          <button className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
        </FormActions>
      </FormGrid>
    </Dialog>
  );
}

/** What the last Update found: one line, the key figures then and now, the rows added and removed, and the largest moves. */
function WhatChanged({ r }: { r: Result }) {
  const c = r.changes;
  const money = r.kind === "theme";
  const noun = r.kind === "filings" ? "Filing" : "Company";
  const rowCols: Column<Row>[] = [
    { key: "c", header: noun, rowHeader: true, wrap: true, cell: (x) => <>{x.label}{x.label !== x.key && !x.label.startsWith(`${x.key}:`) && <span className="k-sub-line k-muted">{x.key}</span>}</> },
    ...(money ? [{ key: "v", header: "Market value", numeric: true, cell: (x: Row) => amount(x.value, r.region === "US" ? "US" : "IN") }] : []),
  ];
  const pct = (v: number | null) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)}%`);
  return (
    <div className="k-inset saved-changes" data-testid="saved-changes" role="status">
      <b className="k-sub">What changed in “{r.name}”</b>
      <p className="k-small">{r.note ?? changeLine(c, r.kind)}</p>
      {c && !c.same && (
        <>
          {c.figures.length > 0 && (
            <DataTable label="Key figures, then and now" rows={c.figures} rowKey={(f) => f.name} columns={[
              { key: "f", header: "Figure", rowHeader: true, wrap: true, cell: (f) => figureName(f.name) },
              { key: "b", header: "At the saved read", numeric: true, cell: (f) => figureText(f.name, f.before, r.region) },
              { key: "a", header: "Now", numeric: true, cell: (f) => figureText(f.name, f.after, r.region) },
              { key: "c", header: "Change", numeric: true, cell: (f) => (f.name === "written" ? (f.change ? "Written again" : "Same read") : f.pct != null ? pct(f.pct) : f.change != null ? (f.change > 0 ? `+${f.change}` : String(f.change).replace("-", "−")) : "–") },
            ]} />
          )}
          {c.added.length > 0 && <DataTable stack label={`${r.kind === "filings" ? "New" : "Added"} since the saved read${c.added_count > c.added.length ? ` (the first ${c.added.length} of ${c.added_count})` : ""}`} rows={c.added} rowKey={(x) => x.key} columns={rowCols} />}
          {c.removed.length > 0 && <DataTable stack label={`${r.kind === "filings" ? "No longer in the list" : "Removed"} since the saved read${c.removed_count > c.removed.length ? ` (the first ${c.removed.length} of ${c.removed_count})` : ""}`} rows={c.removed} rowKey={(x) => x.key} columns={rowCols} />}
          {c.moves.length > 0 && (
            <DataTable stack label="Largest moves in market value" rows={c.moves} rowKey={(m) => m.key} columns={[
              { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (m) => <>{m.label}<span className="k-sub-line k-muted">{m.key}</span></> },
              { key: "b", header: "At the saved read", numeric: true, cell: (m) => amount(m.before, r.region === "US" ? "US" : "IN") },
              { key: "a", header: "Now", numeric: true, cell: (m) => amount(m.after, r.region === "US" ? "US" : "IN") },
              { key: "p", header: "Change", numeric: true, cell: (m) => pct(m.pct) },
            ]} />
          )}
        </>
      )}
    </div>
  );
}
