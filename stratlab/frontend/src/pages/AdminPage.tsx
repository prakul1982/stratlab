import { useCallback, useEffect, useState } from "react";
import { Navigate, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly, money } from "../lib/format";
import { Loading, Modal } from "../components/ui";
import { AuditPanel, MarketAuditPanel } from "../components/AuditPanel";
import { PricesPanel } from "../components/PricesPanel";
import { InvoiceAdminPanel } from "../components/InvoiceAdminPanel";
import { PlatformPanel } from "../components/PlatformPanel";
import { HolidaysPanel, type CalendarStatus } from "../components/HolidaysPanel";

type Plan = "free" | "basic" | "pro";
type AIRow = { label: string; configured: boolean; in_use: boolean; model: string | null; last_error: string | null; quick_rank?: number | null; research_rank?: number | null };
interface Overview {
  server: {
    kite_ready: boolean; kite_token_day: string | null; kite_invalid?: string | null; feed_connected: boolean; live_sessions: number;
    auto_login: { at: string | null; ok: boolean | null; message: string }; auto_login_configured: boolean;
    recent_errors?: { ref: string; at: string; method: string; path: string; error: string; where: string }[];
    billing_enabled: boolean; ai: AIRow[]; research?: { finnhub: boolean }; promo_until?: string | null;
    calendar?: CalendarStatus; admin_alerts?: { email_ready: boolean; to: string[] };
    option_recorder?: { enabled: boolean; targets: string[]; every_minutes: number; today: number; day: string | null; last_at: string | null; last_error: string | null };
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

interface BillingCheck {
  key_id: string; mode: string; secret_length: number; webhook_secret_set: boolean; keys_ok: boolean; keys_error: string | null;
  plans: { label: string; id: string | null; ok: boolean; detail: string | null }[];
  international?: { enabled: boolean | null; detail: string }; currencies?: string[];
}

interface ReportedRow {
  id: string; name: string; author: string; email: string | null; description: string; reports: number;
  reasons: Record<string, number>; hidden: boolean; hidden_by: string | null; published_at: string;
}

type Tab = "overview" | "services" | "checks" | "users" | "billing";
const TABS: [Tab, string][] = [["overview", "Overview"], ["services", "Services"], ["checks", "Data checks"], ["users", "Users"], ["billing", "Billing"]];

export function AdminPage() {
  const { me, notify, fail } = useApp();
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some(([t]) => t === params.get("tab")) ? params.get("tab") as Tab : "overview";
  const [ov, setOv] = useState<Overview | null>(null);
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [shownUsers, setShownUsers] = useState(25);
  const [sessions, setSessions] = useState<SessionRow[] | null>(null);
  const [reported, setReported] = useState<{ entries: ReportedRow[]; reasons: Record<string, string> } | null>(null);
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<UserRow | null>(null);
  const [aiTest, setAiTest] = useState<AITest[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [promoDays, setPromoDays] = useState(10);
  const [billingCheck, setBillingCheck] = useState<BillingCheck | null>(null);
  const [filingCheck, setFilingCheck] = useState<{ ok: boolean; symbol: string; count?: number; error?: string; latest?: { at: string; label: string; subject: string }[];
    documents_found?: number; document?: { ok: boolean; title: string; kind: string; chars?: number; error?: string } | null } | null>(null);

  const [fixtureNote, setFixtureNote] = useState<string | null>(null);

  const loadOverview = useCallback(async () => {
    try {
      setOv(await api<Overview>("/admin/overview")); setSessions(await api<SessionRow[]>("/admin/sessions"));
      setReported(await api<{ entries: ReportedRow[]; reasons: Record<string, string> }>("/admin/library"));
    } catch (e) { fail(e); }
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
    notify("Broker login opened in a new tab. Come back and refresh when it says it's saved.");
  });
  const autoLogin = () => run("auto", async () => {
    const r = await api<{ ok: boolean; message: string }>("/admin/kite/auto-login-now", { method: "POST" });
    notify(r.message); await loadOverview();
  });
  const testEmail = () => run("mail", async () => {
    const r = await api<{ sent_to: string }>("/admin/alerts/test", { method: "POST" });
    notify(`Test email sent to ${r.sent_to}. Check your inbox (and spam).`);
  });
  const testAI = () => run("ai", async () => { setAiTest((await api<{ providers: AITest[] }>("/admin/ai/test", { method: "POST" })).providers); });
  const stop = (s: SessionRow) => {
    if (!confirm(`Stop "${s.name}" for ${s.email}?`)) return;
    run(`stop-${s.id}`, async () => { await api(`/admin/sessions/${s.id}/stop`, { method: "POST" }); notify("Session stopped."); await loadOverview(); });
  };

  const moderate = (r: ReportedRow, action: "hide" | "restore" | "delete") => {
    if (action === "delete" && !confirm(`Delete "${r.name}" from the library for good?`)) return;
    run(`lib-${r.id}`, async () => {
      await api(`/admin/library/${r.id}`, { method: "POST", body: { action } });
      notify(action === "restore" ? "Back in the library, reports cleared." : action === "hide" ? "Hidden." : "Deleted.");
      await loadOverview();
    });
  };

  const saveFixture = () => run("fixture", async () => {
    setFixtureNote("Collecting about two years of prices. This takes a minute or two…");
    const r = await api<Response>("/admin/fixture/prices", { method: "POST", raw: true });
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "real_prices.json.gz"; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 5000);
    setFixtureNote(`Saved real_prices.json.gz: ${r.headers.get("X-Instruments") ?? "?"} instruments, ${Math.round(blob.size / 1024)} KB${Number(r.headers.get("X-Problems")) ? `, ${r.headers.get("X-Problems")} skipped` : ""}. Upload it to GitHub at stratlab/backend/tests/fixtures/real_prices.json.gz.`);
  });
  const checkFilings = () => run("filings", async () => { setFilingCheck(await api("/admin/filings/check", { method: "POST" })); });
  const checkBilling = () => run("billing", async () => { setBillingCheck(await api<BillingCheck>("/admin/billing/check", { method: "POST" })); });
  const startPromo = () => {
    if (!confirm(`Give every user every Pro feature, free, for ${promoDays} days starting now?`)) return;
    run("promo", async () => { await api("/admin/promo", { method: "POST", body: { days: promoDays } }); notify(`Launch offer on for ${promoDays} days.`); await loadOverview(); });
  };
  const endPromo = () => {
    if (!confirm("End the launch offer now? Everyone goes back to their own plan within a minute.")) return;
    run("promo", async () => { await api("/admin/promo", { method: "DELETE" }); notify("Launch offer ended."); await loadOverview(); });
  };

  const sv = ov?.server;
  const st = ov?.stats;
  const aiKeys = sv?.ai.filter((a) => a.configured) ?? [];
  const open = (t: Tab) => setParams(t === "overview" ? {} : { tab: t }, { replace: true });

  // what needs a look, worst first; each item opens the tab where it is fixed
  const attention: { text: string; tab: Tab; bad: boolean }[] = [];
  if (sv) {
    if (!sv.kite_ready) attention.push({ text: sv.kite_invalid || "The broker isn't logged in today, so Indian prices and paper trading are offline.", tab: "services", bad: true });
    if (sv.auto_login_configured && sv.auto_login.ok === false) attention.push({ text: `The automatic broker login failed: ${sv.auto_login.message}`, tab: "services", bad: true });
    const aiDown = (aiTest ?? []).filter((a) => !a.ok).map((a) => a.label);
    if (!aiTest) aiKeys.filter((a) => a.last_error).forEach((a) => aiDown.push(a.label));
    if (!aiKeys.length) attention.push({ text: "No AI keys are set, so the idea builder and research reads are off.", tab: "services", bad: true });
    else if (aiDown.length) attention.push({ text: `AI: ${aiDown.join(", ")} ${aiDown.length > 1 ? "aren't" : "isn't"} answering. The others take over by themselves.`, tab: "services", bad: false });
    if (sv.admin_alerts && !sv.admin_alerts.email_ready) attention.push({ text: "Alert emails can't be sent yet: the server's email (SMTP) settings are missing.", tab: "services", bad: true });
    if (sv.recent_errors?.length) attention.push({ text: `${sv.recent_errors.length} server error${sv.recent_errors.length > 1 ? "s" : ""} since the last restart (listed below).`, tab: "overview", bad: false });
    const pending = (reported?.entries ?? []).filter((r) => r.hidden_by !== "admin").length;
    if (pending) attention.push({ text: `${pending} library entr${pending > 1 ? "ies were" : "y was"} reported by users.`, tab: "users", bad: false });
    if (sv.option_recorder?.last_error) attention.push({ text: `Option chain recording: ${sv.option_recorder.last_error}`, tab: "services", bad: false });
    if (sv.calendar?.days_left != null && sv.calendar.days_left < 60) attention.push({ text: `Exchange holidays are only known for ${sv.calendar.days_left} more days.`, tab: "checks", bad: false });
    if (!sv.billing_enabled) attention.push({ text: "Payments aren't connected, so paid plans show \"Coming soon\".", tab: "billing", bad: false });
    attention.sort((x, y) => Number(y.bad) - Number(x.bad));
  }

  return (
    <div className="stack" style={{ gap: 22 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">Only you can see this page</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Admin</h1>
        </div>
        <button className="btn outline" onClick={() => { loadOverview(); loadUsers(q); }}>Refresh</button>
      </div>

      <nav className="seg" aria-label="Admin sections" style={{ alignSelf: "flex-start", maxWidth: "100%" }}>
        {TABS.map(([t, label]) => (
          <button key={t} aria-pressed={tab === t} onClick={() => open(t)}>
            {label}{t === "overview" && attention.length > 0 ? ` (${attention.length})` : ""}
          </button>
        ))}
      </nav>

      {!ov ? <Loading label="Loading server status" /> : (
        <>
          {tab === "overview" && (
            <>
              <div className="stats-grid">
                {([["Users", st!.users, `${st!.new_7d} new this week`], ["Paid", st!.plans.basic + st!.plans.pro, `${st!.plans.basic} Basic · ${st!.plans.pro} Pro`],
                  ["Experiments", st!.experiments_month, "this month, all users"], ["AI builds", st!.ai_month, "this month, all users"]] as const).map(([k, v, d]) => (
                  <div key={k} className="card stack" style={{ gap: 4 }}>
                    <span className="small muted">{k}</span><span className="serif" style={{ fontSize: 38, lineHeight: 1.1 }}>{v}</span><span className="small muted">{d}</span>
                  </div>
                ))}
              </div>

              <section className="card stack" style={{ gap: 6 }}>
                <h2 className="h2">Needs your attention</h2>
                {!attention.length ? <p className="small muted" style={{ margin: 0 }}>Nothing. The broker is logged in, AI is answering, and there are no new errors or reports. Problems found by the daily check at 4:50 PM IST are emailed to you.</p>
                  : attention.map((x, i) => (
                    <div key={i} className="spread" style={{ padding: "10px 0", borderTop: i ? "1px solid var(--line)" : "none", gap: 12 }}>
                      <span className="row" style={{ gap: 10, alignItems: "baseline" }}><span className={`badge ${x.bad ? "fail" : "warn"}`}>{x.bad ? "Fix" : "Look"}</span><span className="small">{x.text}</span></span>
                      {x.tab !== "overview" && <button className="btn quiet sm" onClick={() => open(x.tab)}>Open {TABS.find(([t]) => t === x.tab)![1]}</button>}
                    </div>
                  ))}
              </section>

              {!!sv?.recent_errors?.length && (
                <section className="card stack" style={{ gap: 12 }}>
                  <h2 className="h2">Recent server errors <span className="muted" style={{ fontSize: 18 }}>({sv.recent_errors.length})</span></h2>
                  <p className="small muted">Crashes since the server last started, newest first. Users see the ref code in the error message.</p>
                  <div className="table-wrap"><table>
                    <thead><tr><th>Ref</th><th>When</th><th>Request</th><th>Error</th><th>Where</th></tr></thead>
                    <tbody>{sv.recent_errors.map((x) => (
                      <tr key={x.ref}><td className="mono">{x.ref}</td><td>{new Date(x.at).toLocaleString()}</td><td className="mono small">{x.method} {x.path}</td>
                        <td className="small" style={{ maxWidth: 380 }}>{x.error}</td><td className="mono small">{x.where}</td></tr>
                    ))}</tbody>
                  </table></div>
                </section>
              )}
            </>
          )}

          {tab === "services" && (
            <div className="grid2">
              <section className="card stack" style={{ gap: 4 }}>
                <h2 className="h2" style={{ marginBottom: 6 }}>Market data</h2>
                <Status ok={sv!.kite_ready} label="Broker data (India)" detail={sv!.kite_invalid ? sv!.kite_invalid : sv!.kite_ready ? `Logged in${sv!.kite_token_day ? ` for ${dateOnly(sv!.kite_token_day)}` : ""}` : "Not logged in today, so Indian prices and paper trading are offline."} />
                <Status ok={sv!.feed_connected || sv!.live_sessions === 0} warn label="Live price feed" detail={sv!.feed_connected ? "Connected" : sv!.live_sessions ? "Not connected" : "Idle (no India sessions running)"} />
                <Status ok={sv!.auto_login_configured && sv!.auto_login.ok === true} warn={!sv!.auto_login_configured || sv!.auto_login.ok === null} label="Automatic daily login"
                  detail={!sv!.auto_login_configured ? "Off. Log in by hand each morning, or set the automatic login variables (setup guide, step 2)." : `${sv!.auto_login.message}${sv!.auto_login.at ? ` (${ago(sv!.auto_login.at)})` : ""}`} />
                <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
                  <button className="btn sm" disabled={busy === "kite"} onClick={kiteLogin}>Log in to the broker</button>
                  {sv!.auto_login_configured && <button className="btn quiet sm" disabled={busy === "auto"} onClick={autoLogin}>{busy === "auto" ? "Logging in…" : "Run the automatic login now"}</button>}
                </div>
                <h2 className="h2" style={{ margin: "22px 0 6px" }}>Other services</h2>
                <Status ok={!!sv!.research?.finnhub} label="US company data" detail={sv!.research?.finnhub ? "Key is set" : "Add the company-data key in Railway for US company pages (setup guide, step 6). India needs no key."} />
                {sv!.admin_alerts && <Status ok={sv!.admin_alerts.email_ready} label="Alerts to you"
                  detail={sv!.admin_alerts.email_ready ? `Emailed to ${sv!.admin_alerts.to.join(", ")}, plus your phone or Telegram if set in Account.`
                    : `Email isn't set up on the server: add SMTP_HOST, SMTP_USER and SMTP_PASSWORD in Railway (for Gmail: smtp.gmail.com and an app password). Until then alerts reach only your phone or Telegram.`} />}
                {sv!.admin_alerts?.email_ready && <button className="btn quiet sm" style={{ alignSelf: "flex-start", marginTop: 8 }} disabled={busy === "mail"} onClick={testEmail}>{busy === "mail" ? "Sending…" : "Send a test email"}</button>}
                {sv!.option_recorder && (() => {
                  const r = sv!.option_recorder!;
                  return <Status ok={r.enabled && !r.last_error} warn={!r.enabled || !!r.last_error} label="Option chain recording"
                    detail={!r.enabled ? "Off. Set OPTION_SNAPSHOTS (for example NFO:NIFTY,NFO:BANKNIFTY) to record chains for options backtesting."
                      : `${r.targets.join(", ")} every ${r.every_minutes} min in market hours. ${r.today} saved today${r.last_at ? `, last ${ago(r.last_at)}` : ""}.${r.last_error ? ` Last problem: ${r.last_error}` : ""}`} />;
                })()}
                <div className="stack" style={{ gap: 8, marginTop: 10 }}>
                  <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy === "filings"} onClick={checkFilings}>{busy === "filings" ? "Asking the exchange…" : "Check filings feed"}</button>
                  {filingCheck && <Status ok={filingCheck.ok} label={`Exchange filings (${filingCheck.symbol})`}
                    detail={filingCheck.ok ? `${filingCheck.count} filings in the last year. Latest: ${(filingCheck.latest ?? []).map((l) => `${l.at.slice(0, 10)} ${l.label}`).join("; ") || "none"}`
                      : `${filingCheck.error} The exchange sometimes blocks cloud servers; if this keeps failing, the BSE feed can be added as a fallback.`} />}
                  {filingCheck?.ok && <Status ok={!!filingCheck.document?.ok} warn={!filingCheck.document} label="Company documents (deep dive)"
                    detail={!filingCheck.document ? `No presentation or call transcript among ${filingCheck.symbol}'s filings to try.`
                      : filingCheck.document.ok ? `Read "${filingCheck.document.title}" (${filingCheck.document.kind}): ${filingCheck.document.chars?.toLocaleString()} characters of text. ${filingCheck.documents_found} documents found.`
                      : `Couldn't read "${filingCheck.document.title}": ${filingCheck.document.error}`} />}
                </div>
              </section>

              <section className="card stack" style={{ gap: 4 }}>
                <div className="spread" style={{ marginBottom: 6 }}>
                  <h2 className="h2">AI</h2>
                  <button className="btn quiet sm" disabled={busy === "ai" || !aiKeys.length} onClick={testAI}>{busy === "ai" ? "Testing…" : "Test every provider"}</button>
                </div>
                {!aiKeys.length && <Status ok={false} label="No AI keys" detail="Add a free GROQ_API_KEY in Railway → Variables, then redeploy." />}
                {(aiTest ?? []).map((a) => <Status key={a.label} ok={a.ok} label={a.label} detail={a.ok ? `Working with ${a.model ?? "its default model"}, ${(a.ms / 1000).toFixed(1)}s` : a.error ?? "Failed"} />)}
                {!aiTest && aiKeys.map((a) => <Status key={a.label} ok={!a.last_error} warn={!a.last_error} label={a.label} detail={a.last_error ? `Last try failed: ${a.last_error}` : "Key set. Press Test to check it now."} />)}
                {aiKeys.length > 0 && <AIOrder rows={sv!.ai} />}
              </section>
            </div>
          )}

          {tab === "checks" && (
            <>
              <PlatformPanel />
              <AuditPanel />
              <MarketAuditPanel />
              <MarketAuditPanel region="US" />
              {sv?.calendar && <HolidaysPanel status={sv.calendar} onSaved={(c) => setOv((o) => o && { ...o, server: { ...o.server, calendar: c } })} />}
              <section className="card stack" style={{ gap: 8 }}>
                <h2 className="h2">Real prices for testing</h2>
                <p className="small muted" style={{ margin: 0, maxWidth: "80ch" }}>About two years of daily prices for the indices and a few stocks in each market, so the test suite checks the tools on real market behaviour. Prices only, no user data. Refresh it every few months.</p>
                <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy === "fixture"} onClick={saveFixture}>{busy === "fixture" ? "Collecting prices…" : "Save real prices"}</button>
                {fixtureNote && <p className="tiny muted" style={{ margin: 0 }}>{fixtureNote}</p>}
              </section>
            </>
          )}

          {tab === "users" && (
            <>
              <section className="card stack" style={{ gap: 14 }}>
                <div className="spread" style={{ flexWrap: "wrap", gap: 12 }}>
                  <h2 className="h2">Users</h2>
                  <input className="input" style={{ maxWidth: 320 }} placeholder="Search by email" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search users by email" />
                </div>
                {!users ? <Loading label="Loading users" /> : users.length === 0 ? <p className="small muted">No users match.</p> : (
                  <div className="table-wrap"><table>
                    <thead><tr><th>Email</th><th>Plan</th><th>Joined</th><th>Experiments</th><th>AI builds</th><th></th></tr></thead>
                    <tbody>{users.slice(0, shownUsers).map((u) => (
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
                {users && users.length > shownUsers && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setShownUsers((n) => n + 50)}>Show more ({users.length - shownUsers} more)</button>}
                <p className="hint">Counts are for this month. The newest 200 users are loaded; search by email to find others.</p>
              </section>

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

              <section className="card stack" style={{ gap: 12 }}>
                <h2 className="h2">Reported in the library <span className="muted" style={{ fontSize: 18 }}>({reported?.entries.length ?? 0})</span></h2>
                {!reported?.entries.length ? <p className="small muted">Nothing reported. An entry is hidden by itself after 3 reports from different people, until you look at it here.</p> : (
                  <div className="stack" style={{ gap: 10 }}>{reported.entries.map((r, i) => (
                    <div key={r.id} className="stack" style={{ gap: 6, paddingBottom: 10, borderBottom: i < reported.entries.length - 1 ? "1px solid var(--line)" : "none" }}>
                      <div className="spread" style={{ flexWrap: "wrap", gap: 8 }}>
                        <b>{r.name} <span className="small muted">by {r.author}{r.email ? ` (${r.email})` : ""}</span></b>
                        <span className="small">{r.hidden ? <span className="badge fail">Hidden{r.hidden_by === "admin" ? " by you" : " by reports"}</span> : <span className="badge">Showing</span>}</span>
                      </div>
                      {r.description && <p className="small muted">{r.description}</p>}
                      <span className="small">{r.reports} report{r.reports === 1 ? "" : "s"}{r.reports ? ": " + Object.entries(r.reasons).map(([k, n]) => `${reported.reasons[k] ?? k} (${n})`).join(", ") : ""}</span>
                      <div className="row wrap" style={{ gap: 8 }}>
                        <button className="btn quiet sm" disabled={busy === `lib-${r.id}`} onClick={() => moderate(r, "restore")}>{r.hidden ? "Restore" : "Keep, clear reports"}</button>
                        {!r.hidden && <button className="btn quiet sm" disabled={busy === `lib-${r.id}`} onClick={() => moderate(r, "hide")}>Hide</button>}
                        <button className="btn quiet sm danger" disabled={busy === `lib-${r.id}`} onClick={() => moderate(r, "delete")}>Delete</button>
                      </div>
                    </div>
                  ))}</div>
                )}
              </section>
            </>
          )}

          {tab === "billing" && (
            <>
              <section className="card stack" style={{ gap: 10 }}>
                <h2 className="h2">Launch offer</h2>
                {sv!.promo_until ? (
                  <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
                    <span><span className="badge pass">On</span> Every user has every Pro feature free until <b>{new Date(sv!.promo_until).toLocaleString()}</b>. Then plans apply again by themselves.</span>
                    <button className="btn quiet sm danger" disabled={busy === "promo"} onClick={endPromo}>End now</button>
                  </div>
                ) : (
                  <div className="row wrap" style={{ gap: 10 }}>
                    <span className="small muted">Off. Start it to give everyone every Pro feature free for a while, e.g. at launch. Payments keep working, so people can still subscribe.</span>
                    <label className="row" style={{ gap: 8 }}><span className="small">Days</span>
                      <input className="input" type="number" min={1} max={90} value={promoDays} onChange={(e) => setPromoDays(Math.max(1, Math.min(90, +e.target.value || 1)))} style={{ width: 80 }} /></label>
                    <button className="btn sm" disabled={busy === "promo"} onClick={startPromo}>Start now</button>
                  </div>
                )}
              </section>

              <section className="card stack" style={{ gap: 4 }}>
                <h2 className="h2" style={{ marginBottom: 6 }}>Payments</h2>
                <Status ok={sv!.billing_enabled} warn label="Razorpay" detail={sv!.billing_enabled ? "Connected" : "Not set up, so paid plans show \"Coming soon\". Grant plans by hand in Users."} />
                <div className="stack" style={{ gap: 8, marginTop: 6 }}>
                  <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy === "billing"} onClick={checkBilling}>{busy === "billing" ? "Asking Razorpay…" : "Check payments setup"}</button>
                  {billingCheck && (
                    <div className="stack small" style={{ gap: 4 }}>
                      <Status ok={billingCheck.keys_ok} label={`Keys (${billingCheck.mode} mode)`}
                        detail={billingCheck.keys_ok ? `Razorpay accepts key ${billingCheck.key_id}` : `Key ${billingCheck.key_id}, secret ${billingCheck.secret_length} characters: ${billingCheck.keys_error}. Regenerate the key in Razorpay and paste BOTH the new Key ID and secret into Railway.`} />
                      {billingCheck.plans.map((p) => <Status key={p.label} ok={p.ok} warn={!p.id} label={p.label} detail={p.detail ?? ""} />)}
                      <Status ok={billingCheck.webhook_secret_set} label="Webhook secret" detail={billingCheck.webhook_secret_set ? "Set" : "RAZORPAY_WEBHOOK_SECRET is missing"} />
                      {billingCheck.international && <Status ok={billingCheck.international.enabled === true} warn={billingCheck.international.enabled !== false}
                        label="International cards" detail={`${billingCheck.international.detail}${billingCheck.currencies?.length ? ` Plans are priced in ${billingCheck.currencies.join(", ")}.` : ""}`} />}
                    </div>
                  )}
                </div>
              </section>

              <InvoiceAdminPanel />
              <PricesPanel />
            </>
          )}
        </>
      )}
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
