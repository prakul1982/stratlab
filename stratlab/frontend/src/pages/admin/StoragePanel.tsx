import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago } from "../../lib/format";
import { Card, CardHead, ConfirmDialog, ErrorState, Meter, Notice, Skeleton } from "../../components/kit";

type Sized = { name: string; bytes: number };
type Group = { prefix: string; bytes: number; rows: number };
type Storage = {
  limit: number; warn_at: number; total?: number; share?: number; tables?: Sized[]; settings?: Group[];
  missing?: boolean; sql?: string; error?: string;
  market: { enabled: boolean; total?: number; tables?: Sized[]; error?: string };
  move: { running?: boolean; started_at?: string; finished_at?: string; moved?: { settings: number; snapshots: number }; error?: string | null };
};

const mb = (n: number) => `${(n / 1024 / 1024).toLocaleString("en-IN", { maximumFractionDigits: n < 10 * 1024 * 1024 ? 1 : 0 })} MB`;

/** Admin: how full the main database is against the free plan's limit, what fills it, and the second database on
 * Railway that the bulky market data can move to. */
export function StoragePanel() {
  const { fail } = useApp();
  const [s, setS] = useState<Storage | null>(null);
  const [copied, setCopied] = useState(false);
  const [asking, setAsking] = useState(false);
  const load = useCallback(async () => { try { setS(await api<Storage>("/admin/storage")); } catch (e) { fail(e); } }, [fail]);
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
  const copy = async () => {
    try { await navigator.clipboard.writeText(s?.sql ?? ""); setCopied(true); } catch { /* the SQL stays shown to copy by hand */ }
  };

  const share = s?.share ?? 0;
  const high = !!s && share >= s.warn_at;
  return (
    <Card label="Storage">
      <CardHead title="Storage" />
      {!s ? <Skeleton label="Loading storage" lines={2} /> : s.error ? (
        <ErrorState title="Couldn't read the database's size">{s.error}</ErrorState>
      ) : s.missing ? (
        <div className="k-stack">
          <p className="k-small">One step to see the size here: in Supabase, open <b>SQL Editor</b> → <b>New query</b>, paste this, and press <b>Run</b>. It only reads sizes.</p>
          <pre className="k-code adm-pre">{s.sql}</pre>
          <div className="k-row">
            <button type="button" className="btn sm" onClick={copy}>{copied ? "Copied" : "Copy SQL"}</button>
            <button type="button" className="btn quiet sm" onClick={load}>Check again</button>
          </div>
        </div>
      ) : (
        <div className="k-stack">
          <div className="k-small"><b>{mb(s.total ?? 0)}</b> of {mb(s.limit)} used ({Math.round(share * 100)}%)</div>
          <div role="meter" aria-label="Main database used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}><Meter pct={share * 100} /></div>
          {high && <Notice tone="warn">Getting full: move the market data to the second database below.</Notice>}
          <div className="adm-sizes">
            <Sizes title="Biggest tables" rows={(s.tables ?? []).slice(0, 6).map((t) => [t.name.replace(/^public\./, ""), t.bytes])} />
            <Sizes title="Biggest stored data" rows={(s.settings ?? []).slice(0, 6).map((g) => [`${g.prefix} (${g.rows.toLocaleString("en-IN")})`, g.bytes])} />
          </div>
        </div>
      )}
      {s && (
        <div className="k-stack">
          <h3 className="adm-sub">Second database for market data</h3>
          {s.market.enabled ? (
            <>
              <p className={`k-small ${s.market.error ? "k-down" : ""}`}>
                {s.market.error ? `Can't reach it: ${s.market.error}` : <>Connected{s.market.total != null && <> · {mb(s.market.total)} used</>}. New market data is saved there.</>}
              </p>
              <p className={`k-small ${s.move.error ? "k-down" : "k-muted"}`}>
                {s.move.running ? <>Moving… started {ago(s.move.started_at ?? "")}</>
                  : s.move.error ? <>The last move stopped: {s.move.error}. Running it again carries on.</>
                  : s.move.finished_at && s.move.moved ? <>Last move {ago(s.move.finished_at)}: {s.move.moved.settings.toLocaleString("en-IN")} stored items and {s.move.moved.snapshots.toLocaleString("en-IN")} option chains.
                    {" "}Supabase frees the space after it's reclaimed: run <code>vacuum full public.option_snapshots, public.app_settings;</code> in its SQL Editor.</>
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
      {asking && (
        <ConfirmDialog title="Move the market data?" confirmLabel="Move it" danger={false} onConfirm={move} onClose={() => setAsking(false)}>
          Whole-market checks, breadth history, stored company reads and option chains move to the second database. Users' own data stays where it is.
        </ConfirmDialog>
      )}
    </Card>
  );
}

function Sizes({ title, rows }: { title: string; rows: [string, number][] }) {
  if (!rows.length) return null;
  return (
    <div>
      <div className="k-note k-muted">{title}</div>
      <div className="k-rows">{rows.map(([name, bytes]) => <div key={name}><span>{name}</span><b>{mb(bytes)}</b></div>)}</div>
    </div>
  );
}
