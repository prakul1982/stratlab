import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly } from "../../lib/format";
import { endsAt } from "../../lib/offer";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, ErrorState, Field, FormGrid, Skeleton, type Column } from "../../components/kit";

/* price102 (owner, 28 Nov: "all ok to do", GTM P1 and P3): the founding-member yearly prices and the student price. The server is
 * backend/app/offers.py; this panel sets the three Razorpay plans those prices are charged on, says whether the founding offer is
 * running (and why not), and lists the student requests to approve. */

type OfferPlan = { field: string; label: string; id: string | null; amount: number };
type Student = { uid: string; email: string | null; college: string; college_email: string; note: string; at: string;
  status: "pending" | "approved" | "rejected"; mode?: "price" | "grant" | null; decided_at?: string | null };
export type OffersView = { plans: OfferPlan[]; student_price: number; students: Student[];
  founding: { until: string; seats: number; paying: number | null; prices: { basic: number; pro: number }; ready: boolean; payments: boolean;
    closed: "date" | "seats" | null; open: boolean } };

const rupee = (v: number) => `₹${v.toLocaleString("en-IN")}`;
/** A plan box's label on one line (the amount goes under the box). */
const SHORT: Record<string, string> = { founding_basic_year: "Founding Basic plan ID", founding_pro_year: "Founding Pro plan ID", student_basic_year: "Student Basic plan ID" };

/** Why the founding prices are or aren't on the pages, in one line. */
export function foundingState(f: OffersView["founding"]): { tone: "ok" | "warn"; text: string } {
  if (f.open) return { tone: "ok", text: `Running: shown on Plans and the landing page until ${endsAt(f.until)} or the ${f.seats}th paying customer.` };
  if (f.closed === "date") return { tone: "warn", text: `Ended at ${endsAt(f.until)}. Founding members keep their price on renewal.` };
  if (f.closed === "seats") return { tone: "warn", text: `Ended: ${f.seats} paying customers reached. Founding members keep their price on renewal.` };
  if (!f.payments) return { tone: "warn", text: "Not shown: payments aren't set up on the server." };
  return { tone: "warn", text: "Not shown yet: set both founding plans below (make them here, or paste their IDs from the Razorpay dashboard)." };
}

/** Admin → Money: the offer plans and the founding offer's state. */
export function OffersPanel() {
  const { fail, notify } = useApp();
  const [v, setV] = useState<OffersView | null>(null);
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);
  const [edit, setEdit] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [ask, setAsk] = useState(false);
  useEffect(() => { setFailed(false); api<OffersView>("/admin/offers").then(setV).catch((e) => { setFailed(true); fail(e); }); }, [fail, tries]);
  if (!v) return <Card label="Founding-member and student prices">{failed ? <ErrorState title="The offers couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }} /> : <Skeleton label="Loading the offers" lines={3} />}</Card>;
  const save = async () => {
    setBusy(true);
    try { setV(await api<OffersView>("/admin/offers/plans", { method: "PUT", body: edit })); setEdit({}); notify("Offer plans saved."); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const make = async () => {
    setAsk(false); setBusy(true);
    try {
      const out = await api<OffersView & { made: Record<string, string>; error?: string }>("/admin/offers/razorpay-plans", { method: "POST" });
      setV(out);
      const n = Object.keys(out.made).length;
      if (out.error) fail(new Error(`Razorpay refused${n ? ` after ${n} made` : ""}: ${out.error}`));
      else notify(n ? `${n} plan${n === 1 ? "" : "s"} made at Razorpay and saved.` : "Every offer plan was already set.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const f = v.founding, state = foundingState(f);
  const missing = v.plans.filter((p) => !p.id);
  return (
    <Card label="Founding-member and student prices" testId="offers-panel">
      <CardHead title="Founding-member and student prices"
        info={<>Founding members pay {rupee(f.prices.basic)} (Basic) or {rupee(f.prices.pro)} (Pro) a year until {endsAt(f.until)} or the first {f.seats} paying customers, whichever comes first, and keep that price for as long as their subscription renews (each is on its own Razorpay plan). Approved students pay {rupee(v.student_price)} a year for Basic. Monthly prices don't change. The prices include GST, like every rupee price.</>}
        actions={<>
          <button type="button" className="btn quiet sm" disabled={busy || !missing.length} onClick={() => setAsk(true)}>Make the offer plans</button>
          <button type="button" className="btn sm" disabled={busy || !Object.keys(edit).length} onClick={save}>{busy ? "Saving…" : "Save plan IDs"}</button>
        </>} />
      <p className="k-small" data-testid="founding-state"><Badge tone={state.tone} dot={false}>{f.open ? "Founding offer on" : "Founding offer off"}</Badge> {state.text}
        {f.paying != null && ` Paying customers so far: ${f.paying} of ${f.seats}.`}</p>
      <FormGrid label="Offer plan IDs">
        {v.plans.map((p) => (
          <Field key={p.field} label={SHORT[p.field] ?? p.label} hint={`${rupee(p.amount)} a year, in rupees`} value={edit[p.field] ?? p.id ?? ""} placeholder="plan_…"
            onChange={(e) => setEdit((x) => ({ ...x, [p.field]: e.target.value }))} />
        ))}
      </FormGrid>
      <p className="k-note k-muted">Each plan is in rupees, renews every year, at the amount beside it. Empty a box and save to clear it (a Railway variable, if set, is used then).</p>
      {ask && (
        <ConfirmDialog title="Make the offer plans at Razorpay?" confirmLabel={`Make ${missing.length} plan${missing.length === 1 ? "" : "s"}`} danger={false}
          onClose={() => setAsk(false)} onConfirm={() => void make()}>
          This makes {missing.map((p) => `${p.label} at ${rupee(p.amount)} a year`).join(", ")} in your Razorpay account with the server's key, and saves their IDs here. Nothing is charged; the founding prices show on the pages once both founding plans are set.
        </ConfirmDialog>
      )}
    </Card>
  );
}

/** Admin → Users: student requests for Basic at the student price. Approve at the price (their Basic yearly checkout is at it), give Basic for
 * a year by hand, or turn it down. */
export function StudentRequests() {
  const { fail, notify } = useApp();
  const [rows, setRows] = useState<Student[] | null>(null);
  const [price, setPrice] = useState(2499);
  const [priced, setPriced] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    setFailed(false);
    api<OffersView>("/admin/offers").then((v) => { setRows(v.students); setPrice(v.student_price); setPriced(!!v.plans.find((p) => p.field === "student_basic_year")?.id); })
      .catch((e) => { setFailed(true); fail(e); });
  }, [fail, tries]);
  const decide = async (s: Student, decision: "price" | "grant" | "reject") => {
    setBusy(s.uid);
    try {
      const out = await api<{ students: Student[] }>(`/admin/students/${encodeURIComponent(s.uid)}`, { method: "POST", body: { decision } });
      setRows(out.students);
      notify(decision === "reject" ? "Turned down." : decision === "grant" ? "Approved: Basic is given for a year." : `Approved: their Basic yearly checkout is ${rupee(price)}.`);
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  if (!rows) return <Card label="Student requests">{failed ? <ErrorState title="Student requests couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }} /> : <Skeleton label="Loading student requests" lines={2} />}</Card>;
  const pending = rows.filter((r) => r.status === "pending");
  const cols: Column<Student>[] = [
    { key: "who", header: "Account", rowHeader: true, wrap: true, cell: (r) => r.email ?? r.uid },
    { key: "college", header: "College", wrap: true, cell: (r) => r.college },
    { key: "proof", header: "College email or ID note", wrap: true, cell: (r) => r.college_email || r.note },
    { key: "at", header: "Sent", cell: (r) => dateOnly(r.at) },
    { key: "status", header: "Status", cell: (r) => r.status === "pending" ? "Waiting" : r.status === "rejected" ? "Turned down"
      : r.mode === "grant" ? "Basic given for a year" : `Approved at ${rupee(price)}` },
    { key: "do", header: <span className="sr-only">Decide</span>, action: true, cell: (r) => r.status !== "pending" ? null : (
      <span className="k-row">
        <button type="button" className="btn quiet sm" disabled={busy === r.uid || !priced} title={priced ? undefined : "Set the student plan in Admin → Money first"} onClick={() => decide(r, "price")}>Approve at {rupee(price)}</button>
        <button type="button" className="btn quiet sm" disabled={busy === r.uid} onClick={() => decide(r, "grant")}>Give Basic for a year</button>
        <button type="button" className="btn quiet sm danger" disabled={busy === r.uid} onClick={() => decide(r, "reject")}>Turn down</button>
      </span>) },
  ];
  return (
    <Card testId="student-requests" label="Student requests">
      <CardHead title="Student requests" info={`Students ask for Basic at ${rupee(price)} a year from Plans, with a college email or a note about their student ID. Check it, then approve at the student price (their Basic yearly checkout is at it; needs the student plan in Admin → Money), give Basic for a year by hand (nothing is charged in the app), or turn it down.`}
        actions={<span className="k-small k-muted">{pending.length} waiting</span>} />
      {!rows.length ? <p className="k-small k-muted" data-testid="students-none">No student requests yet.</p>
        : <DataTable label="Student requests" rows={rows.slice(0, 100)} rowKey={(r) => r.uid} columns={cols} />}
      {!priced && <p className="k-note k-muted">The student plan isn't set yet (Admin → Money), so approving at the price is off; giving Basic for a year by hand works.</p>}
    </Card>
  );
}
