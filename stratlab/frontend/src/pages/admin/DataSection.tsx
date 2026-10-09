import { useEffect, useState } from "react";
import { Modal } from "../../components/ui";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, plainDates } from "../../lib/format";
import { Card, CardHead, DataTable, Light, Skeleton, StatusList, StatusRow, type Column } from "../../components/kit";
import { useAdmin, type JobRow } from "./AdminContext";
import { services } from "./attention";
import { HolidaysPanel } from "./HolidaysPanel";
import { StoragePanel } from "./StoragePanel";

type Outcome = { at: string; text: string };

/** One line on what a "Run now" answered: the jobs' own answers differ, so only the facts they share are told. */
function outcome(label: string, r: unknown): string {
  const o = (r && typeof r === "object" ? r : {}) as Record<string, unknown>;
  if (o.started === false) return `${label}: it is already running.`;
  if (o.started === true) return `${label}: started in the background. The last-run time updates when it finishes.`;
  if (typeof o.etfs === "number") return `${label}: read ${o.etfs} ETFs.`;
  const problems = Array.isArray(o.problems) ? o.problems.length : 0;
  return `${label}: done${problems ? `, with ${problems} problem${problems === 1 ? "" : "s"} (see the log)` : ""}.`;
}

function JobLog({ job, mine, onClose }: { job: JobRow; mine: Outcome[]; onClose: () => void }) {
  return (
    <Modal title={`${job.name}: log`} onClose={onClose}>
      <div className="k-stack">
        <div className="k-rows">
          <div><span>Last run</span><b>{job.last_run ? `${ago(job.last_run)} (${dateOnly(job.last_run)})` : "Not yet"}</b></div>
          <div><span>Next run</span><b>{job.schedule || "–"}</b></div>
          <div><span>Status</span><b><Light state={job.state} /></b></div>
        </div>
        {job.error && <p className={`k-small ${job.state === "bad" ? "k-down" : ""}`} role="alert">Last problem: {job.error}</p>}
        {job.note && <p className="k-small k-muted">{job.note}</p>}
        <h3 className="adm-sub">What it reported</h3>
        {job.log.length ? <ul className="adm-log">{job.log.map((l, i) => <li key={i}>{plainDates(l)}</li>)}</ul> : <p className="k-small k-muted">Nothing besides the times above.</p>}
        {mine.length > 0 && <>
          <h3 className="adm-sub">Run from here, this visit</h3>
          <ul className="adm-log">{mine.map((m, i) => <li key={i}>{ago(m.at)}: {m.text}</li>)}</ul>
        </>}
      </div>
    </Modal>
  );
}

/** Admin → Data and jobs: each background job with its last run, its next run, a "Run now" button and its log; then the
 * India broker connection, exchange holidays and storage. */
export function DataSection() {
  const { fail, notify } = useApp();
  const { ov, setOv, jobs, reloadJobs, reload } = useAdmin();
  const [busy, setBusy] = useState<string | null>(null);
  const [log, setLog] = useState<string | null>(null);
  const [mine, setMine] = useState<Record<string, Outcome[]>>({});
  const [kite, setKite] = useState<string | null>(null);
  const running = !!jobs?.some((j) => j.running);
  useEffect(() => {
    if (!running) return;
    const t = window.setInterval(reloadJobs, 8000);
    return () => window.clearInterval(t);
  }, [running, reloadJobs]);

  const runJob = async (j: JobRow, label: string, path: string) => {
    setBusy(`${j.id}:${path}`);
    try {
      const r = await api<unknown>(path, { method: "POST" });
      const text = outcome(label === "Run now" || label === "Read now" ? j.name : `${j.name} (${label.replace(/^Run /, "")})`, r);
      setMine((m) => ({ ...m, [j.id]: [{ at: new Date().toISOString(), text }, ...(m[j.id] ?? [])].slice(0, 6) }));
      notify(text);
      await reloadJobs();
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const run = async (key: string, fn: () => Promise<void>) => { setKite(key); try { await fn(); } catch (e) { fail(e); } finally { setKite(null); } };
  const sv = ov?.server;
  const broker = services(ov).filter((s) => ["kite", "feed", "auto"].includes(s.key));     // the same lights as Overview's
  const kiteLogin = () => run("kite", async () => {
    const { url } = await api<{ url: string }>("/admin/kite/login-url", { method: "POST" });
    window.open(url, "_blank", "noopener");
    notify("Broker login opened in a new tab. Come back and refresh when it says it's saved.");
  });
  const autoLogin = () => run("auto", async () => {
    const r = await api<{ ok: boolean; message: string }>("/admin/kite/auto-login-now", { method: "POST" });
    notify(r.message); await reload();
  });

  const cols: Column<JobRow>[] = [
    { key: "job", header: "Job", rowHeader: true, wrap: true, cell: (j) => <span className="k-stack"><b>{j.name}</b><span className="k-note k-muted">Next run: {j.schedule || "–"}</span>{j.error && <span className={`k-note ${j.state === "bad" ? "k-down" : "k-muted"}`}>{j.error}</span>}</span> },
    { key: "state", header: "Status", cell: (j) => <Light state={j.state} word={j.running ? "Running" : undefined} /> },
    { key: "last", header: "Last run", cell: (j) => (j.last_run ? ago(j.last_run) : <span className="k-muted">Not yet</span>) },
    { key: "do", header: <span className="sr-only">Run now and log</span>, action: true, cell: (j) => (
      <span className="k-row">
        {j.run.map((r) => (
          <button key={r.path} type="button" className="btn sm" disabled={j.running || busy === `${j.id}:${r.path}`} onClick={() => runJob(j, r.label, r.path)}
            aria-label={`${r.label}: ${j.name}`}>{busy === `${j.id}:${r.path}` ? "Running…" : r.label}</button>
        ))}
        <button type="button" className="btn quiet sm" onClick={() => setLog(j.id)} aria-label={`Log of ${j.name}`}>Log</button>
      </span>) },
  ];
  const open = jobs?.find((j) => j.id === log) ?? null;

  return (
    <>
      <Card label="Background jobs">
        <CardHead title="Background jobs" info="Each job runs on its own clock; Next run says when. Run now starts it at once where the job has a manual trigger (a job without a button runs on its clock only). A job that reads from the exchange can take a minute or two." />
        {!jobs ? <Skeleton label="Loading the jobs" /> : <DataTable label="Background jobs" rows={jobs} rowKey={(j) => j.id} columns={cols} />}
      </Card>

      <Card label="India broker data">
        <CardHead title="India broker data" info="Indian prices, paper trading and the market breadth for India need the broker's login each day." />
        {!sv ? <Skeleton label="Loading" lines={2} /> : (
          <>
            <StatusList label="India broker data">
              {broker.map((s) => <StatusRow key={s.key} state={s.state} label={s.label} detail={s.fix ?? s.detail} />)}
            </StatusList>
            <div className="k-row">
              <button type="button" className="btn sm" disabled={kite === "kite"} onClick={kiteLogin}>Log in to the broker</button>
              {sv.auto_login_configured && <button type="button" className="btn quiet sm" disabled={kite === "auto"} onClick={autoLogin}>{kite === "auto" ? "Logging in…" : "Run the automatic login now"}</button>}
            </div>
          </>
        )}
      </Card>

      {sv?.calendar && <HolidaysPanel status={sv.calendar} onSaved={(c) => setOv((o) => o && { ...o, server: { ...o.server, calendar: c } })} />}
      <StoragePanel />
      {open && <JobLog job={open} mine={mine[open.id] ?? []} onClose={() => setLog(null)} />}
    </>
  );
}
