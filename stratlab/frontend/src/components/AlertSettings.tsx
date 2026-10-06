import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { HELP } from "../lib/help";
import { Badge, Card, CardHead, CheckField, Field, FieldGroup, FormActions, FormGrid, Notice } from "./kit";

/** Settings → Notifications → Alerts: what to send (the report after each market closes, a message for every paper trade)
 * and where (Telegram, email; the phone is on the Get the app page). One Save for all of it, the same call as before. */
export function AlertSettingsCard() {
  const { me, fail, notify, refreshMe } = useApp();
  const feats = me?.plan_info.features;
  const canReport = feats ? !!feats.daily_report : true, canAlert = feats ? !!feats.alerts : true;
  const [alerts, setAlerts] = useState({ enabled: false, tg: "", email: "", daily: true });

  useEffect(() => {
    if (me) setAlerts({ enabled: me.alerts.enabled, tg: me.alerts.telegram_chat_id || "", email: me.alerts.email || "", daily: me.alerts.daily_report ?? true });
  }, [me]);
  if (!me) return null;
  const ch = me.alerts.channels ?? { push: true, telegram: true, email: true };

  const save = async () => {
    try {
      await api("/me/alerts", { method: "PUT", body: { alerts_enabled: canAlert && alerts.enabled, telegram_chat_id: alerts.tg.trim() || null, alert_email: alerts.email.trim() || null, daily_report: alerts.daily } });
      await refreshMe(); notify("Alert settings saved.");
    } catch (e) { fail(e); }
  };
  const test = async () => {
    const names: Record<string, string> = { push: "phone notification", telegram: "Telegram", email: "email" };
    try {
      const r = await api<{ sent: string[]; failed?: Record<string, string> }>("/me/alerts/test", { method: "POST" });
      const bad = Object.entries(r.failed ?? {});
      notify(`Test sent by ${r.sent.map((c) => names[c] ?? c).join(" and ")}.` + (bad.length ? ` Not sent by ${bad.map(([c, why]) => `${names[c] ?? c} (${why})`).join(", ")}.` : ""));
    } catch (e) { fail(e); }
  };

  return (
    <Card id="alerts" label="Alerts">
      <CardHead title="Alerts" info={HELP.alerts} actions={!canReport ? <Badge tone="warn">Basic</Badge> : undefined} />
      <FormGrid label="Alerts" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <FieldGroup label="What to send" wide>
          <div className="k-stack">
            <CheckField checked={alerts.daily} disabled={!canReport} onChange={(on) => setAlerts({ ...alerts, daily: on })} label="A short report after each market closes" />
            <CheckField checked={alerts.enabled} disabled={!canAlert} onChange={(on) => setAlerts({ ...alerts, enabled: on })}
              label={<>A message for every paper trade{!canAlert && <span className="k-inline-badge"><Badge tone="warn">Pro</Badge></span>}</>} />
          </div>
        </FieldGroup>
        {ch.telegram && <Field label="Telegram chat ID" optional info="Open the StratLab bot and press Start, then message @userinfobot to find your chat ID."
          value={alerts.tg} disabled={!canReport} inputMode="numeric" maxLength={40} onChange={(e) => setAlerts({ ...alerts, tg: e.target.value })} />}
        {ch.email && <Field label="Email" optional type="email" value={alerts.email} disabled={!canReport} maxLength={200} onChange={(e) => setAlerts({ ...alerts, email: e.target.value })} />}
        <FormActions>
          <button type="submit" className="btn" disabled={!canReport}>Save</button>
          <button type="button" className="btn outline" disabled={!canReport} onClick={() => void test()}>Send a test</button>
        </FormActions>
      </FormGrid>
      <p className="k-small k-muted k-hint-line">The simplest way is a notification on your phone: turn it on under <Link className="link" to="/app">Get the app</Link>.</p>
      {me.is_admin && (!ch.telegram || !ch.email) && (
        <Notice tone="warn">Admin: {[!ch.telegram && "Telegram (set TELEGRAM_BOT_TOKEN)", !ch.email && "email (set RESEND_API_KEY)"].filter(Boolean).join(" and ")} {!ch.telegram && !ch.email ? "aren't" : "isn't"} set up on the server, so {!ch.telegram && !ch.email ? "they're" : "it's"} hidden. Add the variables in Railway to offer {!ch.telegram && !ch.email ? "them" : "it"}.</Notice>
      )}
    </Card>
  );
}
