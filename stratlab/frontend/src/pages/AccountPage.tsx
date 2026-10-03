import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, CFG, supabase } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";
import { LegalLinks } from "./LegalPage";
import { Info, Loading } from "../components/ui";
import { HELP } from "../lib/help";
import { FOCUSES, LEVELS } from "../components/LevelPrompt";
import { PhoneCard } from "../components/PhoneCard";
import { Block } from "../components/More";
import { InvoicesCard } from "../components/InvoicesCard";

type Row = { t: string; s: "pass" | "fail" | "warn"; d: string };

export function AccountPage() {
  const { me, fail, notify, refreshMe, level, setLevel, focus, setFocus } = useApp();
  const feats = me?.plan_info.features;
  const canReport = feats ? !!feats.daily_report : true, canAlert = feats ? !!feats.alerts : true;
  const [alerts, setAlerts] = useState({ enabled: false, tg: "", email: "", daily: true });
  const [checks, setChecks] = useState<Row[] | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (me) setAlerts({ enabled: me.alerts.enabled, tg: me.alerts.telegram_chat_id || "", email: me.alerts.email || "", daily: me.alerts.daily_report ?? true });
  }, [me]);

  if (!me) return <Loading label="Loading your account" />;
  const b = me.billing, u = me.usage;
  const ch = me.alerts.channels ?? { push: true, telegram: true, email: true };

  const cancel = async () => {
    const until = me?.billing.renews_or_ends ? ` (${dateOnly(me.billing.renews_or_ends)})` : "";
    if (!confirm(`Cancel your subscription? You keep your plan until the end of the period you've paid for${until}, and you won't be charged again.`)) return;
    try { await api("/billing/cancel", { method: "POST" }); await refreshMe(); notify(`Cancelled. Your plan stays until the end of the paid period${until}.`); } catch (e) { fail(e); }
  };
  const saveAlerts = async () => {
    try {
      await api("/me/alerts", { method: "PUT", body: { alerts_enabled: canAlert && alerts.enabled, telegram_chat_id: alerts.tg.trim() || null, alert_email: alerts.email.trim() || null, daily_report: alerts.daily } });
      await refreshMe(); notify("Alert settings saved.");
    } catch (e) { fail(e); }
  };
  const testAlert = async () => {
    const names: Record<string, string> = { push: "phone notification", telegram: "Telegram", email: "email" };
    try {
      const r = await api<{ sent: string[]; failed?: Record<string, string> }>("/me/alerts/test", { method: "POST" });
      const bad = Object.entries(r.failed ?? {});
      notify(`Test sent by ${r.sent.map((c) => names[c] ?? c).join(" and ")}.` + (bad.length ? ` Not sent by ${bad.map(([c, why]) => `${names[c] ?? c} (${why})`).join(", ")}.` : ""));
    } catch (e) { fail(e); }
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
        add({ t: /data$/i.test(m.name) ? m.name : `${m.name} data`, s: m.status === "live" ? "pass" : "warn", d: m.status === "live" ? "Online" : "Offline right now" });
      }
      if (!health?.ai_configured) add({ t: "AI strategy builder", s: me.is_admin ? "fail" : "warn",
        d: me.is_admin ? "No AI key on the server, so the simple converter is used. Add a free GROQ_API_KEY (console.groq.com) in Railway → Variables, then redeploy."
          : "Using the simple converter right now. Describing ideas still works." });
      else if (!me.is_admin) add({ t: "AI strategy builder", s: "pass", d: "Online" });
      else {
        // only the owner tests every provider: each test spends the shared free AI allowance
        add({ t: "AI strategy builder", s: "warn", d: "Testing each provider…" });
        try {
          const r = await api<{ providers: { label: string; ok: boolean; error: string | null; model: string | null; ms: number }[] }>("/admin/ai/test", { method: "POST" });
          rows.pop();
          const working = r.providers.filter((p) => p.ok).length;
          add({ t: "AI strategy builder", s: working ? "pass" : "fail",
            d: working ? `${working} of ${r.providers.length} providers working` : "No provider answered, so the simple converter is used. See the reasons below." });
          for (const p of r.providers) {
            add({ t: `AI: ${p.label}`, s: p.ok ? "pass" : "fail",
              d: p.ok ? `Working${p.model ? ` with ${p.model}` : ""}, answered in ${(p.ms / 1000).toFixed(1)}s` : p.error || "Failed" });
          }
        } catch (e) {
          rows.pop();
          add({ t: "AI strategy builder", s: "warn", d: `Couldn't run the AI test: ${(e as Error).message}` });
        }
      }
      add({ t: "Your account", s: "pass", d: `${me.plan_info.name} plan, ${u.backtests_used} experiments this month` });
    } catch (e) { fail(e); } finally { setChecking(false); }
  };

  const paid = me.paid_plan ?? me.plan;   // what they pay for; me.plan is Pro for everyone during the launch offer
  return (
    <div className="stack" style={{ gap: 26 }}>
      <div className="spread" style={{ flexWrap: "wrap", alignItems: "flex-end" }}>
        <div className="stack" style={{ gap: 6 }}>
          <span className="eyebrow">{me.email}</span>
          <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em" }}>Account</h1>
        </div>
        <button className="btn outline" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>

      <div className="stack" style={{ gap: 18, maxWidth: 820 }}>
        <section className="card stack" style={{ gap: 0 }}>
          <div className="spread" style={{ marginBottom: 6 }}>
            <h2 className="h2 row" style={{ gap: 0 }}>Plan and usage<Info>{HELP.experimentsQuota}</Info></h2>
            <span className="badge skip">{me.plan_info.name}{me.promo ? " (launch offer)" : ""}</span>
          </div>
          {[
            ...(me.promo ? [["Launch offer", `Every Pro feature free until ${dateOnly(me.promo.until)}`]] : []),
            ...(paid !== "free" ? [[b.cancel_at_period_end ? "Ends on" : "Renews on", dateOnly(b.renews_or_ends)]] : []),
            ["Experiments this month", u.backtests_limit == null ? `${u.backtests_used} (unlimited)` : `${u.backtests_used} of ${u.backtests_limit}`],
            ["AI builds this month", u.ai_limit == null ? `${u.ai_used} (unlimited)` : `${u.ai_used} of ${u.ai_limit}`],
            ["Paper sessions running", `${me.live_running} of ${me.live_limit}`],
          ].map(([k, v]) => (
            <div key={k} className="spread" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}><span className="muted">{k}</span><b>{v}</b></div>
          ))}
          <div className="row wrap" style={{ gap: 8, marginTop: 14 }}>
            {paid === "free" ? <Link to="/plans" className="btn">See paid plans</Link>
              : b.cancel_at_period_end ? <><span className="small muted">Cancelled. You keep {me.plan_info.name} until {dateOnly(b.renews_or_ends)}.</span><Link to="/plans" className="btn outline">Compare plans</Link></>
                : <><Link to="/plans" className="btn outline">Change plan</Link><button className="btn quiet danger" onClick={cancel}>Cancel subscription</button></>}
          </div>
        </section>

        <InvoicesCard />

        <section className="card stack" style={{ gap: 16 }}>
          <div className="spread"><h2 className="h2 row" style={{ gap: 0 }}>Alerts<Info>{HELP.alerts}</Info></h2>{!canReport && <span className="badge next">Basic</span>}</div>
          <Block title="What to send">
            <label className="row" style={{ gap: 10, fontWeight: 600 }}>
              <input type="checkbox" style={{ width: 20, height: 20 }} checked={alerts.daily} disabled={!canReport} onChange={(e) => setAlerts({ ...alerts, daily: e.target.checked })} />
              A short report after each market closes
            </label>
            <label className="row" style={{ gap: 10, fontWeight: 600 }}>
              <input type="checkbox" style={{ width: 20, height: 20 }} checked={alerts.enabled} disabled={!canAlert} onChange={(e) => setAlerts({ ...alerts, enabled: e.target.checked })} />
              A message for every paper trade{!canAlert && <span className="badge next">Pro</span>}
            </label>
          </Block>
          <Block title="Where">
            <p className="small muted">On your phone is the simplest: turn it on under <b>On your phone</b> below.{ch.telegram || ch.email ? " Or add:" : ""}</p>
            {ch.telegram && <label className="field">Telegram chat ID<input value={alerts.tg} disabled={!canReport} inputMode="numeric" maxLength={40} onChange={(e) => setAlerts({ ...alerts, tg: e.target.value })} />
              <span className="hint">Open the StratLab bot and press Start, then message @userinfobot to find your chat ID.</span></label>}
            {ch.email && <label className="field">Email<input type="email" value={alerts.email} disabled={!canReport} maxLength={200} onChange={(e) => setAlerts({ ...alerts, email: e.target.value })} /></label>}
            {me.is_admin && (!ch.telegram || !ch.email) && (
              <p className="hint">Admin: {[!ch.telegram && "Telegram (set TELEGRAM_BOT_TOKEN)", !ch.email && "email (set SMTP_HOST, SMTP_USER and SMTP_PASSWORD)"].filter(Boolean).join(" and ")} {!ch.telegram && !ch.email ? "aren't" : "isn't"} set up on the server, so {!ch.telegram && !ch.email ? "they're" : "it's"} hidden. Add the variables in Railway to offer {!ch.telegram && !ch.email ? "them" : "it"}.</p>
            )}
          </Block>
          <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn" disabled={!canReport} onClick={saveAlerts}>Save</button>
            <button className="btn outline" disabled={!canReport} onClick={testAlert}>Send a test</button>
          </div>
        </section>

        <PhoneCard />

        <section className="card stack" style={{ gap: 12 }}>
          <h2 className="h2">What you're here for</h2>
          <div className="seg" role="radiogroup" aria-label="What you're here for" style={{ alignSelf: "flex-start" }}>
            {FOCUSES.map(([f, title]) => <button key={f} role="radio" aria-checked={focus === f} aria-pressed={focus === f} onClick={() => setFocus(f)}>{title}</button>)}
          </div>
          {focus && <p className="small muted">{FOCUSES.find(([f]) => f === focus)?.[2]} This sets what the menu and home page show first.</p>}
        </section>

        <section className="card stack" style={{ gap: 12 }}>
          <h2 className="h2">Experience</h2>
          <div className="seg" role="radiogroup" aria-label="Experience" style={{ alignSelf: "flex-start" }}>
            {LEVELS.map(([l, title]) => <button key={l} role="radio" aria-checked={level === l} aria-pressed={level === l} onClick={() => setLevel(l)}>{title}</button>)}
          </div>
          {level && <p className="small muted">{LEVELS.find(([l]) => l === level)?.[2]} Everything stays available either way.</p>}
        </section>

        <section className="card stack" style={{ gap: 12 }}>
          <div className="spread"><h2 className="h2 row" style={{ gap: 0 }}>Connection check<Info>{HELP.connection}</Info></h2><button className="btn quiet sm" disabled={checking} onClick={runCheck}>{checking ? "Checking…" : "Run check"}</button></div>
          {!checks && <p className="small muted">If something isn't loading: checks your sign-in, the server, each market's data and the AI builder.</p>}
          {checks?.map((r) => (
            <div key={r.t} className="spread" style={{ padding: "6px 0", borderBottom: "1px solid var(--line)" }}>
              <span className="stack" style={{ gap: 0 }}><b style={{ fontSize: 14.5 }}>{r.t}</b><span className="small muted">{r.d}</span></span>
              <span className={`badge ${r.s}`}>{r.s === "pass" ? "OK" : r.s === "warn" ? "Check" : "Problem"}</span>
            </div>
          ))}
        </section>
        <LegalLinks />
      </div>
    </div>
  );
}
