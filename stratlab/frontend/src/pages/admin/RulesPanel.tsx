import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly } from "../../lib/format";
import { Card, CardHead, DataTable, Light, Skeleton, type Column } from "../../components/kit";

type Rule = { id: string; area: string; name: string; value: string; where: string; source: string; since: string | null };
type Area = { area: string; label: string; reviewed: string; days: number; due: boolean; passed: { date: string; what: string }[]; next: { date: string; what: string } | null };
type Pending = { at: string; why: string; was?: string | null; now?: string; uses?: string | null; items?: { date: string; subject: string; url: string }[] };
type Source = { id: string; name: string; area: string; url: string; where: string; checked: string | null; shown: string | null;
  expected: string | null; error: string | null; fails: number; pending: Pending | null };
type Rules = { rules: Rule[]; areas: Area[]; stale_days: number; watch: { sources: Source[]; last_run: string | null };
  check: { state: "pass" | "warn"; detail: string } };

/** Every hard-coded rate and rule, when each area was last checked against its official source, and what the daily
 * watch of those sources found. Nothing changes by itself: a change is made in the code and marked seen here. */
export function RulesPanel() {
  const { fail, notify } = useApp();
  const [r, setR] = useState<Rules | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  useEffect(() => { api<Rules>("/admin/rules").then(setR).catch(() => {}); }, []);
  const go = async (key: string, path: string, done?: string) => {
    setBusy(key);
    try { setR(await api<Rules>(path, { method: "POST" })); if (done) notify(done); } catch (e) { fail(e); } finally { setBusy(null); }
  };
  if (!r) return <Card label="Rates and rules"><Skeleton label="Loading the rates and rules" /></Card>;
  const label = Object.fromEntries(r.areas.map((a) => [a.area, a.label]));
  const areas: Column<Area>[] = [
    { key: "a", header: "Area", rowHeader: true, cell: (a) => a.label },
    { key: "r", header: "Last reviewed", cell: (a) => <>{dateOnly(a.reviewed)} <span className="k-muted">({a.days} days)</span></> },
    { key: "n", header: "Next known change", wrap: true, cell: (a) => (a.next ? <>{dateOnly(a.next.date)} <span className="k-muted">· {a.next.what}</span></> : "–") },
    { key: "s", header: "Status", wrap: true, cell: (a) => (
      <span className="k-stack"><Light state={a.due ? "warn" : "ok"} word={a.due ? "Review" : "OK"} />
        {a.passed.length > 0 && <span className="k-note k-muted">since: {a.passed.map((p) => p.what).join("; ")}</span>}</span>) },
  ];
  const rules: Column<Rule>[] = [
    { key: "n", header: "Rule", rowHeader: true, wrap: true, cell: (x) => <span className="k-stack"><b>{x.name}</b><span className="k-note k-muted">{label[x.area]}</span></span> },
    { key: "v", header: "Value", wrap: true, cell: (x) => x.value },
    { key: "s", header: "Since", cell: (x) => (x.since ? (x.since.length === 10 ? dateOnly(x.since) : x.since) : "–") },
    { key: "w", header: "Where", wrap: true, cell: (x) => <span className="k-note k-muted">{x.where}</span> },
    { key: "so", header: "Source", wrap: true, cell: (x) => <span className="k-note k-muted adm-cell">{x.source}</span> },
  ];
  return (
    <Card testId="rules-panel" label="Rates and rules">
      <CardHead title="Rates and rules"
        info={`Tax slabs, STT, exchange fees, interest rates and contract rules StratLab uses, with the day each area was last checked against its official source. An area needs a review after ${r.stale_days} days, or when a day it is known to change has passed (1 April, each quarter's small-savings rates, the SEC's fiscal year). The official sources that can be read by a program are read every morning; a change is emailed to you and shown here. Nothing is applied by itself.`}
        actions={<button type="button" className="btn sm" disabled={busy === "run"} onClick={() => go("run", "/admin/rules/watch/run", "Sources read.")}>{busy === "run" ? "Reading the sources…" : "Read the sources now"}</button>} />
      <p className="k-small"><Light state={r.check.state === "pass" ? "ok" : "warn"} word={r.check.state === "pass" ? "OK" : "Review"} /> {r.check.detail}</p>
      <DataTable label="Rule areas" rows={r.areas} rowKey={(a) => a.area} columns={areas} />

      <h3 className="adm-sub">Official sources, read every morning{r.watch.last_run ? ` (last ${ago(r.watch.last_run)})` : ""}</h3>
      <div className="k-stack">
        {r.watch.sources.map((s) => (
          <div key={s.id} className="k-stack">
            <p className="k-row k-small">
              <Light state={s.pending ? "bad" : s.error ? "warn" : s.checked ? "ok" : "warn"} word={s.pending ? "Changed" : s.error ? "Unread" : s.checked ? "Same" : "Not read yet"} />
              <b>{s.name}</b>
              <span className="k-muted">{s.error ? `${s.error}${s.fails > 1 ? ` (${s.fails} days running)` : ""}` : s.shown ?? ""}{s.expected && !s.pending ? ` · StratLab uses ${s.expected}` : ""}</span>
              <a className="link" href={s.url} target="_blank" rel="noreferrer">Source</a>
            </p>
            {s.pending && (
              <div className="k-row k-small">
                <span>{s.pending.items ? s.pending.items.map((c) => `${c.date}: ${c.subject}`).join(" · ")
                  : `${s.pending.why}: now ${s.pending.now}${s.pending.uses ? `, StratLab uses ${s.pending.uses}` : s.pending.was ? `, was ${s.pending.was}` : ""}`} <span className="k-muted">({s.where}, {ago(s.pending.at)})</span></span>
                <button type="button" className="btn quiet sm" disabled={busy === s.id} onClick={() => go(s.id, `/admin/rules/watch/${s.id}/seen`, "Marked seen.")}>Mark seen</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="k-row"><button type="button" className="btn quiet sm" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Hide the rules" : `Show all ${r.rules.length} rules`}</button></div>
      {all && <DataTable label="All rules" rows={r.rules} rowKey={(x) => x.id} columns={rules} />}
    </Card>
  );
}
