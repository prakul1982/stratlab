import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly } from "../../lib/format";
import { Modal } from "../../components/ui";
import { Badge, Field, FigureTable, FieldGroup, FormActions, FormGrid, Notice, Seg } from "../../components/kit";
import type { Plan } from "./AdminContext";
import { confirmMatches, confirmWord, PLAN_NAME, planNote, type UserRow } from "./users";

const DURATIONS = [{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "1 year" }, { value: "none", label: "No end date" }];

/** One user, opened from the row's "…" button: their facts, then Change plan, Delete data or Delete user, each in this same box.
 * Deleting asks for the email typed in (never the browser's own box). */
export function UserDialog({ user, onClose, onChanged }: { user: UserRow; onClose: () => void; onChanged: () => void }) {
  const [step, setStep] = useState<"menu" | "plan" | "erase" | "delete">("menu");
  const who = user.email ?? "this user";
  return (
    <Modal title={step === "plan" ? `Change plan: ${who}` : step === "erase" ? `Delete the data of ${who}?` : step === "delete" ? `Delete the user ${who}?` : who} onClose={onClose}>
      {step === "menu" && (
        <div className="k-stack">
          <FigureTable label={`${who}: account`} header="Account" valueHeader="Value" noteHeader={null} rows={[
            { key: "plan", label: "Plan", value: <Badge tone={user.plan === "free" ? "plain" : "ok"} dot={false}>{PLAN_NAME[user.plan]}</Badge> },
            ...(user.plan !== "free" ? [{ key: "how", label: "How", value: planNote(user) }] : []),
            { key: "joined", label: "Joined", value: dateOnly(user.created_at) },
            { key: "exp", label: "Experiments this month", value: user.experiments },
            { key: "ai", label: "AI builds this month", value: user.ai_builds },
            { key: "inv", label: "Invited", value: user.referrals ?? 0 },
          ]} />
          <div className="k-row">
            <button type="button" className="btn outline" onClick={() => setStep("plan")}>Change plan</button>
            <button type="button" className="btn quiet danger" onClick={() => setStep("erase")}>Delete data…</button>
            {/* owner, 7 Nov: "can you give a option to delete user" */}
            {user.email && <button type="button" className="btn quiet danger" onClick={() => setStep("delete")}>Delete user…</button>}
          </div>
        </div>
      )}
      {step === "plan" && <PlanForm user={user} onBack={() => setStep("menu")} onSaved={() => { onChanged(); onClose(); }} />}
      {step === "erase" && <EraseForm user={user} onBack={() => setStep("menu")} onDone={onClose} />}
      {step === "delete" && <DeleteUserForm user={user} onBack={() => setStep("menu")} onDone={() => { onChanged(); onClose(); }} />}
    </Modal>
  );
}

/** The server's own refusal (admin.set_plan), said before Save so the button isn't offered. */
export const PAYS_RAZORPAY = "Cancel their subscription in Razorpay first, then change the plan.";

function PlanForm({ user, onBack, onSaved }: { user: UserRow; onBack: () => void; onSaved: () => void }) {
  const { notify, fail } = useApp();
  const [plan, setPlan] = useState<Plan>(user.plan === "free" ? "basic" : user.plan);
  const [days, setDays] = useState("30");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    const n = days === "none" ? null : Number(days);
    setBusy(true);
    try {
      await api(`/admin/users/${user.id}/plan`, { method: "POST", body: { plan, days: plan === "free" ? null : n } });
      notify(plan === "free" ? `${user.email} is back on Free.` : `${user.email} now has ${PLAN_NAME[plan]}${n ? ` for ${n} days` : ""}.`);
      onSaved();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <div className="k-stack">
      <p className="k-small k-muted">Now on <b>{PLAN_NAME[user.plan]}</b>{user.plan !== "free" ? ` (${planNote(user)})` : ""}.</p>
      {user.paying && <Notice tone="warn">{PAYS_RAZORPAY}</Notice>}
      <FormGrid label="Change plan" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <FieldGroup label="Plan" wide><Seg label="Plan" value={plan} onChange={(v) => setPlan(v as Plan)} options={(["free", "basic", "pro"] as Plan[]).map((p) => ({ value: p, label: PLAN_NAME[p] }))} /></FieldGroup>
        {plan !== "free" && (
          <FieldGroup label="For how long" info="When it ends, they go back to Free automatically." wide><Seg label="Duration" value={days} onChange={setDays} options={DURATIONS} /></FieldGroup>
        )}
        <FormActions>
          <button type="submit" className="btn" disabled={busy || user.paying}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn quiet" onClick={onBack}>Back</button>
        </FormActions>
      </FormGrid>
    </div>
  );
}

function EraseForm({ user, onBack, onDone }: { user: UserRow; onBack: () => void; onDone: () => void }) {
  const { notify, fail } = useApp();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const word = confirmWord(user);
  const ok = confirmMatches(typed, word);
  const erase = async () => {
    if (!ok) return;
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; failed: { label: string }[] }>(`/admin/users/${user.id}/delete-data`, { method: "POST" });
      notify(r.ok ? `The app data of ${word} is deleted.` : `Deleted, except: ${r.failed.map((f) => f.label).join(", ")}. Run it again to retry.`);
      onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <div className="k-stack">
      <p className="k-small k-muted">This removes their chart drawings, connected accounts (tokens, inbox address and statement password), holdings, net worth
        entries, notebooks, alerts and preferences, with no way back. Their sign-in account, plan, payment records and usage counts stay.</p>
      <FormGrid label="Delete this user's data" onSubmit={(e) => { e.preventDefault(); void erase(); }}>
        <Field label={user.email ? "Type their email to confirm" : "Type their user id to confirm"} wide value={typed} onChange={(e) => setTyped(e.target.value)}
          placeholder={word} autoComplete="off" spellCheck={false} />
        <FormActions>
          <button type="submit" className="btn danger" disabled={!ok || busy}>{busy ? "Deleting…" : "Delete this user's data"}</button>
          <button type="button" className="btn quiet" onClick={onBack}>Back</button>
        </FormActions>
      </FormGrid>
    </div>
  );
}

/** The server's own refusal of a plan still billed (main.admin_delete_user), said before the button is offered. */
export const CANCEL_FIRST = "Their plan is still billed. Cancel the subscription first, then delete the user, so nothing paid is cut off or charged again.";

/** Delete the user: every row of theirs and their sign-in account, once their email is typed (the server checks it again, and refuses
 * the owner's own account, an admin's, and a plan still billed). */
function DeleteUserForm({ user, onBack, onDone }: { user: UserRow; onBack: () => void; onDone: () => void }) {
  const { notify, fail } = useApp();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  const word = user.email ?? "";
  const ok = !!word && confirmMatches(typed, word);
  const billed = user.paying && !user.cancel_at_period_end;
  const remove = async () => {
    if (!ok || billed) return;
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; failed: { label: string }[] }>(`/admin/users/${user.id}/delete-account`, { method: "POST", body: { confirm: typed } });
      notify(r.ok ? `${word} is deleted.` : `Not deleted: ${r.failed.map((f) => f.label).join(", ")} couldn't be removed. Their sign-in account stays, so you can run it again.`);
      onDone();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <div className="k-stack" data-testid="delete-user">
      <p className="k-small k-muted">This deletes their sign-in account and everything of theirs: profile, holdings, notebooks, watchlists, preferences, alerts,
        connected accounts (tokens and inbox address), net worth and briefs, with no way back. Their invoices and the payment records behind them stay, as tax law asks.</p>
      {billed && <Notice tone="warn">{CANCEL_FIRST}</Notice>}
      <FormGrid label="Delete this user" onSubmit={(e) => { e.preventDefault(); void remove(); }}>
        <Field label="Type their email to confirm" wide value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={word} autoComplete="off" spellCheck={false} />
        <FormActions>
          <button type="submit" className="btn danger" disabled={!ok || busy || billed}>{busy ? "Deleting…" : "Delete this user"}</button>
          <button type="button" className="btn quiet" onClick={onBack}>Back</button>
        </FormActions>
      </FormGrid>
    </div>
  );
}
