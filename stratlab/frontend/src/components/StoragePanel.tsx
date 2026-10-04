import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

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
  const load = useCallback(async () => { try { setS(await api<Storage>("/admin/storage")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.move?.running) return;
    const t = window.setInterval(load, 10000);
    return () => window.clearInterval(t);
  }, [s?.move?.running, load]);
  const move = async () => {
    if (!window.confirm("Move the market data (whole-market checks, breadth history, stored company reads, option chains) to the second database? Users' own data stays where it is.")) return;
    try { await api("/admin/storage/move", { method: "POST" }); load(); } catch (e) { fail(e); }
  };
  const copy = async () => {
    try { await navigator.clipboard.writeText(s?.sql ?? ""); setCopied(true); } catch { /* the SQL stays shown to copy by hand */ }
  };

  const share = s?.share ?? 0;
  const high = !!s && share >= s.warn_at;
  return (
    <section className="card stack" style={{ gap: 10 }} aria-label="Storage">
      <h2 className="h2">Storage</h2>
      {!s ? <p className="small muted">Loading…</p> : s.error ? (
        <p className="small" style={{ color: "var(--red-ink, #b42318)" }}>Couldn't read the database's size: {s.error}</p>
      ) : s.missing ? (
        <div className="stack" style={{ gap: 8 }}>
          <p className="small" style={{ margin: 0, maxWidth: "80ch" }}>
            One step to see the size here: in Supabase, open <b>SQL Editor</b> → <b>New query</b>, paste this, and press <b>Run</b>. It only reads sizes.
          </p>
          <pre className="small" style={{ maxHeight: 160, overflow: "auto", margin: 0, padding: 10, background: "var(--paper-2)", borderRadius: 8, whiteSpace: "pre" }}>{s.sql}</pre>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn sm" onClick={copy}>{copied ? "Copied" : "Copy SQL"}</button>
            <button className="btn sm ghost" onClick={load}>Check again</button>
          </div>
        </div>
      ) : (
        <div className="stack" style={{ gap: 8 }}>
          <div className="small"><b>{mb(s.total ?? 0)}</b> of {mb(s.limit)} used ({Math.round(share * 100)}%)</div>
          <div role="meter" aria-label="Main database used" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(share * 100)}
            style={{ height: 8, borderRadius: 4, background: "var(--paper-2)", overflow: "hidden" }}>
            <div style={{ width: `${Math.min(100, share * 100)}%`, height: "100%", borderRadius: 4, background: high ? "var(--orange)" : "var(--blue)" }} />
          </div>
          {high && <p className="small" style={{ margin: 0, color: "var(--orange-ink)" }}>Getting full: move the market data to the second database below.</p>}
          <div className="row" style={{ gap: 24, flexWrap: "wrap", alignItems: "flex-start" }}>
            <Sizes title="Biggest tables" rows={(s.tables ?? []).slice(0, 6).map((t) => [t.name.replace(/^public\./, ""), t.bytes])} />
            <Sizes title="Biggest stored data" rows={(s.settings ?? []).slice(0, 6).map((g) => [`${g.prefix} (${g.rows.toLocaleString("en-IN")})`, g.bytes])} />
          </div>
        </div>
      )}
      {s && (
        <div className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
          <b className="small">Second database for market data</b>
          {s.market.enabled ? (
            <>
              <div className="small">
                {s.market.error ? <span style={{ color: "var(--red-ink, #b42318)" }}>Can't reach it: {s.market.error}</span>
                  : <>Connected{s.market.total != null && <> · {mb(s.market.total)} used</>}. New market data is saved there.</>}
              </div>
              <div className="small muted">
                {s.move.running ? <>Moving… started {ago(s.move.started_at ?? "")}</>
                  : s.move.error ? <span style={{ color: "var(--red-ink, #b42318)" }}>The last move stopped: {s.move.error}. Running it again carries on.</span>
                  : s.move.finished_at && s.move.moved ? <>Last move {ago(s.move.finished_at)}: {s.move.moved.settings.toLocaleString("en-IN")} stored items and {s.move.moved.snapshots.toLocaleString("en-IN")} option chains.
                    {" "}Supabase frees the space after it's reclaimed: run <code>vacuum full public.option_snapshots, public.app_settings;</code> in its SQL Editor.</>
                  : "Older market data is still in the main database until you move it."}
              </div>
              <div><button className="btn sm" disabled={!!s.move.running} onClick={move}>{s.move.running ? "Moving…" : "Move market data now"}</button></div>
            </>
          ) : (
            <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>
              Not set up. When the main database nears its limit: in Railway, <b>New → Database → PostgreSQL</b>; then on the backend service add the
              variable <code>MARKET_DATABASE_URL</code> = <code>{"${{Postgres.DATABASE_URL}}"}</code>. After it redeploys, a button here moves the data.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

function Sizes({ title, rows }: { title: string; rows: [string, number][] }) {
  if (!rows.length) return null;
  return (
    <div className="small" style={{ minWidth: 220 }}>
      <div className="muted" style={{ marginBottom: 4 }}>{title}</div>
      {rows.map(([name, bytes]) => (
        <div key={name} className="spread" style={{ gap: 12 }}><span>{name}</span><span className="num">{mb(bytes)}</span></div>
      ))}
    </div>
  );
}
