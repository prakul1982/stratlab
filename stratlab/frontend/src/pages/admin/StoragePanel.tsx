import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, safeHref } from "../../lib/format";
import { Card, CardHead, ConfirmDialog, DataTable, Disclosure, ErrorState, Meter, Notice, Skeleton } from "../../components/kit";

type Sized = { name: string; bytes: number };
type Group = { prefix: string; bytes: number; rows: number };
/** One real database against its own real limit (DJ-020): Railway's Postgres (its limit is the volume's, known only when
 * set on the server; else a link to where Railway shows it) and Supabase (the plan's limit), with what Supabase still
 * holds from before the move. */
export type DbMeter = { name: string; used: number | null; limit: number | null; share: number | null; link: string; error?: string | null;
  note?: string | null; reclaimable?: number | null; reclaimable_tables?: string[] };
type Storage = {
  limit: number; warn_at: number; total?: number; share?: number | null; tables?: Sized[]; settings?: Group[]; databases?: DbMeter[]; main?: "railway" | "supabase";
  missing?: boolean; sql?: string; error?: string;
  market: { enabled: boolean; total?: number; tables?: Sized[]; error?: string };
  move: { running?: boolean; started_at?: string; finished_at?: string; moved?: { settings: number; snapshots: number }; error?: string | null };
  users?: { on: "railway" | "supabase"; forced?: boolean; state?: "pending" | "done" | "failed"; asked_at?: string; done_at?: string;
    failed_at?: string; copied?: Record<string, number>; error?: string | null };
};

export const mb = (n: number) => `${(n / 1024 / 1024).toLocaleString("en-IN", { maximumFractionDigits: n < 10 * 1024 * 1024 ? 1 : 0 })} MB`;

/** Admin: how full each real database is against its own limit (DJ-020), what fills the main one, and the second
 * database on Railway that the bulky market data can move to. */
export function StoragePanel() {
  const { fail } = useApp();
  const [s, setS] = useState<Storage | null>(null);
  const [copied, setCopied] = useState(false);
  const [asking, setAsking] = useState(false);
  const [askingUsers, setAskingUsers] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [failed, setFailed] = useState(false);
  const load = useCallback(async () => { try { setS(await api<Storage>("/admin/storage")); setFailed(false); } catch (e) { setFailed(true); fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.move?.running) return;
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, [s?.move?.running, load]);
  const move = async () => {
    setAsking(false);
    try { await api("/admin/storage/move", { method: "POST" }); load(); } catch (e) { fail(e); }
  };
  const moveUsers = async () => {
    setAskingUsers(false);
    try {
      await api("/admin/storage/move-users", { method: "POST" });
      setRestarting(true);
      window.setTimeout(() => { setRestarting(false); void load(); }, 90000);     // the server is back in about a minute
    } catch (e) { fail(e); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(s?.sql ?? ""); setCopied(true); } catch { /* the SQL stays shown to copy by hand */ }
  };

  const meters = s?.databases ?? [];
  const high = !!s && meters.some((d) => d.share != null && d.share >= s.warn_at);
  const reclaim = meters.find((d) => d.reclaimable);
  return (
    <Card label="Storage">
      <CardHead title="Storage" />
      {!s ? (failed ? <ErrorState title="The storage size couldn't be read" action={{ label: "Try again", onClick: () => void load() }} /> : <Skeleton label="Loading storage" lines={2} />) : s.error ? (
        <ErrorState title="Couldn't read the database's size">{s.error}</ErrorState>
      ) : s.missing ? (
        <div className="k-stack">
          <p className="k-small">Not measured yet. One step shows the size here: copy the SQL, then in Supabase open <b>SQL Editor</b> → <b>New query</b>, paste it and press <b>Run</b>. It only reads sizes.</p>
          <div className="k-row">
            <button type="button" className="btn sm" onClick={copy}>{copied ? "Copied" : "Copy SQL"}</button>
            <button type="button" className="btn quiet sm" onClick={load}>Check again</button>
          </div>
          <Disclosure summary="Show the SQL" testId="storage-sql"><pre className="k-code adm-pre" tabIndex={0} aria-label="The SQL to run">{s.sql}</pre></Disclosure>
        </div>
      ) : (
        <div className="k-stack">
          <div className="adm-meters" data-testid="storage-meters">
            {meters.map((d) => <DbLine key={d.name} d={d} />)}
          </div>
          {high && <Notice tone="warn">{s.main === "supabase" ? "Getting full: move the market data to the second database below." : "A database is getting full: open its dashboard from the line above."}</Notice>}
          {reclaim && (
            // in plain words, with the exact step one click away (DJ-025: "run vacuum full …" as the instruction itself)
            <div className="k-stack k-small" data-testid="storage-reclaim">
              <span>Supabase still holds {mb(reclaim.reclaimable!)} of copies left from before users' data moved to Railway ({(reclaim.reclaimable_tables ?? []).map((t) => t.replace(/^public\./, "")).join(", ")}). StratLab no longer reads them; Supabase gives the space back only once they are emptied and compacted.</span>
              <Disclosure summary="Show the step, for Supabase's SQL Editor" testId="storage-reclaim-sql">
                <pre className="k-code adm-pre" tabIndex={0} aria-label="The step to run in Supabase">{`truncate ${(reclaim.reclaimable_tables ?? []).join(", ")};\nvacuum full ${(reclaim.reclaimable_tables ?? []).join(", ")};`}</pre>
              </Disclosure>
            </div>
          )}
          {/* each list says whose database it is from, and the Railway total is split into its two parts, so the lists add up to the meter (LIVE1C-017:
              115 MB beside lists of 10 MB, the other lists being Supabase's) */}
          {s.main === "railway" && s.total != null && s.market.total != null && (
            <p className="k-small k-muted" data-testid="storage-split">
              Railway Postgres {mb(s.market.total)} = users' data {mb(s.total)} + market data and the rest {mb(Math.max(0, s.market.total - s.total))}.
            </p>
          )}
          <div className="adm-sizes">
            <Sizes title={s.main === "railway" ? "Biggest tables: users' data (Railway)" : "Biggest tables (Supabase)"} rows={(s.tables ?? []).slice(0, 6).map((t) => [t.name.replace(/^public\./, ""), t.bytes])} />
            <Sizes title={s.main === "railway" ? "Biggest stored data: users' data (Railway)" : "Biggest stored data (Supabase)"} rows={(s.settings ?? []).slice(0, 6).map((g) => [`${g.prefix} (${g.rows.toLocaleString("en-IN")})`, g.bytes])} />
            {s.main === "railway" && <Sizes title="Biggest tables: market data (Railway)" rows={(s.market.tables ?? []).slice(0, 6).map((t) => [t.name, t.bytes])} />}
          </div>
        </div>
      )}
      {s && (
        <div className="k-stack">
          <h3 className="adm-sub">Second database for market data</h3>
          {s.market.enabled ? (
            <>
              <p className={`k-small ${s.market.error ? "k-down" : ""}`}>
                {s.market.error ? `Can't reach it: ${s.market.error}` : <>Connected: it is the Railway Postgres above{s.main === "railway" ? ", which holds users' data too" : ""}. New market data is saved there.</>}
              </p>
              <p className={`k-small ${s.move.error ? "k-down" : "k-muted"}`}>
                {s.move.running ? <>Moving… started {ago(s.move.started_at ?? "")}</>
                  : s.move.error ? <>The last move stopped: {s.move.error}. Running it again carries on.</>
                  : s.move.finished_at && s.move.moved ? <>Last move {ago(s.move.finished_at)}: {s.move.moved.settings.toLocaleString("en-IN")} stored items and {s.move.moved.snapshots.toLocaleString("en-IN")} option chains.</>
                  : "Older market data is still in the main database until you move it."}
              </p>
              <div className="k-row"><button type="button" className="btn sm" disabled={!!s.move.running} onClick={() => setAsking(true)}>{s.move.running ? "Moving…" : "Move market data now"}</button></div>
            </>
          ) : (
            <p className="k-small k-muted">
              Not set up. When the main database nears its limit: in Railway, <b>New → Database → PostgreSQL</b>; then on the backend service add the
              variable <code>MARKET_DATABASE_URL</code> = <code>{"${{Postgres.DATABASE_URL}}"}</code>. After it redeploys, a button here moves the data.
            </p>
          )}
        </div>
      )}
      {s?.users && s.market.enabled && (
        <div className="k-stack">
          <h3 className="adm-sub">Users' data</h3>
          {s.users.on === "railway" ? (
            <p className="k-small">On Railway{s.users.done_at && <>, since {ago(s.users.done_at)}</>}. Supabase is used for sign-ins only.</p>
          ) : (
            <>
              <p className={`k-small ${s.users.state === "failed" ? "k-down" : ""}`}>
                {restarting || s.users.state === "pending" ? "Moving: the server is restarting and copying everything across. Back in about a minute."
                  : s.users.state === "failed" ? <>The last move stopped and nothing changed: {s.users.error}. Users' data is still on Supabase; pressing the button tries again.</>
                  : s.users.forced ? <>On Supabase: <code>MAIN_DATABASE=supabase</code> is set on the backend.</>
                  : "On Supabase, whose free plan counts every read the server makes. Moving it puts it next to the server on Railway; sign-ins stay with Supabase."}
              </p>
              {!s.users.forced && (
                <div className="k-row"><button type="button" className="btn sm" disabled={restarting || s.users.state === "pending"} onClick={() => setAskingUsers(true)}>
                  {restarting || s.users.state === "pending" ? "Moving…" : "Move users' data to Railway"}</button></div>
              )}
            </>
          )}
        </div>
      )}
      {askingUsers && (
        <ConfirmDialog title="Move users' data to Railway?" confirmLabel="Move and restart" danger={false} onConfirm={moveUsers} onClose={() => setAskingUsers(false)}>
          Profiles, notebooks, paper sessions, settings and usage are copied to Railway's Postgres. The server restarts and
          copies everything before it answers anyone, so the site is away for about a minute. Running paper sessions are
          saved first and carry on after. If the copy fails, nothing changes and Supabase stays in use.
        </ConfirmDialog>
      )}
      {asking && (
        <ConfirmDialog title="Move the market data?" confirmLabel="Move it" danger={false} onConfirm={move} onClose={() => setAsking(false)}>
          Whole-market checks, breadth history, stored company reads and option chains move to the second database. Users' own data stays where it is.
        </ConfirmDialog>
      )}
    </Card>
  );
}

/** One database's line: what it uses against its limit, or what it uses and where its limit is shown. */
function DbLine({ d }: { d: DbMeter }) {
  const pct = d.share != null ? Math.round(d.share * 100) : null;
  return (
    <div className="k-stack" data-testid="storage-db">
      <div className="k-small">
        <b>{d.name}</b>{": "}
        {d.used == null ? <span className="k-down">size not read{d.error ? ` (${d.error})` : ""}</span>
          : d.limit ? <><b>{mb(d.used)}</b> of {mb(d.limit)} used ({pct}%)</> : <><b>{mb(d.used)}</b> used</>}
        {" · "}<a className="link" href={safeHref(d.link)} target="_blank" rel="noopener noreferrer">{d.limit ? `Open ${d.name.split(" ")[0]}` : `Volume size on ${d.name.split(" ")[0]}`}</a>
      </div>
      {d.used != null && d.limit ? <div role="meter" aria-label={`${d.name} used`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct ?? 0}><Meter pct={(d.share ?? 0) * 100} /></div> : null}
      {d.note && <span className="k-note k-muted">{d.note}</span>}
    </div>
  );
}

function Sizes({ title, rows }: { title: string; rows: [string, number][] }) {
  if (!rows.length) return null;
  return (
    <div>
      <div className="k-note k-muted">{title}</div>
      <DataTable label={title} rows={rows} rowKey={([name]) => name} columns={[
        { key: "n", header: "Name", rowHeader: true, wrap: true, cell: ([name]) => name },
        { key: "s", header: "Size", numeric: true, cell: ([, bytes]) => mb(bytes) },
      ]} />
    </div>
  );
}
