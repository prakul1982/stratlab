import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

type Level = "mismatch" | "gap" | "error";
type Region = "IN" | "US";
type Issue = { level: Level; area: string; detail: string };
/** A company's page: BSE-only companies (BSE:543210) open by their BSE code. */
const pageSymbol = (s: string) => (s.startsWith("BSE:") ? s.slice(4) : s);   // a BSE code opens the same page as its symbol

type Row = { symbol: string; name: string; seconds: number; issues: Issue[] };
type Summary = { companies: number; clean: number; mismatches: number; gaps: number; errors: number; avg_seconds: number | null;
  by_area: Record<string, Record<Level, number>>; slowest: { symbol: string; seconds: number }[] };
interface AuditState {
  running: boolean; cancelled?: boolean; label?: string; docs?: boolean; region?: Region; total?: number; done?: number; rows?: Row[]; started_at?: string; finished_at?: string | null;
  summary?: Summary;
  sets: { id: string; name: string; count: number }[];
}

const SHOWN = 300;
const LEVEL: Record<Level, [string, string]> = { mismatch: ["Mismatch", "fail"], error: ["Error", "warn"], gap: ["Gap", "next"] };

/** The data audit: every company in a set checked against its sources, on the live server. */
export function AuditPanel() {
  const { fail } = useApp();
  const [s, setS] = useState<AuditState | null>(null);
  const [region, setRegion] = useState<Region>("IN");
  const [set, setSet] = useState("nifty50");
  const [custom, setCustom] = useState("");
  const [docs, setDocs] = useState(false);

  const load = useCallback(async () => { try { setS(await api<AuditState>(`/admin/audit?region=${region}`)); } catch (e) { fail(e); } }, [fail, region]);
  useEffect(() => { load(); }, [load]);
  const pick = (r: Region) => { setRegion(r); setSet(r === "US" ? "us_mega" : "nifty50"); };
  useEffect(() => {
    if (!s?.running) return;
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [s?.running, load]);

  const stop = async () => { try { setS(await api<AuditState>("/admin/audit", { method: "DELETE" })); } catch (e) { fail(e); } };
  const start = async () => {
    const symbols = custom.split(/[\s,]+/).filter(Boolean);
    try { setS(await api<AuditState>("/admin/audit", { method: "POST", body: { region, set, symbols, docs } })); } catch (e) { fail(e); }
  };

  const sum = s?.summary;

  return (
    <section className="card stack" style={{ gap: 12 }}>
      <h2 className="h2">Data audit</h2>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>Runs every company in a set through the deep dive on this server: numbers, prices, industry, valuation, checklist and documents,
        each compared with its source. Mismatches are numbers that disagree with the source; gaps are things a user would still have to look up elsewhere. No AI is used.
        About 3 to 10 seconds a company.</p>
      {!s ? <p className="small muted">Loading…</p> : (
        <>
          <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <div className="seg" role="radiogroup" aria-label="Market">
              {(["IN", "US"] as const).map((r) => (
                <button key={r} role="radio" aria-checked={region === r} aria-pressed={region === r} disabled={s.running} onClick={() => pick(r)}>{r === "IN" ? "India" : "US"}</button>))}
            </div>
            <select value={set} onChange={(e) => setSet(e.target.value)} disabled={s.running || !!custom.trim()} aria-label="Companies to check">
              {s.sets.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.count})</option>)}
            </select>
            <input className="input" value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Or symbols, e.g. INFY TITAN" style={{ minWidth: 200 }} disabled={s.running} aria-label="Symbols to check" />
            {region === "IN" && <label className="row small" style={{ gap: 6 }}><input type="checkbox" checked={docs} onChange={(e) => setDocs(e.target.checked)} disabled={s.running} />Also try reading documents (slower)</label>}
            <button className="btn sm" disabled={s.running} onClick={start}>{s.running ? `Checking ${s.done ?? 0} of ${s.total}…` : "Run audit"}</button>
            {s.running && <button className="btn quiet sm" onClick={stop}>Stop</button>}
          </div>
          {sum && s.label && (
            <>
              <p className="small" style={{ margin: 0 }}><b>{s.label}</b>{s.docs ? " with documents" : ""} · {s.running ? `started ${ago(s.started_at!)}` : s.finished_at ? `${s.cancelled ? "stopped" : "finished"} ${ago(s.finished_at)}` : ""}
                {" · "}{sum.companies} checked, {sum.clean} clean · <span className="neg">{sum.mismatches} mismatches</span> · {sum.gaps} gaps · {sum.errors} errors
                {sum.avg_seconds != null && ` · ${sum.avg_seconds}s a company`}</p>
              <Findings rows={s.rows ?? []} sum={sum} running={s.running} file="stratlab-audit.csv" region={s.region ?? "IN"} />
            </>
          )}
        </>
      )}
    </section>
  );
}

interface MarketState {
  enabled: boolean; listed: number; checked: number; due: number; current: string | null; eta_hours: number | null;
  list_at: string | null; list_error: string | null;
  full?: { running: boolean; since: string | null; done_at: string | null; left: number; checked: number | null };
  new_listings: { symbol: string; name: string; listed: string | null; checked: boolean }[];
  summary: Summary; rows: Row[];
}

/** Every company listed in India (NSE, plus those only on BSE), checked in the background while switched on; new listings first. */
export function MarketAuditPanel({ region = "IN" }: { region?: Region }) {
  const { fail } = useApp();
  const us = region === "US";
  const [m, setM] = useState<MarketState | null>(null);
  const load = useCallback(async () => { try { setM(await api<MarketState>(`/admin/audit/market?region=${region}`)); } catch (e) { fail(e); } }, [fail, region]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!m?.enabled) return;
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, [m?.enabled, load]);
  const send = async (body: object) => { try { setM(await api<MarketState>("/admin/audit/market", { method: "POST", body: { region, ...body } })); } catch (e) { fail(e); } };
  const sum = m?.summary;

  return (
    <section className="card stack" style={{ gap: 12 }}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Whole market: {us ? "US" : "India"}</h2>
        {m && <button className="btn sm" onClick={() => send({ on: !m.enabled })}>{m.enabled ? "Pause" : "Check new listings"}</button>}
      </div>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>{us
        ? "The SEC's list of companies is read once a day. Each company that newly appears on it is checked once from its filings, the same way as the audit above; ones that drop off the list are removed."
        : "The lists of every company in India (all of NSE, plus those listed only on BSE, shown as BSE: and their code) are read once a day. Each new listing is checked once, the same way as the audit above; delisted companies drop off."}
        {" "}Every company not checked yet is checked once to start (companies already checked keep their results); after that only new listings are, unless you start another full check. A check that failed because a source was down is tried again. It pauses while an audit above runs.</p>
      {!m ? <p className="small muted">Loading…</p> : (
        <>
          <p className="small" style={{ margin: 0 }}>
            <b>{m.enabled ? (m.due ? `Running · ${m.due.toLocaleString("en-IN")} to check` : "Running · up to date") : m.checked ? "Paused" : "Not started"}</b>
            {" · "}{m.listed ? `${m.listed.toLocaleString("en-IN")} companies listed` : "list not read yet"}, {m.checked.toLocaleString("en-IN")} checked so far
            {m.enabled && m.eta_hours != null && m.due > 0 && ` · about ${m.eta_hours < 1 ? "under an hour" : `${Math.round(m.eta_hours)} hours`} left`}
            {m.current && <> · now <span className="mono">{m.current}</span></>}
          </p>
          <p className="small muted" style={{ margin: 0 }}>
            {m.list_error ? <span className="neg">Couldn't read the exchange's list: {m.list_error}{m.list_at ? ` (using the one from ${ago(m.list_at)})` : ""}. </span>
              : m.list_at ? `List read ${ago(m.list_at)}. ` : ""}
            <button className="btn quiet sm" onClick={() => send({ read_list: true })}>Read the list now</button>{" "}
            {m.full && !m.full.running && <button className="btn quiet sm" onClick={() => { if (confirm("Check every listed company once more? It takes about a day, then goes back to new listings only.")) send({ full: true }); }}>Check everything once</button>}
          </p>
          {m.full?.running && (
            <p className="small" style={{ margin: 0 }}><b>Full check:</b> {(m.full.checked ?? 0).toLocaleString("en-IN")} of {m.listed.toLocaleString("en-IN")} companies done
              {m.full.since ? `, started ${ago(m.full.since)}` : ""}. New listings go first; then it goes back to new listings only.{!m.enabled && " Switch it on to run."}</p>
          )}
          {m.full && !m.full.running && m.full.done_at && <p className="small muted" style={{ margin: 0 }}>Last full check finished {ago(m.full.done_at)}.</p>}
          {m.new_listings.length > 0 && (
            <p className="small" style={{ margin: 0 }}>New listings: {m.new_listings.slice(0, 12).map((n, i) => (
              <span key={n.symbol}>{i ? ", " : ""}<Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(n.symbol))}/deep`}>{n.symbol}</Link>
                <span className="muted">{n.listed ? ` (${n.listed})` : ""}{n.checked ? "" : " · queued"}</span></span>))}</p>
          )}
          {sum && sum.companies > 0 && (
            <>
              <p className="small" style={{ margin: 0 }}>{sum.companies.toLocaleString("en-IN")} checked, {sum.clean.toLocaleString("en-IN")} clean · <span className="neg">{sum.mismatches} mismatches</span> · {sum.gaps} gaps · {sum.errors} errors</p>
              <Findings rows={m.rows} sum={sum} running={m.enabled} file={`stratlab-${us ? "us" : "india"}-market-audit.csv`} region={region} />
            </>
          )}
        </>
      )}
    </section>
  );
}

/** The area table, the kind filter, each company's findings, and a CSV of every finding. */
function Findings({ rows: all, sum, running, file, region }: { rows: Row[]; sum: Summary; running: boolean; file: string; region: Region }) {
  const [show, setShow] = useState<Level | "all">("mismatch");
  const rows = useMemo(() => all.map((r) => ({ ...r, shown: r.issues.filter((i) => show === "all" || i.level === show) }))
    .filter((r) => r.shown.length), [all, show]);
  const csv = () => {
    const lines = [["symbol", "name", "level", "area", "detail"].join(",")];
    for (const r of all) for (const i of r.issues) lines.push([r.symbol, r.name, i.level, i.area, i.detail].map((x) => `"${String(x).replace(/"/g, '""')}"`).join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = file; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  return (
    <>
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
            <button key={k} role="radio" aria-checked={show === k} aria-pressed={show === k} onClick={() => setShow(k)}>{k === "all" ? "All" : k === "mismatch" ? "Mismatches" : LEVEL[k][0] + "s"}</button>
          ))}
        </div>
        {!!all.length && <button className="btn quiet sm" onClick={csv}>Download CSV</button>}
      </div>
      {rows.length === 0 ? <p className="small muted">Nothing of this kind{running ? " yet" : ""}.</p> : (
        <div className="stack" style={{ gap: 8 }}>
          {rows.length > SHOWN && <p className="small muted" style={{ margin: 0 }}>Showing {SHOWN} of {rows.length} companies; the CSV has all of them.</p>}
          {rows.slice(0, SHOWN).map((r) => (
            <div key={r.symbol} className="stack small" style={{ gap: 2 }}>
              <span><Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(r.symbol))}/deep`}><b>{r.name}</b></Link> <span className="mono tiny muted">{r.symbol} · {r.seconds}s</span></span>
              {r.shown.map((i, n) => <span key={n}><span className={`badge ${LEVEL[i.level][1]}`}>{i.area}</span> {i.detail}</span>)}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
