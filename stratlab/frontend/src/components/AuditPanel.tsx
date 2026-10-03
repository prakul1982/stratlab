import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

type Level = "mismatch" | "gap" | "error";
type Issue = { level: Level; area: string; detail: string };
type Row = { symbol: string; name: string; seconds: number; issues: Issue[] };
interface AuditState {
  running: boolean; cancelled?: boolean; label?: string; docs?: boolean; total?: number; done?: number; rows?: Row[]; started_at?: string; finished_at?: string | null;
  summary?: { companies: number; clean: number; mismatches: number; gaps: number; errors: number; avg_seconds: number | null;
    by_area: Record<string, Record<Level, number>>; slowest: { symbol: string; seconds: number }[] };
  sets: { id: string; name: string; count: number }[];
}

const LEVEL: Record<Level, [string, string]> = { mismatch: ["Mismatch", "fail"], error: ["Error", "warn"], gap: ["Gap", "next"] };

/** The data audit: every company in a set checked against its sources, on the live server. */
export function AuditPanel() {
  const { fail } = useApp();
  const [s, setS] = useState<AuditState | null>(null);
  const [set, setSet] = useState("nifty50");
  const [custom, setCustom] = useState("");
  const [docs, setDocs] = useState(false);
  const [show, setShow] = useState<Level | "all">("mismatch");

  const load = useCallback(async () => { try { setS(await api<AuditState>("/admin/audit")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!s?.running) return;
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [s?.running, load]);

  const stop = async () => { try { setS(await api<AuditState>("/admin/audit", { method: "DELETE" })); } catch (e) { fail(e); } };
  const start = async () => {
    const symbols = custom.split(/[\s,]+/).filter(Boolean);
    try { setS(await api<AuditState>("/admin/audit", { method: "POST", body: { set, symbols, docs } })); } catch (e) { fail(e); }
  };

  const rows = useMemo(() => (s?.rows ?? []).map((r) => ({ ...r, shown: r.issues.filter((i) => show === "all" || i.level === show) }))
    .filter((r) => r.shown.length), [s?.rows, show]);
  const sum = s?.summary;

  const csv = () => {
    const lines = [["symbol", "name", "level", "area", "detail"].join(",")];
    for (const r of s?.rows ?? []) for (const i of r.issues) lines.push([r.symbol, r.name, i.level, i.area, i.detail].map((x) => `"${String(x).replace(/"/g, '""')}"`).join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = "stratlab-audit.csv"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };

  return (
    <section className="card stack" style={{ gap: 12 }}>
      <h2 className="h2">Data audit</h2>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>Runs every company in a set through the deep dive on this server: numbers, prices, industry, valuation, checklist and documents,
        each compared with its source. Mismatches are numbers that disagree with the source; gaps are things a user would still have to look up elsewhere. No AI is used.
        About 3 to 10 seconds a company.</p>
      {!s ? <p className="small muted">Loading…</p> : (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <select value={set} onChange={(e) => setSet(e.target.value)} disabled={s.running || !!custom.trim()} aria-label="Companies to check">
              {s.sets.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.count})</option>)}
            </select>
            <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Or symbols, e.g. INFY TITAN" style={{ minWidth: 200 }} disabled={s.running} aria-label="Symbols to check" />
            <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={docs} onChange={(e) => setDocs(e.target.checked)} disabled={s.running} />Also try reading documents (slower)</label>
            <button className="btn sm" disabled={s.running} onClick={start}>{s.running ? `Checking ${s.done ?? 0} of ${s.total}…` : "Run audit"}</button>
            {s.running && <button className="btn quiet sm" onClick={stop}>Stop</button>}
          </div>
          {sum && s.label && (
            <>
              <p className="small" style={{ margin: 0 }}><b>{s.label}</b>{s.docs ? " with documents" : ""} · {s.running ? `started ${ago(s.started_at!)}` : s.finished_at ? `${s.cancelled ? "stopped" : "finished"} ${ago(s.finished_at)}` : ""}
                {" · "}{sum.companies} checked, {sum.clean} clean · <span className="neg">{sum.mismatches} mismatches</span> · {sum.gaps} gaps · {sum.errors} errors
                {sum.avg_seconds != null && ` · ${sum.avg_seconds}s a company`}</p>
              {Object.keys(sum.by_area).length > 0 && (
                <div className="table-wrap"><table>
                  <thead><tr><th>Area</th><th className="num">Mismatches</th><th className="num">Gaps</th><th className="num">Errors</th></tr></thead>
                  <tbody>{Object.entries(sum.by_area).sort((a, b) => (b[1].mismatch * 3 + b[1].error * 2 + b[1].gap) - (a[1].mismatch * 3 + a[1].error * 2 + a[1].gap)).map(([area, c]) => (
                    <tr key={area}><td>{area}</td><td className="num">{c.mismatch}</td><td className="num">{c.gap}</td><td className="num">{c.error}</td></tr>
                  ))}</tbody>
                </table></div>
              )}
              <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                <div className="seg" role="radiogroup" aria-label="Show">
                  {(["mismatch", "error", "gap", "all"] as const).map((k) => (
                    <button key={k} role="radio" aria-checked={show === k} aria-pressed={show === k} onClick={() => setShow(k)}>{k === "all" ? "All" : LEVEL[k][0] + "s"}</button>
                  ))}
                </div>
                {!!s.rows?.length && <button className="btn quiet sm" onClick={csv}>Download CSV</button>}
              </div>
              {rows.length === 0 ? <p className="small muted">Nothing of this kind{s.running ? " yet" : ""}.</p> : (
                <div className="stack" style={{ gap: 8 }}>
                  {rows.map((r) => (
                    <div key={r.symbol} className="stack small" style={{ gap: 2 }}>
                      <span><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}/deep`}><b>{r.name}</b></Link> <span className="mono tiny muted">{r.symbol} · {r.seconds}s</span></span>
                      {r.shown.map((i, n) => <span key={n}><span className={`badge ${LEVEL[i.level][1]}`}>{i.area}</span> {i.detail}</span>)}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
