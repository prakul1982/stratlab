import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, money } from "../../lib/format";
import { Modal } from "../../components/ui";
import { useMoreColumns } from "../../components/MoreColumns";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, EmptyState, Field, FieldGroup, FormActions, FormGrid, Notice, Seg, Skeleton, type Column } from "../../components/kit";
import { useAdmin, type Plan } from "./AdminContext";

interface UserRow {
  id: string; email: string | null; created_at: string | null; plan: Plan; plan_set: string; plan_status: string | null;
  plan_until: string | null; paying: boolean; experiments: number; ai_builds: number; referrals?: number; free_months?: number;
}
interface SessionRow { id: string; name: string; email: string | null; symbol: string; market: string; started_at: string; capital: number | null; equity: number | null; trades: number | null }

const PLAN_NAME: Record<Plan, string> = { free: "Free", basic: "Basic", pro: "Pro" };
const DURATIONS = [{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "1 year" }, { value: "none", label: "No end date" }];

function PlanModal({ user, onClose, onSaved }: { user: UserRow; onClose: () => void; onSaved: () => void }) {
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
      onSaved(); onClose();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal title="Change plan" onClose={onClose}>
      <div className="k-stack">
        <p className="k-muted">{user.email} · now on <b>{PLAN_NAME[user.plan]}</b>{user.plan_until ? ` until ${dateOnly(user.plan_until)}` : ""}.</p>
        {user.paying && <Notice tone="warn">This user has a Razorpay subscription. Its next payment or cancellation will overwrite what you set here.</Notice>}
        <FormGrid label="Change plan" onSubmit={(e) => { e.preventDefault(); save(); }}>
          <FieldGroup label="Plan" wide><Seg label="Plan" value={plan} onChange={(v) => setPlan(v as Plan)} options={(["free", "basic", "pro"] as Plan[]).map((p) => ({ value: p, label: PLAN_NAME[p] }))} /></FieldGroup>
          {plan !== "free" && (
            <FieldGroup label="For how long" info="When it ends, they go back to Free automatically." wide><Seg label="Duration" value={days} onChange={setDays} options={DURATIONS} /></FieldGroup>
          )}
          <FormActions>
            <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save"}</button>
            <button type="button" className="btn quiet" onClick={onClose}>Cancel</button>
          </FormActions>
        </FormGrid>
      </div>
    </Modal>
  );
}

type RewardRow = { newcomer: string; newcomer_email: string | null; referrer: string; referrer_email: string | null; at: string | null;
  status: string; given_at: string | null; signups_that_day: number; months: number; capped: boolean;
  reward?: string | null; reward_label?: string };
type RewardsView = { review: RewardRow[]; given: RewardRow[]; months_given: number; waiting: number; extras_given?: number; waiting_to_subscribe?: number };

/** Rewards waiting for review (a link that brought more than 5 sign-ups in a day), and the newest given. Approved, a
 * reward is given once the friend is active; rejected, nothing is given. */
function InviteRewards({ onChanged }: { onChanged: () => void }) {
  const { notify, fail } = useApp();
  const [v, setV] = useState<RewardsView | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => { api<RewardsView>("/admin/invite-rewards").then(setV).catch(fail); }, [fail]);
  const decide = async (r: RewardRow, decision: "approve" | "reject") => {
    setBusy(r.newcomer);
    try {
      const out = await api<RewardsView & { status: string }>(`/admin/invite-rewards/${encodeURIComponent(r.newcomer)}/${decision}`, { method: "POST" });
      setV(out);
      notify(decision === "reject" ? "Rejected: no free months for this invite."
        : out.status === "given" ? "Approved and given: the friend has a free month of Basic, and the inviter's reward is counted."
          : out.status === "expired" ? "Approved, but the friend's first 14 days ended without 3 active days, so there's nothing to give."
            : "Approved: given once the friend is active.");
      onChanged();
    } catch (e) { fail(e); } finally { setBusy(null); }
  };
  if (!v) return <Card label="Invite rewards"><Skeleton label="Loading invite rewards" lines={2} /></Card>;
  const review: Column<RewardRow>[] = [
    { key: "friend", header: "Friend", rowHeader: true, cell: (r) => r.newcomer_email ?? r.newcomer },
    { key: "by", header: "Invited by", cell: (r) => r.referrer_email ?? r.referrer },
    { key: "at", header: "Joined", cell: (r) => dateOnly(r.at) },
    { key: "n", header: "That day", info: "Sign-ups through this link that day", numeric: true, cell: (r) => r.signups_that_day },
    { key: "do", header: <span className="sr-only">Decide</span>, action: true, cell: (r) => (
      <span className="k-row">
        <button type="button" className="btn quiet sm" disabled={busy === r.newcomer} onClick={() => decide(r, "approve")}>Approve</button>
        <button type="button" className="btn quiet sm danger" disabled={busy === r.newcomer} onClick={() => decide(r, "reject")}>Reject</button>
      </span>) },
  ];
  const given: Column<RewardRow>[] = [
    { key: "friend", header: "Friend", rowHeader: true, cell: (r) => r.newcomer_email ?? r.newcomer },
    { key: "by", header: "Invited by", cell: (r) => r.referrer_email ?? r.referrer },
    { key: "at", header: "Given", cell: (r) => dateOnly(r.given_at) },
    { key: "type", header: "Reward", info: "How the inviter earned: the friend's use, or the friend's first payment", cell: (r) => <span data-testid="reward-type">{r.reward_label || "None"}</span> },
    { key: "m", header: "Months", numeric: true, cell: (r) => r.months },
  ];
  return (
    <Card testId="invite-rewards" label="Invite rewards">
      <CardHead title="Invite rewards" info="A friend who joins through someone's link and uses the app on 3 different days in their first 2 weeks gets a free month of Basic. The inviter gets a free month for each of their first 2 such friends in a rolling year (Use), and for each of their first 2 friends whose first real payment comes within 90 days of joining (Payment); after that each paying friend gives them 25% of a month as 8 days of free time, at most 8 a year. One reward per friend; a refund or dispute within 7 days of the payment takes it back. More than 5 sign-ups through one link in a day wait here; the sign-ups themselves go through."
        actions={<span className="k-small k-muted">{v.months_given} free {v.months_given === 1 ? "month" : "months"} given · {v.extras_given ?? 0} extra credits · {v.waiting} waiting for the friend to be active · {v.waiting_to_subscribe ?? 0} waiting to subscribe</span>} />
      <h3 className="adm-sub">Waiting for your review ({v.review.length})</h3>
      <DataTable label="Invite rewards waiting for review" rows={v.review} rowKey={(r) => r.newcomer} columns={review} empty="Nothing to review." />
      <h3 className="adm-sub">Given</h3>
      <DataTable label="Invite rewards given" rows={v.given.slice(0, 50)} rowKey={(r) => r.newcomer} columns={given} empty="None yet." />
    </Card>
  );
}

/** Admin → Users and growth: the users (search by email, change a plan), invite rewards, the launch offer, and the paper
 * trading sessions running now. */
export function UsersSection() {
  const { me, notify, fail } = useApp();
  const { ov, reload } = useAdmin();
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [q, setQ] = useState("");
  const [shown, setShown] = useState(25);
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [stopping, setStopping] = useState<SessionRow | null>(null);
  const [erasing, setErasing] = useState<UserRow | null>(null);
  const [promo, setPromo] = useState<"start" | "end" | null>(null);
  const [promoDays, setPromoDays] = useState("10");
  const [busy, setBusy] = useState(false);
  const more = useMoreColumns("admin-users", 2);      // invite counts: one click away, so the users table fits a laptop

  const loadUsers = useCallback(async (query: string) => {
    try { setUsers(await api<UserRow[]>(`/admin/users?q=${encodeURIComponent(query)}`)); } catch (e) { fail(e); }
  }, [fail]);
  const loadSessions = useCallback(async () => { try { setSessions(await api<SessionRow[]>("/admin/sessions")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => {
    if (!me?.is_admin) return;
    const t = window.setTimeout(() => loadUsers(q), q ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [q, me?.is_admin, loadUsers]);
  useEffect(() => { loadSessions(); }, [loadSessions]);

  const days = Math.max(1, Math.min(90, Number(promoDays) || 1));
  const doPromo = async () => {
    setBusy(true);
    try {
      if (promo === "start") { await api("/admin/promo", { method: "POST", body: { days } }); notify(`Launch offer on for ${days} days.`); }
      else { await api("/admin/promo", { method: "DELETE" }); notify("Launch offer ended."); }
      setPromo(null); await reload();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const doStop = async () => {
    if (!stopping) return;
    setBusy(true);
    try { await api(`/admin/sessions/${stopping.id}/stop`, { method: "POST" }); notify("Session stopped."); setStopping(null); await loadSessions(); } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const doErase = async () => {
    if (!erasing) return;
    setBusy(true);
    try {
      const r = await api<{ ok: boolean; failed: { label: string }[] }>(`/admin/users/${erasing.id}/delete-data`, { method: "POST" });
      notify(r.ok ? `The app data of ${erasing.email} is deleted.` : `Deleted, except: ${r.failed.map((f) => f.label).join(", ")}. Run it again to retry.`);
      setErasing(null);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const cols: Column<UserRow>[] = [
    { key: "email", header: "Email", rowHeader: true, wrap: true, cell: (u) => u.email ?? "–" },
    { key: "plan", header: "Plan", cell: (u) => (
      <span className="k-row"><Badge tone={u.plan === "free" ? "plain" : "ok"} dot={false}>{PLAN_NAME[u.plan]}</Badge>
        {u.plan !== "free" && <span className="k-small k-muted">{u.plan_until ? `until ${dateOnly(u.plan_until)}` : u.paying ? "Razorpay" : "no end"}</span>}</span>) },
    { key: "joined", header: "Joined", cell: (u) => dateOnly(u.created_at) },
    { key: "exp", header: "Experiments", numeric: true, cell: (u) => u.experiments },
    { key: "ai", header: "AI builds", numeric: true, cell: (u) => u.ai_builds },
    ...(more.on ? [
      { key: "inv", header: "Invited", info: "Accounts that signed up through this user's invite link", numeric: true, cell: (u: UserRow) => u.referrals ?? 0 },
      { key: "free", header: "Free months", info: "Free months of Basic this user earned from invites", numeric: true, cell: (u: UserRow) => u.free_months ?? 0 },
    ] : []),
    { key: "do", header: <span className="sr-only">Actions</span>, action: true, cell: (u) => (
      <span className="k-row">
        <button type="button" className="btn quiet sm" onClick={() => setEditing(u)}>Change plan</button>
        <button type="button" className="btn quiet sm danger" onClick={() => setErasing(u)}>Delete this user's data</button>
      </span>) },
  ];
  const sess: Column<SessionRow>[] = [
    { key: "name", header: "Session", rowHeader: true, wrap: true, cell: (s) => s.name },
    { key: "user", header: "User", wrap: true, cell: (s) => s.email },
    { key: "sym", header: "Instrument", cell: (s) => s.symbol },
    { key: "at", header: "Started", cell: (s) => ago(s.started_at) },
    { key: "eq", header: "Equity", numeric: true, cell: (s) => (s.equity != null ? money(s.equity) : "–") },
    { key: "tr", header: "Trades", numeric: true, cell: (s) => s.trades ?? 0 },
    { key: "do", header: <span className="sr-only">Actions</span>, action: true, cell: (s) => <button type="button" className="btn quiet sm" onClick={() => setStopping(s)}>Stop</button> },
  ];
  const until = ov?.server.promo_until;

  return (
    <>
      <Card label="Users">
        <CardHead title="Users" info="Experiments and AI builds are for this month; Invited is everyone who signed up through the user's invite link, ever; Free months are the months of Basic they earned from invites. The newest 200 users are loaded; search by email to find others."
          actions={<>
            <input className="k-input adm-search" type="search" placeholder="Search by email" value={q} onChange={(e) => { setQ(e.target.value); setShown(25); }} aria-label="Search users by email" />
            {more.toggle}
          </>} />
        {!users ? <Skeleton label="Loading users" /> : users.length === 0 ? <EmptyState title="No users match">Try part of an email address.</EmptyState> : (
          <>
            <DataTable label="Users" rows={users.slice(0, shown)} rowKey={(u) => u.id} columns={cols} />
            {users.length > shown && <div className="k-row"><button type="button" className="btn quiet sm" onClick={() => setShown((n) => n + 50)}>Show more ({users.length - shown} more)</button></div>}
          </>
        )}
      </Card>

      <InviteRewards onChanged={() => loadUsers(q)} />

      <Card label="Launch offer">
        <CardHead title="Launch offer" actions={until ? <Badge tone="ok">On</Badge> : <Badge>Off</Badge>} />
        {until ? (
          <div className="k-spread">
            <span>Every user has every Pro feature free until <b>{new Date(until).toLocaleString("en-GB")}</b>. Then plans apply again by themselves.</span>
            <button type="button" className="btn quiet sm danger" onClick={() => setPromo("end")}>End now</button>
          </div>
        ) : (
          <FormGrid label="Start the launch offer" onSubmit={(e) => { e.preventDefault(); setPromo("start"); }}>
            <p className="k-small k-muted">Start it to give everyone every Pro feature free for a while, e.g. at launch. Payments keep working, so people can still subscribe.</p>
            <Field label="Days" type="number" min={1} max={90} value={promoDays} onChange={(e) => setPromoDays(e.target.value)} />
            <FormActions><button type="submit" className="btn sm">Start now</button></FormActions>
          </FormGrid>
        )}
      </Card>

      <Card label="Paper trading now">
        <CardHead title={`Paper trading now (${sessions?.length ?? 0})`} />
        {!sessions ? <Skeleton label="Loading sessions" lines={2} /> : <DataTable label="Paper trading sessions" rows={sessions} rowKey={(s) => s.id} columns={sess} empty="No sessions running." />}
      </Card>

      {editing && <PlanModal user={editing} onClose={() => setEditing(null)} onSaved={() => { loadUsers(q); reload(); }} />}
      {promo === "start" && <ConfirmDialog title={`Start the launch offer for ${days} days?`} confirmLabel="Start the offer" danger={false} busy={busy} onConfirm={doPromo} onClose={() => setPromo(null)}>Every user gets every Pro feature, free, for {days} days starting now.</ConfirmDialog>}
      {promo === "end" && <ConfirmDialog title="End the launch offer now?" confirmLabel="End the offer" busy={busy} onConfirm={doPromo} onClose={() => setPromo(null)}>Everyone goes back to their own plan within a minute.</ConfirmDialog>}
      {erasing && <ConfirmDialog title={`Delete the data of ${erasing.email ?? "this user"}?`} confirmLabel="Delete this user's data" busy={busy} onConfirm={doErase} onClose={() => setErasing(null)}>
        This removes their chart drawings, connected accounts (tokens, inbox address and statement password), holdings, net worth entries, notebooks, alerts and preferences, with no way back. Their sign-in account, plan and payment records stay.</ConfirmDialog>}
      {stopping && <ConfirmDialog title={`Stop "${stopping.name}"?`} confirmLabel="Stop the session" busy={busy} onConfirm={doStop} onClose={() => setStopping(null)}>This ends {stopping.email}'s paper trading session now.</ConfirmDialog>}
    </>
  );
}
