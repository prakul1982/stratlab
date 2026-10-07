import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { dateOnly } from "../../lib/format";
import { Modal } from "../../components/ui";
import { Badge, Field, FieldGroup, FormActions, FormGrid, Notice, Seg } from "../../components/kit";
import type { Plan } from "./AdminContext";
import { confirmMatches, confirmWord, PLAN_NAME, planNote, type UserRow } from "./users";

const DURATIONS = [{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "1 year" }, { value: "none", label: "No end date" }];

/** One user, opened from the row's "…" button: their facts, then Change plan or Delete data, each in this same box.
 * Deleting asks for the email typed in (never the browser's own box). */
export function UserDialog({ user, onClose, onChanged }: { user: UserRow; onClose: () => void; onChanged: () => void }) {
  const [step, setStep] = useState<"menu" | "plan" | "erase">("menu");
  const who = user.email ?? "this user";
  return (
    <Modal title={step === "plan" ? `Change plan: ${who}` : step === "erase" ? `Delete the data of ${who}?` : who} onClose={onClose}>
      {step === "menu" && (
        <div className="k-stack">
          <div className="k-rows">
            <div><span>Plan</span><b><Badge tone={user.plan === "free" ? "plain" : "ok"} dot={false}>{PLAN_NAME[user.plan]}</Badge></b></div>
            {user.plan !== "free" && <div><span>How</span><b>{planNote(user)}</b></div>}
            <div><span>Joined</span><b>{dateOnly(user.created_at)}</b></div>
            <div><span>Experiments this month</span><b>{user.experiments}</b></div>
            <div><span>AI builds this month</span><b>{user.ai_builds}</b></div>
            <div><span>Invited</span><b>{user.referrals ?? 0}</b></div>
          </div>
          <div className="k-row">
            <button type="button" className="btn outline" onClick={() => setStep("plan")}>Change plan</button>
            <button type="button" className="btn quiet danger" onClick={() => setStep("erase")}>Delete data…</button>
          </div>
        </div>
      )}
      {step === "plan" && <PlanForm user={user} onBack={() => setStep("menu")} onSaved={() => { onChanged(); onClose(); }} />}
      {step === "erase" && <EraseForm user={user} onBack={() => setStep("menu")} onDone={onClose} />}
    </Modal>
  );
}

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
      {user.paying && <Notice tone="warn">This user has a Razorpay subscription. Its next payment or cancellation will overwrite what you set here.</Notice>}
      <FormGrid label="Change plan" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <FieldGroup label="Plan" wide><Seg label="Plan" value={plan} onChange={(v) => setPlan(v as Plan)} options={(["free", "basic", "pro"] as Plan[]).map((p) => ({ value: p, label: PLAN_NAME[p] }))} /></FieldGroup>
        {plan !== "free" && (
          <FieldGroup label="For how long" info="When it ends, they go back to Free automatically." wide><Seg label="Duration" value={days} onChange={setDays} options={DURATIONS} /></FieldGroup>
        )}
        <FormActions>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
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
        entries, notebooks, alerts and preferences, with no way back. Their sign-in account, plan and payment records stay.</p>
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
