/* Import a watchlist (owner, 12 Nov): paste symbols (one a line or separated by commas, any case, NSE, BSE or US tickers, ISINs or company
 * names) or drop a CSV or Excel file and pick its column; each is looked up with the app's own symbol search and shown as found, to
 * confirm (with suggestions) or not found; then "Add N to <list>". The list's plan limit is said before anything is added, and the server
 * keeps it too. Pasting is on every plan; a file on Basic and up (plans.py watchlist_import). Downloaded only when opened. */
import { useEffect, useMemo, useState, type DragEvent, type ReactNode } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { adoptWatchlist, type Region } from "../../lib/research";
import { getLists, putItems, type WatchAnswer } from "../../lib/watchApi";
import { DEFAULT_ID, labelOf, listName } from "../../lib/watch";
import { LIMITS, type PlanId } from "../../lib/plans";
import { addLabel, allQueries, chosenItem, IMPORT_MAX, limitSaid, room, splitPasted, summaryLine, toAdd, type ImportColumn, type ImportRow } from "../../lib/watchImport";
import { Badge } from "../kit/Badge";
import { DataTable, type Column } from "../kit/DataTable";
import { Dialog } from "../kit/Dialog";
import { Select } from "../kit/Form";
import { Seg } from "../kit/Seg";
import { Working } from "../kit/States";
import { UploadButton, UploadProblem, useUploadProblem } from "../kit/UploadButton";
import "./import.css";

const MARKETS = [{ value: "both", label: "India and US", short: "Both" }, { value: "IN", label: "India" }, { value: "US", label: "US" }];
const FILE_MB = 1;
const read64 = (f: File) => new Promise<string>((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = () => no(r.error); r.readAsDataURL(f); });

/** `lock`: the opener's PlanNote with FILE_LOCK (passed in, not imported here: importing the lock code here changed how the build
 * splits it, and the landing page's preload lists grew). */
export default function ImportWatchlist({ initialList, onClose, onDone, lock }: { initialList?: string; onClose: () => void; onDone?: (a: WatchAnswer) => void; lock: ReactNode }) {
  const { me, notify, fail } = useApp();
  const plan = me?.plan_info.name ?? "Free";
  const canFile = me?.plan_info.features?.watchlist_import !== false;
  const [answer, setAnswer] = useState<WatchAnswer | null>(null);
  const [target, setTarget] = useState(initialList ?? DEFAULT_ID);
  // read once when opened (the lists as they are now, with the plan's limits)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { getLists().then(setAnswer).catch((e) => { fail(e); onClose(); }); }, []);
  const [market, setMarket] = useState("both");
  const [text, setText] = useState("");
  const [cols, setCols] = useState<{ name: string; columns: ImportColumn[] } | null>(null);
  const [col, setCol] = useState<number | null>(null);
  const [reading, setReading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const upload = useUploadProblem();
  const [rows, setRows] = useState<ImportRow[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [adding, setAdding] = useState(false);

  const pasted = useMemo(() => splitPasted(text), [text]);
  const column = cols?.columns.find((c) => c.index === col)?.values ?? [];
  const queries = useMemo(() => allQueries(pasted, column), [pasted, column]);
  const list = answer?.lists.find((l) => l.id === target) ?? answer?.lists[0] ?? null;
  const named = list ? (list.default ? list.name : listName(list.name)) : "your list";
  const onList = useMemo(() => new Set(list?.items.map((i) => i.id) ?? []), [list]);
  const items = rows ? toAdd(rows, picks, onList) : [];
  const cap = answer?.limits.symbols ?? null;
  const fit = room(cap, list?.items.length ?? 0, items.length);
  const next = answer?.limits.next.symbols;
  const nextCap = next ? LIMITS[next.toLowerCase() as PlanId]?.watchlist_symbols : undefined;
  const nextWords = next ? (nextCap == null ? `${next} has no limit` : `${next} keeps ${nextCap}`) : null;
  const over = list ? limitSaid({ cap, used: list.items.length, adding: items.length, plan, list: named, next: nextWords }) : null;

  const readFile = async (f: File | undefined | null) => {
    upload.clear();
    if (!f) return;
    if (!canFile) { upload.reject("Importing from a file is on the Basic plan. Paste the symbols instead, or see Plans."); return; }
    if (f.size > FILE_MB * 1024 * 1024) { upload.reject(`That file is larger than ${FILE_MB} MB. A watchlist file is much smaller; check it's the right file.`); return; }
    setReading(true);
    try {
      const got = await api<{ columns: ImportColumn[]; guess: number | null }>("/watch/import/file", { method: "POST", body: { data: await read64(f), filename: f.name.slice(0, 200) } });
      setCols({ name: f.name, columns: got.columns });
      setCol(got.guess ?? got.columns[0]?.index ?? null);
    } catch (e) { if (!upload.refused(e)) fail(e); } finally { setReading(false); }
  };
  const drop = (e: DragEvent) => { e.preventDefault(); setDragOver(false); void readFile(e.dataTransfer.files?.[0]); };

  const check = async () => {
    if (!queries.length) return;
    setChecking(true);
    try {
      const r = await api<{ rows: ImportRow[] }>("/watch/import/resolve", { method: "POST", body: { queries, market } });
      setRows(r.rows); setPicks({});
    } catch (e) { fail(e); } finally { setChecking(false); }
  };

  const add = async () => {
    if (!list || !fit) return;
    setAdding(true);
    try {
      const keep = items.slice(0, fit);
      const a = await putItems(list.id, [...list.items, ...keep]);
      // the first list is the Research watchlist: its stocks are that page's list too (as Market Watch hands them over)
      const first = a.lists.find((l) => l.default);
      if (first) adoptWatchlist(first.items.filter((i) => (i.market === "IN" || i.market === "US") && (i.kind === "stock" || i.kind === "etf")).map((i) => ({ region: i.market as Region, symbol: i.symbol, name: i.name })));
      onDone?.(a);
      notify(`Added ${keep.length} to ${named}.`);
      onClose();
    } catch (e) { fail(e); } finally { setAdding(false); }
  };

  const columns: Column<ImportRow>[] = [
    // what was given with its result under it, and what it adds: two columns, so a phone reads a row across, not a tall card a line
    { key: "q", header: "You gave", rowHeader: true, wrap: true, cell: (r) => <><span className="wl-q">{r.query}</span>
      <span className="k-sub-line">{r.status === "found" ? <Badge tone="ok">Found</Badge> : r.status === "confirm" ? <Badge tone="warn">Confirm</Badge> : <Badge tone="plain" dot={false}>Not found</Badge>}</span></> },
    { key: "m", header: "Adds", wrap: true, cell: (r) => {
      const it = chosenItem(r, picks[r.query]);
      if (r.status === "missing") return <span className="k-muted">Nothing in the lists matches. Check the spelling, or add it from the search.</span>;
      if (r.status === "confirm") {
        return <Select small label={`Which company is ${r.query}?`} value={picks[r.query] ?? r.suggestions[0]?.id ?? ""} onChange={(v) => setPicks((p) => ({ ...p, [r.query]: v }))}
          options={[...r.suggestions.map((s) => ({ value: s.id, label: `${labelOf(s)}: ${s.name} (${s.market === "US" ? "US" : "India"})` })), { value: "", label: "Skip this one" }]} />;
      }
      return it ? <span><b>{labelOf(it)}</b> <span className="k-muted">{it.name} · {it.market === "US" ? "US" : "India"}</span>{onList.has(it.id) && <span className="k-sub-line k-muted">Already on {named}</span>}</span> : null;
    } },
  ];

  return (
    <Dialog title="Import a watchlist" onClose={onClose} wide>
      {!answer ? <Working label="Reading your lists" /> : !rows ? (
        <div className="k-stack wl-import" data-testid="watch-import">
          <Seg label="Look in" value={market} onChange={setMarket} options={MARKETS} />
          <label className="k-stack k-tight">
            <span className="k-label">Paste symbols, one a line or separated by commas</span>
            <textarea className="k-textarea" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={"RELIANCE, TCS, HDFCBANK\nNVDA\ninfosys"} spellCheck={false} />
            <span className="k-note">NSE, BSE or US tickers, BSE codes, ISINs or company names, in any case. Up to {IMPORT_MAX} at a time.</span>
          </label>
          {canFile ? (
            <div className={`wl-drop${dragOver ? " over" : ""}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)} onDrop={drop} data-testid="watch-import-drop">
              <span className="k-small">Or drop a CSV or Excel file here (a broker's holdings export works too)</span>
              <UploadButton quiet label="Choose a file" busy={reading} accept=".csv,.xlsx,.xls,.txt,text/csv" ariaLabel="Choose a CSV or Excel file of symbols"
                onFiles={(fs, reset) => { void readFile(fs?.[0]).finally(reset); }} />
            </div>
          ) : (
            lock
          )}
          <UploadProblem problem={upload.problem} />
          {cols && (
            <div className="k-stack k-tight" data-testid="watch-import-columns">
              <span className="k-label" aria-hidden="true">Column with the symbols in {cols.name}</span>
              <Select label={`Column with the symbols in ${cols.name}`} value={col ?? ""} onChange={(v) => setCol(Number(v))}
                options={cols.columns.map((c) => ({ value: c.index, label: `${c.name}: ${c.sample.join(", ")}${c.count > c.sample.length ? "…" : ""} (${c.count})` }))} />
            </div>
          )}
          <div className="k-row">
            <button type="button" className="btn" disabled={!queries.length || checking} onClick={() => void check()}>
              {checking ? "Checking…" : queries.length ? `Check ${queries.length} symbol${queries.length === 1 ? "" : "s"}` : "Check symbols"}</button>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="k-stack wl-import" data-testid="watch-import-results">
          <p className="k-small" role="status" data-testid="watch-import-summary"><b>{summaryLine(rows)}</b>{rows.some((r) => r.status === "confirm") ? ". Check the suggested company for each one to confirm." : "."}</p>
          <div className="wl-results"><DataTable label="What each symbol matched" rows={rows} rowKey={(r) => r.query} columns={columns} stack={false} /></div>
          {answer.lists.length > 1 && (
            <div className="k-stack k-tight">
              <span className="k-label" aria-hidden="true">Add to</span>
              <Select label="Add to" value={list?.id ?? DEFAULT_ID} onChange={setTarget} options={answer.lists.map((l) => ({ value: l.id, label: l.default ? l.name : listName(l.name) }))} />
            </div>
          )}
          {over && <p className="k-small" role="status" data-testid="watch-import-limit">{over}</p>}
          <div className="k-row">
            <button type="button" className="btn" disabled={!fit || adding} onClick={() => void add()} data-testid="watch-import-add">{adding ? "Adding…" : addLabel(items.length, fit, named)}</button>
            <button type="button" className="btn quiet" onClick={() => setRows(null)}>Back</button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
