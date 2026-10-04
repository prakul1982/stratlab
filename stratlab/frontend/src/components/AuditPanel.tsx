import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

/** fact: true of the company (a recent listing, no calls held), not a gap of ours; pending: a source turned the check away, so it runs again. */
type Level = "mismatch" | "gap" | "error" | "fact" | "pending";
type Region = "IN" | "US";
type Issue = { level: Level; area: string; detail: string };
/** A company's page: BSE-only companies (BSE:543210) open by their BSE code. */
const pageSymbol = (s: string) => (s.startsWith("BSE:") ? s.slice(4) : s);   // a BSE code opens the same page as its symbol

type Row = { symbol: string; name: string; seconds: number; issues: Issue[] };
type Summary = { companies: number; clean: number; mismatches: number; gaps: number; errors: number; facts?: number; pending?: number; avg_seconds: number | null;
  by_area: Record<string, Partial<Record<Level, number>>>; slowest: { symbol: string; seconds: number }[] };
interface AuditState {
  running: boolean; cancelled?: boolean; label?: string; docs?: boolean; region?: Region; total?: number; done?: number; rows?: Row[]; started_at?: string; finished_at?: string | null;
  summary?: Summary;
  sets: { id: string; name: string; count: number }[];
}

const SHOWN = 300;
const LEVEL: Record<Level, [string, string]> = { mismatch: ["Mismatch", "fail"], error: ["Error", "warn"], gap: ["Gap", "next"],
  fact: ["Fact", "warn"], pending: ["Not checked yet", "warn"] };
/** Which areas need a look first: mismatches, then errors, then gaps. */
const weight = (c: Partial<Record<Level, number>>) => (c.mismatch ?? 0) * 3 + (c.error ?? 0) * 2 + (c.gap ?? 0);
const SHOWS: Record<Level | "all", string> = { mismatch: "Mismatches", error: "Errors", gap: "Gaps", fact: "Facts", pending: "Not checked yet", all: "All" };
/** The counts line: facts and companies not checked yet only when there are any. */
const count = (n: number, one: string, many: string) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
const tally = (sum: Summary) => `${count(sum.gaps, "gap", "gaps")} · ${count(sum.errors, "error", "errors")}${sum.facts ? ` · ${count(sum.facts, "fact", "facts")}` : ""}${sum.pending ? ` · ${sum.pending.toLocaleString("en-IN")} not checked yet` : ""}`;

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
                {" · "}{sum.companies} checked, {sum.clean} clean · <span className="neg">{count(sum.mismatches, "mismatch", "mismatches")}</span> · {tally(sum)}
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
  /** why nothing is being checked: switched off, an audit above is running, or a source is turning every company away */
  paused?: "off" | "busy" | "cooling" | null; cool_minutes?: number; rate_per_hour?: number;
  list_at: string | null; list_error: string | null; reset_at?: string | null;
  full?: { running: boolean; since: string | null; done_at: string | null; left: number; checked: number | null; everything?: boolean; pending_only?: boolean };
  monthly?: { on: boolean; last: string | null; next: string | null };
  retry?: { waiting: number; due: number; next: string | null; gap_hours: number; batch: number };
  bse?: { refusing?: boolean; refused_at?: string | null; waiting: number };
  pending?: number;
  new_listings: { symbol: string; name: string; listed: string | null; checked: boolean }[];
  summary: Summary; rows: Row[];
}

/** "1 Nov" from "2026-11-01". */
const dayMonth = (d: string) => new Date(`${d}T00:00:00Z`).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
/** "in 40 min", "in 3 h" for a time ahead. */
const until = (iso: string) => {
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  return s < 60 ? "any minute" : s < 3600 ? `in ${Math.round(s / 60)} min` : `in ${Math.round(s / 3600)} h`;
};
const hoursText = (h: number) => (h < 1 ? "under an hour" : h < 48 ? `about ${Math.round(h)} hours` : `about ${Math.round(h / 24)} days`);
const PAUSED: Record<"off" | "busy" | "cooling", string> = {
  off: "Paused: switched off. Press Start to check companies.",
  busy: "Paused: an audit above is running. It carries on by itself when that finishes.",
  cooling: "Slowed down: a source is turning every company away, so it waits between companies until it answers again.",
};

/** Every company listed in India (NSE, plus those only on BSE) or filing with the SEC, checked in the background
 * while started: new listings first, a full check of every company on the 1st of each month, and a reset to check
 * everything again from nothing. */
export function MarketAuditPanel({ region = "IN" }: { region?: Region }) {
  const { fail } = useApp();
  const us = region === "US";
  const [m, setM] = useState<MarketState | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => { try { setM(await api<MarketState>(`/admin/audit/market?region=${region}`)); } catch (e) { fail(e); } }, [fail, region]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!m?.enabled) return;
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, [m?.enabled, load]);
  const send = async (body: object) => {
    setBusy(true);
    try { setM(await api<MarketState>("/admin/audit/market", { method: "POST", body: { region, ...body } })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const reset = () => {
    if (confirm(`Clear every stored result for ${us ? "the US" : "India"} and check all ${m?.listed.toLocaleString("en-IN") ?? ""} companies again from the start? `
      + "It takes a day or more, paced so the sources aren't asked too fast, and switches the check on.")) send({ reset: true });
  };
  const sum = m?.summary;
  const full = m?.full;
  const done = full?.running ? (full.checked ?? 0) : 0;
  const name = us ? "US" : "India";

  return (
    <section className="card stack" style={{ gap: 12 }} aria-label={`Whole market: ${name}`}>
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Whole market: {name}</h2>
        {m && (
          <div className="row" style={{ gap: 8, alignItems: "center" }}>
            <span className={`badge ${m.enabled ? (m.paused ? "paused" : "running") : "paused"}`}>{m.enabled ? (m.paused ? "Waiting" : "Running") : "Paused"}</span>
            <button className={`btn sm ${m.enabled ? "quiet" : "blue"}`} disabled={busy} onClick={() => send({ on: !m.enabled })}
              aria-label={m.enabled ? `Pause the ${name} check` : `Start the ${name} check`}>{m.enabled ? "Pause" : "Start"}</button>
          </div>
        )}
      </div>
      <p className="small muted" style={{ maxWidth: "80ch", margin: 0 }}>{us
        ? "Every company that files with the SEC (common stock only: preferred shares, warrants, units and rights are left out). The SEC's list is read once a day; new companies are checked as they appear."
        : "Every company listed in India: all of NSE, plus those listed only on BSE (shown as BSE: and their code). The lists are read once a day; new listings are checked as they appear and delisted companies drop off."}
        {" "}A full check of every company runs on the 1st of each month; between those, only new listings. A check a source turned away is tried again in small batches every hour.</p>
      {!m ? <p className="small muted">Loading…</p> : (
        <>
          <p className="small" style={{ margin: 0 }}>
            <b>{m.paused ? PAUSED[m.paused] : m.due ? `Running · ${m.due.toLocaleString("en-IN")} to check` : "Running · up to date"}</b>
            {m.paused === "cooling" && !!m.cool_minutes && ` (${m.cool_minutes} min between companies now)`}
            {" · "}{m.listed ? `${m.listed.toLocaleString("en-IN")} companies listed` : "list not read yet"}, {m.checked.toLocaleString("en-IN")} checked
            {m.current && <> · now <span className="mono">{m.current}</span></>}
          </p>
          {full?.running && (
            <div className="stack" style={{ gap: 6 }}>
              <p className="small" style={{ margin: 0 }}>{full.pending_only
                ? <><b>Re-checking companies not checked yet:</b> {full.left.toLocaleString("en-IN")} left</>
                : <><b>Full check:</b> {done.toLocaleString("en-IN")} of {m.listed.toLocaleString("en-IN")} done</>}
                {m.rate_per_hour ? ` · ${m.rate_per_hour.toLocaleString("en-IN")} an hour` : ""}
                {m.enabled && m.eta_hours != null && full.left > 0 && ` · ${hoursText(m.eta_hours)} left`}
                {full.since ? ` · started ${ago(full.since)}` : ""}
                {!m.enabled && " · paused: press Start to carry on"}</p>
              {!full.pending_only && m.listed > 0 && (
                <div role="progressbar" aria-label={`Full check ${name}`} aria-valuemin={0} aria-valuemax={m.listed} aria-valuenow={done}
                  style={{ height: 8, borderRadius: 999, background: "var(--chip)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.min(100, (done / m.listed) * 100)}%`, height: "100%", background: "var(--blue)" }} />
                </div>
              )}
            </div>
          )}
          {full && !full.running && full.done_at && <p className="small muted" style={{ margin: 0 }}>Last full check finished {ago(full.done_at)}.</p>}
          {!!m.bse?.waiting && (
            <p className="small" style={{ margin: 0 }}><span className="badge warn">BSE</span>{" "}
              {m.bse.refusing ? "BSE is refusing requests from this server; " : "Waiting for documents from BSE: "}
              {m.bse.waiting.toLocaleString("en-IN")} {m.bse.waiting === 1 ? "company" : "companies"} waiting. Companies also on NSE use NSE's filings.
              {m.retry?.next && new Date(m.retry.next).getTime() > Date.now() ? ` Next batch of ${m.retry.batch} ${until(m.retry.next)}.` : ` Retried ${m.retry?.batch ?? 20} at a time, every hour.`}</p>
          )}
          <div className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <button className="btn sm" disabled={busy} onClick={reset}>Reset and check everything again</button>
            {!full?.running && !!m.pending && <button className="btn quiet sm" disabled={busy} onClick={() => send({ retry: true })}>
              Re-check the {m.pending.toLocaleString("en-IN")} not checked yet</button>}
            <button className="btn quiet sm" disabled={busy} onClick={() => send({ read_list: true })}>Read the list now</button>
          </div>
          <div className="row small" style={{ gap: 10, flexWrap: "wrap", alignItems: "center" }}>
            <label className="row" style={{ gap: 6, minHeight: 32 }}>
              <input type="checkbox" checked={!!m.monthly?.on} disabled={busy} onChange={(e) => send({ monthly: e.target.checked })} />
              Full re-check on the 1st of each month
            </label>
            <span className="muted">{m.monthly?.on && m.monthly.next ? `Next full check: ${dayMonth(m.monthly.next)}` : "Only new listings, until you reset"}</span>
          </div>
          <p className="small muted" style={{ margin: 0 }}>
            {m.list_error ? <span className="neg">Couldn't read the exchange's list: {m.list_error}{m.list_at ? ` (using the one from ${ago(m.list_at)})` : ""}.</span>
              : m.list_at ? `List read ${ago(m.list_at)}.` : ""}
            {m.reset_at ? ` Results last reset ${ago(m.reset_at)}.` : ""}
          </p>
          {m.new_listings.length > 0 && (
            <p className="small" style={{ margin: 0 }}>New listings: {m.new_listings.slice(0, 12).map((n, i) => (
              <span key={n.symbol}>{i ? ", " : ""}<Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(n.symbol))}/deep`}>{n.symbol}</Link>
                <span className="muted">{n.listed ? ` (${n.listed})` : ""}{n.checked ? "" : " · queued"}</span></span>))}</p>
          )}
          {sum && sum.companies > 0 && (
            <>
              <p className="small" style={{ margin: 0 }}>{sum.companies.toLocaleString("en-IN")} checked, {sum.clean.toLocaleString("en-IN")} clean · <span className="neg">{count(sum.mismatches, "mismatch", "mismatches")}</span> · {tally(sum)}</p>
              <Findings rows={m.rows} sum={sum} running={m.enabled} file={`stratlab-${us ? "us" : "india"}-market-audit.csv`} region={region}
                onRecheck={(symbol) => send({ recheck: symbol })} />
            </>
          )}
        </>
      )}
    </section>
  );
}

/** The area table, the kind filter, each company's findings, and a CSV of every finding. */
function Findings({ rows: all, sum, running, file, region, onRecheck }: { rows: Row[]; sum: Summary; running: boolean; file: string; region: Region;
  /** the whole-market audit: check one company again now */ onRecheck?: (symbol: string) => Promise<void> }) {
  const [show, setShow] = useState<Level | "all">("mismatch");
  const [again, setAgain] = useState<string | null>(null);
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
          <thead><tr><th>Area</th><th className="num">Mismatches</th><th className="num">Gaps</th><th className="num">Errors</th><th className="num">Facts</th><th className="num">Not checked</th></tr></thead>
          <tbody>{Object.entries(sum.by_area).sort((a, b) => weight(b[1]) - weight(a[1])).map(([area, c]) => (
            <tr key={area}><td>{area}</td><td className="num">{c.mismatch ?? 0}</td><td className="num">{c.gap ?? 0}</td><td className="num">{c.error ?? 0}</td><td className="num">{c.fact ?? 0}</td><td className="num">{c.pending ?? 0}</td></tr>
          ))}</tbody>
        </table></div>
      )}
      <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
        <div className="seg" role="radiogroup" aria-label="Show">
          {(["mismatch", "error", "gap", "fact", "pending", "all"] as const).map((k) => (
            <button key={k} role="radio" aria-checked={show === k} aria-pressed={show === k} onClick={() => setShow(k)}>{SHOWS[k]}</button>
          ))}
        </div>
        {!!all.length && <button className="btn quiet sm" onClick={csv}>Download CSV</button>}
      </div>
      {rows.length === 0 ? <p className="small muted">Nothing of this kind{running ? " yet" : ""}.</p> : (
        <div className="stack" style={{ gap: 8 }}>
          {rows.length > SHOWN && <p className="small muted" style={{ margin: 0 }}>Showing {SHOWN} of {rows.length} companies; the CSV has all of them.</p>}
          {rows.slice(0, SHOWN).map((r) => (
            <div key={r.symbol} className="stack small" style={{ gap: 2 }}>
              <span className="row" style={{ gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                <span><Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(r.symbol))}/deep`}><b>{r.name}</b></Link> <span className="mono tiny muted">{r.symbol} · {r.seconds}s</span></span>
                {onRecheck && <button className="btn quiet sm" disabled={!!again} aria-label={`Re-check ${r.name}`}
                  onClick={async () => { setAgain(r.symbol); try { await onRecheck(r.symbol); } finally { setAgain(null); } }}>{again === r.symbol ? "Checking…" : "Re-check"}</button>}
              </span>
              {r.shown.map((i, n) => <span key={n}><span className={`badge ${LEVEL[i.level][1]}`}>{show === "all" && i.level !== "pending" ? `${LEVEL[i.level][0]}: ` : ""}{i.area}</span> {i.detail}</span>)}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
