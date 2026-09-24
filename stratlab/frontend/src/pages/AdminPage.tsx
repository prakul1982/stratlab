import { useCallback, useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, money } from "../lib/format";
import { Loading, Modal } from "../components/ui";

type Plan = "free" | "basic" | "pro";
type AIRow = { label: string; configured: boolean; in_use: boolean; model: string | null; last_error: string | null; quick_rank?: number | null; research_rank?: number | null };
interface Overview {
  server: {
    kite_ready: boolean; kite_token_day: string | null; feed_connected: boolean; live_sessions: number;
    auto_login: { at: string | null; ok: boolean | null; message: string }; auto_login_configured: boolean;
    billing_enabled: boolean; ai: AIRow[]; research?: { finnhub: boolean };
  };
  stats: { users: number; plans: Record<Plan, number>; new_7d: number; experiments_month: number; ai_month: number };
}
interface UserRow {
  id: string; email: string | null; created_at: string | null; plan: Plan; plan_set: string; plan_status: string | null;
  plan_until: string | null; paying: boolean; experiments: number; ai_builds: number;
}
interface SessionRow { id: string; name: string; email: string | null; symbol: string; market: string; started_at: string; capital: number | null; equity: number | null; trades: number | null }
type AITest = { label: string; ok: boolean; error: string | null; model: string | null; ms: number };

const PLAN_NAME: Record<Plan, string> = { free: "Free", basic: "Basic", pro: "Pro" };
const DURATIONS: [string, number | null][] = [["30 days", 30], ["90 days", 90], ["1 year", 365], ["No end date", null]];

function Status({ ok, warn, label, detail }: { ok: boolean; warn?: boolean; label: string; detail: string }) {
  return (
    <div className="spread" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)", gap: 12 }}>
      <span className="stack" style={{ gap: 0, minWidth: 0 }}><b style={{ fontSize: 14.5 }}>{label}</b><span className="small muted">{detail}</span></span>
      <span className={`badge ${ok ? "pass" : warn ? "warn" : "fail"}`}>{ok ? "OK" : warn ? "Check" : "Problem"}</span>
    </div>
  );
}

function PlanModal({ user, onClose, onSaved }: { user: UserRow; onClose: () => void; onSaved: () => void }) {
  const { notify, fail } = useApp();
  const [plan, setPlan] = useState<Plan>(user.plan === "free" ? "basic" : user.plan);
  const [days, setDays] = useState<number | null>(30);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api(`/admin/users/${user.id}/plan`, { method: "POST", body: { plan, days: plan === "free" ? null : days } });
      notify(plan === "free" ? `${user.email} is back on Free.` : `${user.email} now has ${PLAN_NAME[plan]}${days ? ` for ${days} days` : ""}.`);
      onSaved(); onClose();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <Modal title="Change plan" onClose={onClose}>
      <div className="stack" style={{ gap: 18 }}>
        <p className="muted">{user.email} · now on <b>{PLAN_NAME[user.plan]}</b>{user.plan_until ? ` until ${dateOnly(user.plan_until)}` : ""}.</p>
        {user.paying && <p className="banner">This user has a Razorpay subscription. Its next payment or cancellation will overwrite what you set here.</p>}
        <div className="stack" style={{ gap: 8 }}>
          <span className="label">Plan</span>
          <div className="seg" role="radiogroup" aria-label="Plan">
            {(["free", "basic", "pro"] as Plan[]).map((p) => <button key={p} role="radio" aria-checked={plan === p} aria-pressed={plan === p} onClick={() => setPlan(p)}>{PLAN_NAME[p]}</button>)}
          </div>
        </div>
        {plan !== "free" && (
          <div className="stack" style={{ gap: 8 }}>
            <span className="label">For how long</span>
            <div className="seg" role="radiogroup" aria-label="Duration">
              {DURATIONS.map(([n, d]) => <button key={n} role="radio" aria-checked={days === d} aria-pressed={days === d} onClick={() => setDays(d)}>{n}</button>)}
            </div>
            <p className="hint">When it ends, they go back to Free automatically.</p>
          </div>
        )}
        <div className="row" style={{ gap: 10, justifyContent: "flex-end" }}>
          <button className="btn quiet" onClick={onClose}>Cancel</button>
          <button className="btn" disabled={busy} onClick={save}>{busy ? "Saving…" : "Save"}</button>
        </div>
      </div>
    </Modal>
  );
}

export function AdminPage() {
  const { me, notify, fail } = useApp();
  const [ov, setOv] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [aiTest, setAiTest] = useState<AITest[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    try { setOv(await api<Overview>("/admin/overview")); setSessions(await api<SessionRow[]>("/admin/sessions")); } catch (e) { fail(e); }
  }, [fail]);
  const loadUsers = useCallback(async (query: string) => {
    try { setUsers(await api<UserRow[]>(`/admin/users?q=${encodeURIComponent(query)}`)); } catch (e) { fail(e); }
  }, [fail]);

  useEffect(() => { if (me?.is_admin) loadOverview(); }, [me?.is_admin, loadOverview]);
  useEffect(() => {
    if (!me?.is_admin) return;
    const t = window.setTimeout(() => loadUsers(q), q ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [q, me?.is_admin, loadUsers]);

  if (!me) return <Loading label="Opening admin" />;
  if (!me.is_admin) return <Navigate to="/" replace />;

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try { await fn(); } catch (e) { fail(e); } finally { setBusy(null); }
  };
  const kiteLogin = () => run("kite", async () => {
    const { url } = await api<{ url: string }>("/admin/kite/login-url", { method: "POST" });
    window.open(url, "_blank", "noopener");
    notify("Kite login opened in a new tab. Come back and refresh when it says it's saved.");
  });
  const autoLogin = () => run("auto", async () => {
    const r = await api<{ ok: boolean; message: string }>("/admin/kite/auto-login-now", { method: "POST" });
    notify(r.message); await loadOverview();
  });
  const testAI = () => run("ai", async () => { setAiTest((await api<{ providers: AITest[] }>("/admin/ai/test", { method: "POST" })).providers); });
  const stop = (s: SessionRow) => {
    if (!confirm(`Stop "${s.name}" for ${s.email}?`)) return;
    run(`stop-${s.id}`, async () => { await api(`/admin/sessions/${s.id}/stop`, { method: "POST" }); notify("Session stopped."); await loadOverview(); });
  };

  const sv = ov?.server;
  const st = ov?.stats;
  const aiKeys = sv?.ai.filter((a) => a.configured) ?? [];
  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">Only you can see this page</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Admin</h1>
        </div>
        <button className="btn outline" onClick={() => { loadOverview(); loadUsers(q); }}>Refresh</button>
      </div>

      {!ov ? <Loading label="Loading server status" /> : (
        <>
          <div className="stats-grid">
            {([["Users", st!.users, `${st!.new_7d} new this week`], ["Paid", st!.plans.basic + st!.plans.pro, `${st!.plans.basic} Basic · ${st!.plans.pro} Pro`],
              ["Experiments", st!.experiments_month, "this month, all users"], ["AI builds", st!.ai_month, "this month, all users"]] as const).map(([k, v, d]) => (
              <div key={k} className="card stack" style={{ gap: 4 }}>
                <span className="small muted">{k}</span><span className="serif" style={{ fontSize: 38, lineHeight: 1.1 }}>{v}</span><span className="small muted">{d}</span>
              </div>
            ))}
          </div>

          <div className="grid2">
            <section className="card stack" style={{ gap: 4 }}>
              <h2 className="h2" style={{ marginBottom: 6 }}>Market data</h2>
              <Status ok={sv!.kite_ready} label="Kite (India)" detail={sv!.kite_ready ? `Logged in${sv!.kite_token_day ? ` for ${dateOnly(sv!.kite_token_day)}` : ""}` : "Not logged in today, so Indian prices and paper trading are offline."} />
              <Status ok={sv!.feed_connected || sv!.live_sessions === 0} warn label="Live price feed" detail={sv!.feed_connected ? "Connected" : sv!.live_sessions ? "Not connected" : "Idle (no India sessions running)"} />
              <Status ok={sv!.auto_login_configured && sv!.auto_login.ok === true} warn={!sv!.auto_login_configured || sv!.auto_login.ok === null} label="Automatic daily login"
                detail={!sv!.auto_login_configured ? "Off. Log in by hand each morning, or set KITE_USER_ID, KITE_PASSWORD and KITE_TOTP_SECRET." : `${sv!.auto_login.message}${sv!.auto_login.at ? ` (${ago(sv!.auto_login.at)})` : ""}`} />
              <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
                <button className="btn sm" disabled={busy === "kite"} onClick={kiteLogin}>Log in to Kite</button>
                {sv!.auto_login_configured && <button className="btn quiet sm" disabled={busy === "auto"} onClick={autoLogin}>{busy === "auto" ? "Logging in…" : "Run the automatic login now"}</button>}
              </div>
            </section>

            <section className="card stack" style={{ gap: 4 }}>
              <div className="spread" style={{ marginBottom: 6 }}>
                <h2 className="h2">AI builder</h2>
                <button className="btn quiet sm" disabled={busy === "ai" || !aiKeys.length} onClick={testAI}>{busy === "ai" ? "Testing…" : "Test every provider"}</button>
              </div>
              {!aiKeys.length && <Status ok={false} label="No AI keys" detail="Add a free GROQ_API_KEY in Railway → Variables, then redeploy." />}
              {(aiTest ?? []).map((a) => <Status key={a.label} ok={a.ok} label={a.label} detail={a.ok ? `Working with ${a.model ?? "its default model"}, ${(a.ms / 1000).toFixed(1)}s` : a.error ?? "Failed"} />)}
              {!aiTest && aiKeys.map((a) => <Status key={a.label} ok={!a.last_error} warn={!a.last_error} label={a.label} detail={a.last_error ? `Last try failed: ${a.last_error}` : "Key set. Press Test to check it now."} />)}
              {aiKeys.length > 0 && <AIOrder rows={sv!.ai} />}
              <Status ok={!!sv!.research?.finnhub} label="US company data (Finnhub)" detail={sv!.research?.finnhub ? "FINNHUB_API_KEY is set" : "Add FINNHUB_API_KEY in Railway for US company pages (free at finnhub.io). India needs no key."} />
              <Status ok={sv!.billing_enabled} warn label="Payments" detail={sv!.billing_enabled ? "Razorpay is connected" : "Razorpay not set up, so paid plans show \"Coming soon\". Grant plans by hand below."} />
            </section>
          </div>

          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">Paper trading now <span className="muted" style={{ fontSize: 18 }}>({sessions?.length ?? 0})</span></h2>
            {!sessions?.length ? <p className="small muted">No sessions running.</p> : (
              <div className="table-wrap"><table>
                <thead><tr><th>Session</th><th>User</th><th>Instrument</th><th>Started</th><th>Equity</th><th>Trades</th><th></th></tr></thead>
                <tbody>{sessions.map((s) => (
                  <tr key={s.id}>
                    <td>{s.name}</td><td>{s.email}</td><td className="num">{s.symbol}</td><td>{ago(s.started_at)}</td>
                    <td className="num">{s.equity != null ? money(s.equity) : "–"}</td><td className="num">{s.trades ?? 0}</td>
                    <td><button className="btn quiet sm" disabled={busy === `stop-${s.id}`} onClick={() => stop(s)}>Stop</button></td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </section>
        </>
      )}

      <section className="card stack" style={{ gap: 14 }}>
        <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
          <h2 className="h2">Users</h2>
          <input className="input" style={{ maxWidth: 320 }} placeholder="Search by email" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users by email" />
        </div>
        {!users ? <Loading label="Loading users" /> : users.length === 0 ? <p className="small muted">No users match.</p> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Email</th><th>Plan</th><th>Joined</th><th>Experiments</th><th>AI builds</th><th></th></tr></thead>
            <tbody>{users.map((u) => (
              <tr key={u.id}>
                <td>{u.email ?? "–"}</td>
                <td><span className={`badge ${u.plan === "free" ? "skip" : "next"}`}>{PLAN_NAME[u.plan]}</span>
                  {u.plan !== "free" && <span className="small muted" style={{ marginLeft: 8 }}>{u.plan_until ? `until ${dateOnly(u.plan_until)}` : u.paying ? "Razorpay" : "no end"}</span>}</td>
                <td>{dateOnly(u.created_at)}</td><td className="num">{u.experiments}</td><td className="num">{u.ai_builds}</td>
                <td><button className="btn quiet sm" onClick={() => setEditing(u)}>Change plan</button></td>
              </tr>
            ))}</tbody>
          </table></div>
        )}
        <p className="hint">Counts are for this month. The newest 200 users are shown; search to find others.</p>
      </section>
      {editing && <PlanModal user={editing} onClose={() => setEditing(null)} onSaved={() => { loadUsers(q); loadOverview(); }} />}
    </div>
  );
}


/** Which provider is asked first for each kind of job, and which keys are still missing. */
function AIOrder({ rows }: { rows: AIRow[] }) {
  const chain = (k: "quick_rank" | "research_rank") => rows.filter((r) => r[k]).sort((a, b) => a[k]! - b[k]!).map((r) => r.label).join(" → ");
  const missing = rows.filter((r) => !r.configured).map((r) => r.label);
  return (
    <div className="stack small" style={{ gap: 4, padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
      <span><b>Idea builder asks:</b> <span className="muted">{chain("quick_rank") || "–"}</span></span>
      <span><b>Research reads ask:</b> <span className="muted">{chain("research_rank") || "–"}</span></span>
      {missing.length > 0 && <span className="muted">No key yet: {missing.join(", ")}.</span>}
    </div>
  );
}
