import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";

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
  if (!r) return null;
  const label = Object.fromEntries(r.areas.map((a) => [a.area, a.label]));
  return (
    <section className="card stack" style={{ gap: 12 }} data-testid="rules-panel">
      <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
        <h2 className="h2">Rates and rules</h2>
        <button className="btn sm" disabled={busy === "run"} onClick={() => go("run", "/admin/rules/watch/run", "Sources read.")}>{busy === "run" ? "Reading the sources…" : "Read the sources now"}</button>
      </div>
      <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>Tax slabs, STT, exchange fees, interest rates and contract rules StratLab uses, with
        the day each area was last checked against its official source. An area needs a review after {r.stale_days} days, or when a day it is known to change
        has passed (1 April, each quarter's small-savings rates, the SEC's fiscal year). The official sources that can be read by a program are read every
        morning; a change is emailed to you and shown here. Nothing is applied by itself.</p>
      <p className="small" style={{ margin: 0 }}><span className={`badge ${r.check.state === "pass" ? "pass" : "warn"}`}>{r.check.state === "pass" ? "OK" : "Review"}</span> {r.check.detail}</p>

      <div className="table-wrap"><table>
        <thead><tr><th>Area</th><th>Last reviewed</th><th>Next known change</th><th>Status</th></tr></thead>
        <tbody>{r.areas.map((a) => (
          <tr key={a.area}>
            <td><b>{a.label}</b></td>
            <td>{dateOnly(a.reviewed)} <span className="muted">({a.days} days)</span></td>
            <td>{a.next ? <>{dateOnly(a.next.date)} <span className="muted">· {a.next.what}</span></> : "–"}</td>
            <td><span className={`badge ${a.due ? "warn" : "pass"}`}>{a.due ? "Review" : "OK"}</span>
              {a.passed.length > 0 && <span className="small muted"> since: {a.passed.map((p) => p.what).join("; ")}</span>}</td>
          </tr>))}</tbody>
      </table></div>

      <h3 className="h3" style={{ margin: "6px 0 0" }}>Official sources, read every morning{r.watch.last_run ? ` (last ${ago(r.watch.last_run)})` : ""}</h3>
      <div className="stack" style={{ gap: 8 }}>
        {r.watch.sources.map((s) => (
          <div key={s.id} className="stack" style={{ gap: 4 }}>
            <p className="row small" style={{ gap: 8, alignItems: "baseline", flexWrap: "wrap", margin: 0 }}>
              <span className={`badge ${s.pending ? "fail" : s.error ? "warn" : s.checked ? "pass" : "warn"}`}>{s.pending ? "Changed" : s.error ? "Unread" : s.checked ? "Same" : "Not read yet"}</span>
              <b>{s.name}</b>
              <span className="muted">{s.error ? `${s.error}${s.fails > 1 ? ` (${s.fails} days running)` : ""}` : s.shown ?? ""}{s.expected && !s.pending ? ` · StratLab uses ${s.expected}` : ""}</span>
              <a className="small" href={s.url} target="_blank" rel="noreferrer">Source</a>
            </p>
            {s.pending && (
              <div className="row small" style={{ gap: 8, flexWrap: "wrap", alignItems: "center", paddingLeft: 12 }}>
                <span>{s.pending.items ? s.pending.items.map((c) => `${c.date}: ${c.subject}`).join(" · ")
                  : `${s.pending.why}: now ${s.pending.now}${s.pending.uses ? `, StratLab uses ${s.pending.uses}` : s.pending.was ? `, was ${s.pending.was}` : ""}`} <span className="muted">({s.where}, {ago(s.pending.at)})</span></span>
                <button className="btn quiet sm" disabled={busy === s.id} onClick={() => go(s.id, `/admin/rules/watch/${s.id}/seen`, "Marked seen.")}>Mark seen</button>
              </div>
            )}
          </div>
        ))}
      </div>

      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Hide the rules" : `Show all ${r.rules.length} rules`}</button>
      {all && (
        <div className="table-wrap"><table>
          <thead><tr><th>Rule</th><th>Value</th><th>Since</th><th>Where</th><th>Source</th></tr></thead>
          <tbody>{r.rules.map((x) => (
            <tr key={x.id}>
              <td><b>{x.name}</b><br /><span className="tiny muted">{label[x.area]}</span></td>
              <td className="small">{x.value}</td>
              <td className="small">{x.since ? (x.since.length === 10 ? dateOnly(x.since) : x.since) : "–"}</td>
              <td className="tiny muted">{x.where}</td>
              <td className="tiny muted" style={{ wordBreak: "break-word" }}>{x.source}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </section>
  );
}
