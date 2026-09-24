import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CFG, supabase } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { Loading } from "../components/ui";

type Row = { t: string; s: "pass" | "fail" | "warn"; d: string };

export function AccountPage() {
  const { me, isPro, fail, notify, refreshMe, theme, setTheme } = useApp();
  const [alerts, setAlerts] = useState({ enabled: false, tg: "", email: "" });
  const [checks, setChecks] = useState<Row[] | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (me) setAlerts({ enabled: me.alerts.enabled, tg: me.alerts.telegram_chat_id || "", email: me.alerts.email || "" });
  }, [me]);

  if (!me) return <Loading label="Loading your account" />;
  const b = me.billing, u = me.usage;

  const cancel = async () => {
    if (!confirm("Cancel your subscription? You keep your plan until the end of this billing month.")) return;
    try { await api("/billing/cancel", { method: "POST" }); await refreshMe(); notify("Subscription cancelled at the end of this month."); } catch (e) { fail(e); }
  };
  const saveAlerts = async () => {
    try {
      await api("/me/alerts", { method: "PUT", body: { alerts_enabled: alerts.enabled, telegram_chat_id: alerts.tg.trim() || null, alert_email: alerts.email.trim() || null } });
      await refreshMe(); notify("Alert settings saved.");
    } catch (e) { fail(e); }
  };
  const testAlert = async () => {
    try { const r = await api<{ sent: string[] }>("/me/alerts/test", { method: "POST" }); notify(`Test alert sent by ${r.sent.join(" and ")}.`); } catch (e) { fail(e); }
  };
  const runCheck = async () => {
    setChecking(true);
    const rows: Row[] = [];
    const add = (r: Row) => { rows.push(r); setChecks([...rows]); };
    try {
      const { data } = await supabase.auth.getSession();
      add({ t: "Signed in", s: data.session ? "pass" : "fail", d: data.session?.user.email || "Not signed in. Sign out and in again." });
      let health: { data_online: boolean; ai_configured: boolean } | null = null;
      try { health = await (await fetch(CFG.API_BASE + "/health")).json(); add({ t: "StratLab server", s: "pass", d: CFG.API_BASE.replace("https://", "") }); }
      catch { add({ t: "StratLab server", s: "fail", d: "Can't reach the server. Check the Railway service is running and FRONTEND_ORIGIN lists this site." }); return; }
      const markets = await api<{ name: string; status: string }[]>("/markets");
      for (const m of markets.filter((x) => x.status !== "soon")) {
        add({ t: `${m.name} data`, s: m.status === "live" ? "pass" : "warn", d: m.status === "live" ? "Online" : "Offline right now" });
      }
      add({ t: "AI strategy builder", s: health?.ai_configured ? "pass" : "warn", d: health?.ai_configured ? "Configured" : "No AI key on the server: the simple converter is used instead." });
      add({ t: "Your account", s: "pass", d: `${me.plan_info.name} plan, ${u.backtests_used} experiments this month` });
    } catch (e) { fail(e); } finally { setChecking(false); }
  };

  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">{me.email}</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Account</h1>
        </div>
        <button className="btn outline" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>

      <div className="grid2">
        <div className="stack">
          <section className="card stack" style={{ gap: 0 }}>
            <h2 className="h2" style={{ marginBottom: 10 }}>Plan and usage</h2>
            {[
              ["Plan", me.plan_info.name],
              ...(me.plan !== "free" ? [[b.cancel_at_period_end ? "Ends on" : "Renews on", dateOnly(b.renews_or_ends)]] : []),
              ["Experiments this month", u.backtests_limit == null ? `${u.backtests_used} (unlimited)` : `${u.backtests_used} of ${u.backtests_limit}`],
              ["AI builds this month", u.ai_limit == null ? `${u.ai_used} (unlimited)` : `${u.ai_used} of ${u.ai_limit}`],
              ["Paper sessions running", `${me.live_running} of ${me.live_limit}`],
            ].map(([k, v]) => (
              <div key={k} className="spread" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}><span className="muted">{k}</span><b>{v}</b></div>
            ))}
            <div className="row wrap" style={{ gap: 8, marginTop: 14 }}>
              {me.plan === "free" ? <Link to="/plans" className="btn">See paid plans</Link>
                : b.cancel_at_period_end ? <span className="small muted">Cancelled. You keep {me.plan_info.name} until {dateOnly(b.renews_or_ends)}.</span>
                  : <><Link to="/plans" className="btn outline">Change plan</Link><button className="btn danger" onClick={cancel}>Cancel subscription</button></>}
            </div>
          </section>
          <section className="card stack" style={{ gap: 12 }}>
            <h2 className="h2">Look</h2>
            <div className="seg" role="group" aria-label="Theme">
              {(["system", "light", "dark"] as const).map((t) => (
                <button key={t} aria-pressed={theme === t} onClick={() => setTheme(t)}>{{ system: "Match my device", light: "Paper", dark: "Night" }[t]}</button>
              ))}
            </div>
          </section>
          <section className="card stack" style={{ gap: 12 }}>
            <div className="spread"><h2 className="h2">Connection check</h2><button className="btn quiet sm" disabled={checking} onClick={runCheck}>{checking ? "Checking…" : "Run check"}</button></div>
            {!checks && <p className="small muted">Checks your sign-in, the server, each market's data and the AI builder. Run it if something isn't loading.</p>}
            {checks?.map((r) => (
              <div key={r.t} className="spread" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
                <span className="stack" style={{ gap: 0 }}><b style={{ fontSize: 14.5 }}>{r.t}</b><span className="small muted">{r.d}</span></span>
                <span className={`badge ${r.s}`}>{r.s === "pass" ? "OK" : r.s === "warn" ? "Check" : "Problem"}</span>
              </div>
            ))}
          </section>
        </div>
        <section className="card stack" style={{ gap: 14, alignSelf: "start" }}>
          <div className="spread"><h2 className="h2">Trade alerts</h2>{!isPro && <span className="badge next">Pro</span>}</div>
          <p className="small muted">Get a message whenever a paper trading session buys or sells. For Telegram, open the StratLab bot and press Start, then paste your chat ID (message @userinfobot to find it).</p>
          <label className="row" style={{ gap: 10, fontWeight: 600 }}>
            <input type="checkbox" style={{ width: 20, height: 20 }} checked={alerts.enabled} disabled={!isPro} onChange={(e) => setAlerts({ ...alerts, enabled: e.target.checked })} />
            Send alerts for paper trades
          </label>
          <label className="field">Telegram chat ID<input value={alerts.tg} disabled={!isPro} inputMode="numeric" maxLength={40} onChange={(e) => setAlerts({ ...alerts, tg: e.target.value })} /></label>
          <label className="field">Alert email<input type="email" value={alerts.email} disabled={!isPro} maxLength={200} onChange={(e) => setAlerts({ ...alerts, email: e.target.value })} /></label>
          <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn" disabled={!isPro} onClick={saveAlerts}>Save alerts</button>
            <button className="btn outline" disabled={!isPro} onClick={testAlert}>Send a test alert</button>
          </div>
        </section>
      </div>
    </div>
  );
}
