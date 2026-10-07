import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly, money } from "../../lib/format";
import { useMoreColumns } from "../../components/MoreColumns";
import { Badge, Card, CardHead, ConfirmDialog, DataTable, EmptyState, Field, FormActions, FormGrid, Pager, Seg, Skeleton, type Column } from "../../components/kit";
import { useAdmin } from "./AdminContext";
import { UserDialog } from "./UserDialog";
import { PLAN_FILTERS, PLAN_NAME, planNote, usersPath, type PlanFilter, type UserRow } from "./users";

interface SessionRow { id: string; name: string; email: string | null; symbol: string; market: string; started_at: string; capital: number | null; equity: number | null; trades: number | null }

const PAGE = 25;

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
  const [plan, setPlan] = useState<PlanFilter>("all");
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState<UserRow | null>(null);
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [stopping, setStopping] = useState<SessionRow | null>(null);
  const [promo, setPromo] = useState<"start" | "end" | null>(null);
  const [promoDays, setPromoDays] = useState("10");
  const [busy, setBusy] = useState(false);
  const more = useMoreColumns("admin-users", 2);      // invite counts: one click away, so the users table fits a laptop

  const loadUsers = useCallback(async (query: string, on: PlanFilter) => {
    try { setUsers(await api<UserRow[]>(usersPath(query, on))); } catch (e) { fail(e); }
  }, [fail]);
  const loadSessions = useCallback(async () => { try { setSessions(await api<SessionRow[]>("/admin/sessions")); } catch (e) { fail(e); } }, [fail]);
  useEffect(() => {
    if (!me?.is_admin) return;
    const t = window.setTimeout(() => loadUsers(q, plan), q ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [q, plan, me?.is_admin, loadUsers]);
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

  const cols: Column<UserRow>[] = [
    { key: "email", header: "Email", rowHeader: true, wrap: true, cell: (u) => u.email ?? "–" },
    { key: "plan", header: "Plan", cell: (u) => (
      <span className="k-row"><Badge tone={u.plan === "free" ? "plain" : "ok"} dot={false}>{PLAN_NAME[u.plan]}</Badge>
        {u.plan !== "free" && <span className="k-small k-muted">{planNote(u)}</span>}</span>) },
    { key: "joined", header: "Joined", cell: (u) => dateOnly(u.created_at) },
    { key: "exp", header: "Experiments", numeric: true, cell: (u) => u.experiments },
    { key: "ai", header: "AI builds", numeric: true, cell: (u) => u.ai_builds },
    ...(more.on ? [
      { key: "inv", header: "Invited", info: "Accounts that signed up through this user's invite link", numeric: true, cell: (u: UserRow) => u.referrals ?? 0 },
      { key: "free", header: "Free months", info: "Free months of Basic this user earned from invites", numeric: true, cell: (u: UserRow) => u.free_months ?? 0 },
    ] : []),
    { key: "do", header: <span className="sr-only">Actions</span>, action: true, cell: (u) => (
      <button type="button" className="btn quiet sm" aria-haspopup="dialog" aria-label={`Actions for ${u.email ?? "this user"}`} title="Change plan or delete data"
        onClick={() => setOpen(u)}>⋯</button>) },
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
  const pages = Math.max(1, Math.ceil((users?.length ?? 0) / PAGE));
  const at = Math.min(page, pages);

  return (
    <>
      <Card label="Users">
        <CardHead title="Users" info="Experiments and AI builds are for this month; Invited is everyone who signed up through the user's invite link, ever; Free months are the months of Basic they earned from invites. The newest 200 users are loaded; search by email to find others. The … button on a row changes the plan or deletes the user's data."
          actions={more.toggle} />
        <div className="k-row adm-filters">
          <input className="k-input adm-search" type="search" placeholder="Search by email" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} aria-label="Search users by email" />
          <Seg label="Plan" options={PLAN_FILTERS} value={plan} onChange={(v) => { setPlan(v as PlanFilter); setPage(1); }} />
        </div>
        {!users ? <Skeleton label="Loading users" /> : users.length === 0 ? (
          <EmptyState title="No users match">{plan === "all" ? "Try part of an email address." : `No ${PLAN_NAME[plan]} users${q ? " with that in their email" : ""}.`}</EmptyState>
        ) : (
          <>
            <DataTable label="Users" rows={users.slice((at - 1) * PAGE, at * PAGE)} rowKey={(u) => u.id} columns={cols} />
            <Pager page={at} pages={pages} total={users.length} noun={users.length === 1 ? "user" : "users"} onPage={setPage} />
            {users.length >= 200 && <p className="k-small k-muted">The newest 200 are listed. Search by email to find others.</p>}
          </>
        )}
      </Card>

      <InviteRewards onChanged={() => loadUsers(q, plan)} />

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

      {open && <UserDialog user={open} onClose={() => setOpen(null)} onChanged={() => { void loadUsers(q, plan); void reload(); }} />}
      {promo === "start" && <ConfirmDialog title={`Start the launch offer for ${days} days?`} confirmLabel="Start the offer" danger={false} busy={busy} onConfirm={doPromo} onClose={() => setPromo(null)}>Every user gets every Pro feature, free, for {days} days starting now.</ConfirmDialog>}
      {promo === "end" && <ConfirmDialog title="End the launch offer now?" confirmLabel="End the offer" busy={busy} onConfirm={doPromo} onClose={() => setPromo(null)}>Everyone goes back to their own plan within a minute.</ConfirmDialog>}
      {stopping && <ConfirmDialog title={`Stop "${stopping.name}"?`} confirmLabel="Stop the session" busy={busy} onConfirm={doStop} onClose={() => setStopping(null)}>This ends {stopping.email}'s paper trading session now.</ConfirmDialog>}
    </>
  );
}
