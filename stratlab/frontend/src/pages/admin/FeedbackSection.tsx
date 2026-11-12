import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { fmtDateTime, IST } from "../../lib/format";
import { ADMIN_TYPES, type FeedbackRow } from "../../lib/feedback";
import { Card, CardHead, DataTable, EmptyState, Select, Skeleton, type Column } from "../../components/kit";
import { useAdmin } from "./AdminContext";

const TYPE_NAME = Object.fromEntries(ADMIN_TYPES) as Record<string, string>;
const STATUS: [FeedbackRow["status"], string][] = [["new", "New"], ["seen", "Seen"], ["fixed", "Fixed"]];

/** Admin → Feedback: every Help & feedback report, newest first, filtered by type and status, each one's status set here
 * (owner, 4 Nov). The reply address shows only where the person asked for a reply. */
export function FeedbackSection() {
  const { fail } = useApp();
  const { reload } = useAdmin();
  const [rows, setRows] = useState<FeedbackRow[] | null>(null);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const [again, setAgain] = useState(0);
  useEffect(() => {
    let live = true;
    api<{ rows: FeedbackRow[]; counts: Record<string, number> }>(`/admin/feedback?${new URLSearchParams({ type, status })}`)
      .then((r) => { if (live) { setRows(r.rows); setCounts(r.counts); } }).catch((e) => { if (live) { setRows([]); fail(e); } });
    return () => { live = false; };
  }, [type, status, again, fail]);
  const mark = async (r: FeedbackRow, to: FeedbackRow["status"]) => {
    try {
      await api(`/admin/feedback/${r.id}`, { method: "PUT", body: { status: to } });
      setAgain((n) => n + 1);
      void reload();          // the count in "Needs your attention"
    } catch (e) { fail(e); }
  };
  const cols: Column<FeedbackRow>[] = [
    { key: "at", header: "When", cell: (r) => fmtDateTime(r.at, { zone: true, tz: IST }) },
    { key: "type", header: "Type", cell: (r) => TYPE_NAME[r.type] ?? r.type },
    { key: "text", header: "What they wrote", rowHeader: true, wrap: true, lead: true, cell: (r) => (
      <span className="k-stack k-tight">
        {/* a data error's figure first, as the page showed it (owner, 12 Nov) */}
        {r.figure && <span className="adm-break" data-testid="feedback-figure"><b>{r.figure.label}</b>{r.figure.period ? `, ${r.figure.period}` : ""}{r.figure.value ? `: ${r.figure.value}` : ""}
          {r.figure.section ? <span className="k-note k-muted"> · {r.figure.section}</span> : null}{r.figure.source ? <span className="k-note k-muted"> · Source: {r.figure.source}</span> : null}</span>}
        <span className="adm-break">{r.text}</span>
        <span className="k-note k-muted">{[r.browser, r.screen, r.version && `build ${r.version}`].filter(Boolean).join(" · ")}</span></span>) },
    { key: "page", header: "Page", wrap: true, cell: (r) => <span className="adm-mono adm-break">{r.path}</span> },
    { key: "plan", header: "Plan", cell: (r) => (r.signed_in ? r.plan.replace(/^./, (c) => c.toUpperCase()) : "Signed out") },
    { key: "reply", header: "Reply wanted", wrap: true, cell: (r) => (r.reply ? <span className="adm-break">Yes{r.reply_to ? `: ${r.reply_to}` : ""}</span> : "No") },
    { key: "status", header: "Status", action: true, cell: (r) => (<>
      <Select label={`Status of the report from ${fmtDateTime(r.at, { tz: IST })}`} small value={r.status} onChange={(v) => { void mark(r, v as FeedbackRow["status"]); }}
        options={STATUS.map(([value, label]) => ({ value, label }))} />
      {r.type === "data_error" && r.status === "fixed" && r.noted && <span className="k-note k-muted">Reporter told</span>}</>) },
  ];
  return (
    <Card label="Feedback inbox">
      <CardHead title={`Feedback (${counts.new ?? 0} new, ${counts.seen ?? 0} seen, ${counts.fixed ?? 0} fixed)`}
        info="Reports from the Feedback button, and data errors sent from the flag beside a figure (with the figure as the page showed it): the page, the app's version, the browser and screen size and the plan come with each. Nothing else about the person is kept, and a reply address only when they asked for a reply. Marking a data error Fixed sends its reporter a one-line note in the app (and an email if they get alert emails)." />
      <div className="k-toolbar">
        <Select label="Type" value={type} onChange={setType} options={[{ value: "", label: "Every type" }, ...ADMIN_TYPES.map(([value, label]) => ({ value, label }))]} />
        <Select label="Status" value={status} onChange={setStatus} options={[{ value: "", label: "Every status" }, ...STATUS.map(([value, label]) => ({ value, label }))]} />
      </div>
      {rows === null ? <Skeleton label="Loading the feedback" lines={3} />
        : !rows.length ? <EmptyState title={type || status ? "No reports match" : "No feedback yet"}>Reports sent from the Feedback button show here, newest first.</EmptyState>
          : <DataTable label="Feedback reports" rows={rows} rowKey={(r) => r.id} columns={cols} stack />}
    </Card>
  );
}
