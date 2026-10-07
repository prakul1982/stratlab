import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, fmtDate } from "../../lib/format";
import { Badge, Card, CardHead, CheckField, ChipBar, ConfirmDialog, DataTable, EmptyState, Field, FieldGroup, FormActions, Meter, Notice, Select, Skeleton, type Column } from "../../components/kit";

/** fact: true of the company (a recent listing, no calls held), not a gap of ours; pending: a source turned the check away, so it runs again. */
type Level = "mismatch" | "gap" | "error" | "fact" | "pending";
export type Region = "IN" | "US";
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
const LEVEL: Record<Level, [string, "warn" | "plain"]> = { mismatch: ["Mismatch", "warn"], error: ["Error", "warn"], gap: ["Gap", "plain"], fact: ["Fact", "plain"], pending: ["Not checked yet", "plain"] };
/** Which areas need a look first: mismatches, then errors, then gaps. */
const weight = (c: Partial<Record<Level, number>>) => (c.mismatch ?? 0) * 3 + (c.error ?? 0) * 2 + (c.gap ?? 0);
const SHOWS: Record<Level | "all", string> = { mismatch: "Mismatches", error: "Errors", gap: "Gaps", fact: "Facts", pending: "Not checked yet", all: "All" };
const count = (n: number, one: string, many: string) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;
const tally = (sum: Summary) => `${count(sum.gaps, "gap", "gaps")} · ${count(sum.errors, "error", "errors")}${sum.facts ? ` · ${count(sum.facts, "fact", "facts")}` : ""}${sum.pending ? ` · ${sum.pending.toLocaleString("en-IN")} not checked yet` : ""}`;

/** The data audit: every company in a set checked against its sources, on the live server. */
export function AuditPanel({ region }: { region: Region }) {
  const { fail } = useApp();
  const [s, setS] = useState<AuditState | null>(null);
  const [set, setSet] = useState(region === "US" ? "us_mega" : "nifty50");
  const [custom, setCustom] = useState("");
  const [docs, setDocs] = useState(false);

  const load = useCallback(async () => { try { setS(await api<AuditState>(`/admin/audit?region=${region}`)); } catch (e) { fail(e); } }, [fail, region]);
  useEffect(() => { setS(null); setSet(region === "US" ? "us_mega" : "nifty50"); load(); }, [load, region]);
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
    <Card label="Data audit">
      <CardHead title="Data audit" info="Runs every company in a set through the deep dive on this server: numbers, prices, industry, valuation, checklist and documents, each compared with its source. Mismatches are numbers that disagree with the source; gaps are things a user would still have to look up elsewhere. No AI is used. About 3 to 10 seconds a company." />
      {!s ? <Skeleton label="Loading the audit" lines={3} /> : (
        <>
          <form className="k-form" onSubmit={(e) => { e.preventDefault(); start(); }} aria-label="Run an audit">
            <Field label="Companies to check">{(id) => <Select id={id} value={set} onChange={setSet} disabled={s.running || !!custom.trim()} options={s.sets.map((x) => ({ value: x.id, label: `${x.name} (${x.count})` }))} />}</Field>
            <Field label="Or symbols" optional placeholder="INFY TITAN" value={custom} onChange={(e) => setCustom(e.target.value)} disabled={s.running} />
            {region === "IN" && <FieldGroup label="Documents" wide><CheckField label="Also try reading documents (slower)" checked={docs} onChange={setDocs} disabled={s.running} /></FieldGroup>}
            <FormActions>
              <button type="submit" className="btn sm" disabled={s.running}>{s.running ? `Checking ${s.done ?? 0} of ${s.total}…` : "Run audit"}</button>
              {s.running && <button type="button" className="btn quiet sm" onClick={stop}>Stop</button>}
            </FormActions>
          </form>
          {sum && s.label && (
            <>
              <p className="k-small"><b>{s.label}</b>{s.docs ? " with documents" : ""} · {s.running ? `started ${ago(s.started_at!)}` : s.finished_at ? `${s.cancelled ? "stopped" : "finished"} ${ago(s.finished_at)}` : ""}
                {" · "}{sum.companies} checked, {sum.clean} clean · <span className="k-down">{count(sum.mismatches, "mismatch", "mismatches")}</span> · {tally(sum)}
                {sum.avg_seconds != null && ` · ${sum.avg_seconds}s a company`}</p>
              <Findings rows={s.rows ?? []} sum={sum} running={s.running} file="stratlab-audit.csv" region={s.region ?? region} />
            </>
          )}
        </>
      )}
    </Card>
  );
}

interface MarketState {
  /** the stored results couldn't be read yet (just after a restart): nothing else is filled in */
  loading?: boolean; error?: string;
  enabled: boolean; listed: number; checked: number; due: number; current: string | null; eta_hours: number | null;
  /** why nothing is being checked: switched off, an audit above is running, market data offline, or a source is
   * turning every company away */
  paused?: "off" | "busy" | "offline" | "cooling" | "loading" | null; cool_minutes?: number; rate_per_hour?: number;
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
const dayMonth = (d: string) => fmtDate(d, { year: false });
/** "in 40 min", "in 3 h" for a time ahead. */
const until = (iso: string) => {
  const s = (new Date(iso).getTime() - Date.now()) / 1000;
  return s < 60 ? "any minute" : s < 3600 ? `in ${Math.round(s / 60)} min` : `in ${Math.round(s / 3600)} h`;
};
const hoursText = (h: number) => (h < 1 ? "under an hour" : h < 48 ? `about ${Math.round(h)} hours` : `about ${Math.round(h / 24)} days`);
const PAUSED: Record<"off" | "busy" | "offline" | "cooling" | "loading", string> = {
  loading: "Reading the stored results; nothing is checked or changed until they are.",
  off: "Paused: switched off. Press Start to check companies.",
  busy: "Paused: an audit above is running. It carries on by itself when that finishes.",
  offline: "Waiting: market data is offline until today's data login. It carries on by itself once prices are back.",
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
  const [asking, setAsking] = useState(false);
  const load = useCallback(async () => { try { setM(await api<MarketState>(`/admin/audit/market?region=${region}`)); } catch (e) { fail(e); } }, [fail, region]);
  useEffect(() => { setM(null); load(); }, [load]);
  useEffect(() => {
    if (!m?.enabled) return;
    const t = window.setInterval(load, 30000);
    return () => window.clearInterval(t);
  }, [m?.enabled, load]);
  const send = async (body: object) => {
    setBusy(true);
    try { setM(await api<MarketState>("/admin/audit/market", { method: "POST", body: { region, ...body } })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const sum = m?.summary;
  const full = m?.full;
  const done = full?.running ? (full.checked ?? 0) : 0;
  const name = us ? "US" : "India";

  return (
    <Card label={`Whole market: ${name}`}>
      <CardHead title={`Whole market: ${name}`}
        info={<>{us
          ? "Every company that files with the SEC (common stock only: preferred shares, warrants, units and rights are left out). The SEC's list is read once a day; new companies are checked as they appear."
          : "Every company listed in India: all of NSE, plus those listed only on BSE (shown as BSE: and their code). The lists are read once a day; new listings are checked as they appear and delisted companies drop off."}
          {" "}A full check of every company runs on the 1st of each month; between those, only new listings. A check a source turned away is tried again in small batches every hour.</>}
        actions={m && !m.loading ? (
          <>
            <Badge tone={m.enabled && !m.paused ? "live" : "warn"}>{m.enabled ? (m.paused ? "Waiting" : "Running") : "Paused"}</Badge>
            <button type="button" className={`btn sm${m.enabled ? " quiet" : ""}`} disabled={busy} onClick={() => send({ on: !m.enabled })}
              aria-label={m.enabled ? `Pause the ${name} check` : `Start the ${name} check`}>{m.enabled ? "Pause" : "Start"}</button>
          </>
        ) : undefined} />
      {!m ? <Skeleton label="Loading the whole-market check" lines={3} /> : m.loading ? (
        <p className="k-small k-muted" role="status">{m.error || "The stored results are being read. Nothing is checked or changed until they are."}</p>
      ) : (
        <>
          <p className="k-small">
            <b>{m.paused ? PAUSED[m.paused] : m.due ? `Running · ${m.due.toLocaleString("en-IN")} to check` : "Running · up to date"}</b>
            {m.paused === "cooling" && !!m.cool_minutes && ` ${m.cool_minutes} min between companies now.`}
            {/* a pause reason is a full sentence, so the counts start a new one rather than hang off a "." with a "·" */}
            {m.paused ? " " : " · "}{m.listed ? `${m.listed.toLocaleString("en-IN")} companies listed` : m.paused ? "List not read yet" : "list not read yet"}, {m.checked.toLocaleString("en-IN")} checked
            {m.current && <> · now <span className="adm-mono">{m.current}</span></>}
          </p>
          {full?.running && (
            <div className="k-stack">
              <p className="k-small">{full.pending_only
                ? <><b>Re-checking companies not checked yet:</b> {full.left.toLocaleString("en-IN")} left</>
                : <><b>Full check:</b> {done.toLocaleString("en-IN")} of {m.listed.toLocaleString("en-IN")} done</>}
                {m.rate_per_hour ? ` · ${m.rate_per_hour.toLocaleString("en-IN")} an hour` : ""}
                {/* no time left while it waits (switched off, an audit above, market data offline): nothing is moving */}
                {m.enabled && (!m.paused || m.paused === "cooling") && m.eta_hours != null && full.left > 0 && ` · ${hoursText(m.eta_hours)} left`}
                {full.since ? ` · started ${ago(full.since)}` : ""}
                {!m.enabled && " · paused: press Start to carry on"}</p>
              {!full.pending_only && m.listed > 0 && (
                <div role="progressbar" aria-label={`Full check ${name}`} aria-valuemin={0} aria-valuemax={m.listed} aria-valuenow={done}><Meter pct={(done / m.listed) * 100} /></div>
              )}
            </div>
          )}
          {full && !full.running && full.done_at && <p className="k-small k-muted">Last full check finished {ago(full.done_at)}.</p>}
          {!!m.bse?.waiting && (
            <Notice tone="warn">
              {m.bse.refusing ? "BSE is refusing requests from this server; " : "Waiting for documents from BSE: "}
              {m.bse.waiting.toLocaleString("en-IN")} {m.bse.waiting === 1 ? "company" : "companies"} waiting. Companies also on NSE use NSE's filings.
              {m.retry?.next && new Date(m.retry.next).getTime() > Date.now() ? ` Next batch of ${m.retry.batch} ${until(m.retry.next)}.` : ` Retried ${m.retry?.batch ?? 20} at a time, every hour.`}
            </Notice>
          )}
          <div className="k-row">
            <button type="button" className="btn sm" disabled={busy} onClick={() => setAsking(true)}>Reset and check everything again</button>
            {!full?.running && !!m.pending && <button type="button" className="btn quiet sm" disabled={busy} onClick={() => send({ retry: true })}>Re-check the {m.pending.toLocaleString("en-IN")} not checked yet</button>}
            <button type="button" className="btn quiet sm" disabled={busy} onClick={() => send({ read_list: true })}>Read the list now</button>
          </div>
          <div className="k-row">
            <CheckField label="Full re-check on the 1st of each month" checked={!!m.monthly?.on} disabled={busy} onChange={(on) => send({ monthly: on })} />
            <span className="k-small k-muted">{m.monthly?.on && m.monthly.next ? `Next full check: ${dayMonth(m.monthly.next)}` : "Only new listings, until you reset"}</span>
          </div>
          <p className="k-small k-muted">
            {m.list_error ? <span className="k-down">Couldn't read the exchange's list: {m.list_error}{m.list_at ? ` (using the one from ${ago(m.list_at)})` : ""}.</span>
              : m.list_at ? `List read ${ago(m.list_at)}.` : ""}
            {m.reset_at ? ` Results last reset ${ago(m.reset_at)}.` : ""}
          </p>
          {m.new_listings.length > 0 && (
            <p className="k-small">New listings: {m.new_listings.slice(0, 12).map((n, i) => (
              <span key={n.symbol}>{i ? ", " : ""}<Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(n.symbol))}/deep`}>{n.symbol}</Link>
                <span className="k-muted">{n.listed ? ` (${n.listed})` : ""}{n.checked ? "" : " · queued"}</span></span>))}</p>
          )}
          {sum && sum.companies > 0 && (
            <>
              <p className="k-small">{sum.companies.toLocaleString("en-IN")} checked, {sum.clean.toLocaleString("en-IN")} clean · <span className="k-down">{count(sum.mismatches, "mismatch", "mismatches")}</span> · {tally(sum)}</p>
              <Findings rows={m.rows} sum={sum} running={m.enabled} file={`stratlab-${us ? "us" : "india"}-market-audit.csv`} region={region}
                onRecheck={(symbol) => send({ recheck: symbol })} />
            </>
          )}
        </>
      )}
      {asking && (
        <ConfirmDialog title={`Check every ${name} company again?`} confirmLabel="Reset and check again" busy={busy} onClose={() => setAsking(false)}
          onConfirm={async () => { await send({ reset: true }); setAsking(false); }}>
          This clears every stored result for {us ? "the US" : "India"} and checks all {m?.listed.toLocaleString("en-IN") ?? ""} companies again from the start.
          It takes a day or more, paced so the sources aren't asked too fast, and switches the check on.
        </ConfirmDialog>
      )}
    </Card>
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
    // names and details come from the exchanges' feeds: a leading = + - @ (or tab/CR) would run as a spreadsheet
    // formula when the file is opened, so such a cell is written as text
    const cell = (x: unknown) => { const s = String(x ?? ""); return `"${(/^[=+\-@\t\r]/.test(s) ? "'" + s : s).replace(/"/g, '""')}"`; };
    for (const r of all) for (const i of r.issues) lines.push([r.symbol, r.name, i.level, i.area, i.detail].map(cell).join(","));
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = file; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  };
  const areas = Object.entries(sum.by_area).sort((a, b) => weight(b[1]) - weight(a[1]));
  const cols: Column<[string, Partial<Record<Level, number>>]>[] = [
    { key: "a", header: "Area", rowHeader: true, cell: ([a]) => a },
    { key: "m", header: "Mismatches", numeric: true, cell: ([, c]) => c.mismatch ?? 0 },
    { key: "g", header: "Gaps", numeric: true, cell: ([, c]) => c.gap ?? 0 },
    { key: "e", header: "Errors", numeric: true, cell: ([, c]) => c.error ?? 0 },
    { key: "f", header: "Facts", numeric: true, cell: ([, c]) => c.fact ?? 0 },
    { key: "p", header: "Not checked", numeric: true, cell: ([, c]) => c.pending ?? 0 },
  ];
  return (
    <>
      {areas.length > 0 && <DataTable label="Findings by area" rows={areas} rowKey={([a]) => a} columns={cols} />}
      <div className="k-toolbar">
        <ChipBar label="Show" value={show} onChange={(v) => setShow(v as Level | "all")}
          options={(["mismatch", "error", "gap", "fact", "pending", "all"] as const).map((k) => ({ value: k, label: SHOWS[k] }))} />
        {!!all.length && <button type="button" className="btn quiet sm" onClick={csv}>Download CSV</button>}
      </div>
      {rows.length === 0 ? <EmptyState title={`Nothing of this kind${running ? " yet" : ""}`}>Pick another kind above to see the rest.</EmptyState> : (
        <div className="k-stack">
          {rows.length > SHOWN && <p className="k-small k-muted">Showing {SHOWN} of {rows.length} companies; the CSV has all of them.</p>}
          {rows.slice(0, SHOWN).map((r) => (
            <div key={r.symbol} className="k-stack k-small">
              <span className="k-row">
                <span><Link className="link" to={`/research/${region}/${encodeURIComponent(pageSymbol(r.symbol))}/deep`}><b>{r.name}</b></Link> <span className="adm-mono k-muted">{r.symbol} · {r.seconds}s</span></span>
                {onRecheck && <button type="button" className="btn quiet sm" disabled={!!again} aria-label={`Re-check ${r.name}`}
                  onClick={async () => { setAgain(r.symbol); try { await onRecheck(r.symbol); } finally { setAgain(null); } }}>{again === r.symbol ? "Checking…" : "Re-check"}</button>}
              </span>
              {r.shown.map((i, n) => <span key={n}><Badge tone={LEVEL[i.level][1]} dot={false}>{show === "all" && i.level !== "pending" ? `${LEVEL[i.level][0]}: ` : ""}{i.area}</Badge> {i.detail}</span>)}
            </div>
          ))}
        </div>
      )}
    </>
  );
}
