import { useState, type FormEvent } from "react";
import { Dialog, Field, FormActions, FormGrid } from "./kit";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import type { StudentState } from "../lib/types";

/** The student price (the server's offers.STUDENT_PRICE) and its line on Plans; here, not in lib/founding.ts, so the landing page doesn't carry
 * them (review-r5's 450 KB). */
export const STUDENT_PRICE = 2499;
export function studentLine(price = STUDENT_PRICE): string {
  return `Student? Basic is ₹${price.toLocaleString("en-IN")} a year for students, approved by hand: send your college email or a note about your student ID.`;
}

/** price102 (owner, 28 Nov, GTM P3): "Student? Apply" on Plans. The request goes to the owner (Admin → Users, Student requests), who checks
 * the college email or the ID note by hand and approves Basic at the student price, or gives Basic for a year. Signed in only. */
export function StudentApply() {
  const { me, refreshMe, notify } = useApp();
  const [open, setOpen] = useState(false);
  const [college, setCollege] = useState("");
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!me) return null;
  const s: StudentState | null = me.student ?? null;
  if (s && s.status === "approved") {
    return <p className="k-small k-muted" data-testid="student-line">{s.mode === "grant"
      ? `Your student request was approved${s.decided_at ? ` on ${dateOnly(s.decided_at)}` : ""}: Basic is given to you for a year.`
      : s.price ? `Your student request was approved: Basic yearly is ₹${s.price.toLocaleString("en-IN")} for you. Pick Yearly above.`
        : "Your student request was approved. We'll write to you about paying the student price."}</p>;
  }
  if (s && s.status === "pending") {
    return <p className="k-small k-muted" data-testid="student-line">Your student request{s.at ? ` of ${dateOnly(s.at)}` : ""} is waiting for a check. We'll tell you when it's done.</p>;
  }
  const send = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      await api("/student/apply", { method: "POST", body: { college, college_email: email, note } });
      setOpen(false);
      notify("Request sent. We check it by hand and tell you when it's approved.");
      await refreshMe();
    } catch (x) { setError((x as Error).message || "The request couldn't be sent. Try again."); }
    finally { setBusy(false); }
  };
  return (
    <>
      <p className="k-small k-muted" data-testid="student-line">{s?.status === "rejected" ? "Your last student request wasn't approved. You can send a new one. " : ""}
        {studentLine(STUDENT_PRICE)} <button type="button" className="link" onClick={() => setOpen(true)} data-testid="student-apply">Apply</button></p>
      {open && (
        <Dialog title="Student price for Basic" onClose={() => setOpen(false)}>
          <FormGrid onSubmit={send} label="Student request" noValidate>
            <Field label="College or university" value={college} onChange={(e) => setCollege(e.target.value)} maxLength={120} wide required />
            <Field label="College email" type="email" optional value={email} onChange={(e) => setEmail(e.target.value)} maxLength={200} wide
              hint="An address your college gave you, ending in its own domain" />
            <Field label="Or a note about your student ID" optional value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} wide
              hint="Its number and the year it is valid to" error={error} />
            <FormActions>
              <button type="submit" className="btn" disabled={busy}>{busy ? "Sending…" : "Send the request"}</button>
              <button type="button" className="btn quiet" onClick={() => setOpen(false)}>Cancel</button>
            </FormActions>
          </FormGrid>
          <p className="k-note">Basic is ₹{STUDENT_PRICE.toLocaleString("en-IN")} a year for students. Nothing is charged until it's approved.</p>
        </Dialog>
      )}
    </>
  );
}
