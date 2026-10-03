import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago } from "../lib/format";

type Email = { kind: string; name: string; transactional: boolean };
type List = { emails: Email[]; job: { last_run: string | null; sent: number; last_error: string | null }; email_ready: boolean };
type Preview = { subject: string; html: string; text: string; transactional: boolean };

/** Admin → Services: each lifecycle email (welcome, day 2, trial and offer reminders, what's new, receipts) previewed
 *  with made-up details, or sent to the admin's own address as a test, like the test email above it. */
export function LifecycleEmails() {
  const { notify, fail } = useApp();
  const [list, setList] = useState<List | null>(null);
  const [kind, setKind] = useState("welcome");
  const [shown, setShown] = useState<Preview | null>(null);
  const [busy, setBusy] = useState<"preview" | "test" | null>(null);

  useEffect(() => {
    let live = true;
    api<List>("/admin/lifecycle").then((l) => { if (live && l && Array.isArray(l.emails)) setList(l); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (!list) return null;

  const run = async (what: "preview" | "test") => {
    setBusy(what);
    try {
      if (what === "preview") setShown(await api<Preview>(`/admin/lifecycle/${kind}/preview`, { method: "POST" }));
      else {
        const r = await api<{ sent_to: string; subject: string }>(`/admin/lifecycle/${kind}/test`, { method: "POST" });
        notify(`"${r.subject}" sent to ${r.sent_to}. Check your inbox (and spam).`);
      }
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const job = list.job;
  return (
    <div className="stack" style={{ gap: 8, marginTop: 14 }}>
      <h3 style={{ fontSize: 15, margin: 0 }}>Lifecycle emails</h3>
      <p className="small muted" style={{ margin: 0 }}>
        Sent once per user, hourly from 8 am to 9 pm IST{job.last_run ? `; last sweep ${ago(job.last_run)}, ${job.sent} sent` : ""}.
        {job.last_error ? ` Last problem: ${job.last_error}` : ""} Users turn off tips and reminders in Account; receipts always go.
      </p>
      <div className="row wrap" style={{ gap: 8 }}>
        <select aria-label="Lifecycle email" value={kind} onChange={(e) => { setKind(e.target.value); setShown(null); }} style={{ minHeight: 36, maxWidth: "100%" }}>
          {list.emails.map((m) => <option key={m.kind} value={m.kind}>{m.name}{m.transactional ? " (always sent)" : ""}</option>)}
        </select>
        <button className="btn quiet sm" disabled={!!busy} onClick={() => run("preview")}>{busy === "preview" ? "Building…" : "Preview"}</button>
        {list.email_ready && <button className="btn quiet sm" disabled={!!busy} onClick={() => run("test")}>{busy === "test" ? "Sending…" : "Send me a test"}</button>}
      </div>
      {shown && (
        <div className="stack" style={{ gap: 6 }}>
          <span className="small"><b>Subject:</b> {shown.subject}</span>
          <iframe className="mail-preview" title={`Preview: ${shown.subject}`} sandbox="" srcDoc={shown.html} />
        </div>
      )}
    </div>
  );
}
