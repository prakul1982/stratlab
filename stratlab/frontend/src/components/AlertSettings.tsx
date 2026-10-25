import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type ApiError } from "../lib/api";
import { alertsApi } from "../lib/alerts";
import { useApp } from "../lib/app";
import { HELP } from "../lib/help";
import { telegramState } from "../lib/telegramState";
import { Badge, Card, CardHead, CheckField, Field, FieldGroup, FormActions, FormGrid, Notice, PlanNote } from "./kit";

/** Settings → Notifications → Alerts: what to send (the report after each market closes, a message for every paper trade)
 * and where (Telegram, email; the phone is on the Get the app page). One Save for all of it, the same call as before. */
export function AlertSettingsCard() {
  const { me, fail, notify, refreshMe } = useApp();
  const feats = me?.plan_info.features;
  const canReport = feats ? !!feats.daily_report : true, canAlert = feats ? !!feats.alerts : true;
  const [alerts, setAlerts] = useState({ enabled: false, tg: "", email: "", daily: true });
  // where an alert can go right now (a phone, Telegram, a confirmed email): a test needs one of them
  const [routes, setRoutes] = useState<string[] | null>(null);
  const [code, setCode] = useState("");
  const [testNote, setTestNote] = useState<string | null>(null);
  useEffect(() => { alertsApi.list().then((p) => setRoutes(p.channels)).catch(() => setRoutes(null)); }, [me?.alerts.telegram_chat_id, me?.alerts.email]);

  useEffect(() => {
    if (me) setAlerts({ enabled: me.alerts.enabled, tg: me.alerts.telegram_chat_id || "", email: me.alerts.email || "", daily: me.alerts.daily_report ?? true });
  }, [me]);
  if (!me) return null;
  const ch = me.alerts.channels ?? { push: true, telegram: true, email: true };
  // why "Send a test" is off, in words that name only what this page has (the Telegram and email boxes show only where the
  // server can send by them; the phone is on the Get the app page)
  const edited = (ch.telegram && alerts.tg.trim() !== (me.alerts.telegram_chat_id || "")) || (ch.email && alerts.email.trim() !== (me.alerts.email || ""));
  const ways = [ch.telegram && "save a Telegram chat ID", ch.email && "save an email address and confirm it", ch.push && "turn on phone notifications"].filter(Boolean) as string[];
  const testWhy: string | null = !canReport ? "Send a test is part of the Basic plan, with the reports and messages."
    : edited ? "Save your changes first; the test goes to what is saved."
    : routes != null && !routes.length ? `Send a test works once alerts have somewhere to go: ${ways.length > 1 ? `${ways.slice(0, -1).join(", ")} or ${ways[ways.length - 1]}` : ways[0] ?? "turn on phone notifications"}.`
    : null;

  const save = async (emailsBackOn = false) => {
    try {
      await api("/me/alerts", { method: "PUT", body: { alerts_enabled: canAlert && alerts.enabled, telegram_chat_id: alerts.tg.trim() || null, alert_email: alerts.email.trim() || null, daily_report: alerts.daily, ...(emailsBackOn ? { alert_emails: true } : {}) } });
      await refreshMe(); setCode("");
      notify(emailsBackOn ? "Alert emails are on again." : "Alert settings saved.");
    } catch (e) { fail(e); }
  };
  const sendCode = async () => {
    try { await api("/me/alerts/telegram/code", { method: "POST" }); notify("Code sent to your Telegram chat."); } catch (e) { fail(e); }
  };
  const confirmCode = async () => {
    try { await api("/me/alerts/telegram/verify", { method: "POST", body: { code: code.trim() } }); setCode(""); await refreshMe(); notify("Telegram chat confirmed."); } catch (e) { fail(e); }
  };
  const tgState = telegramState(me.alerts.telegram_chat_id, alerts.tg, !!me.alerts.telegram_verified);
  const test = async () => {
    const names: Record<string, string> = { push: "phone notification", telegram: "Telegram", email: "email" };
    try {
      const r = await api<{ sent: string[]; failed?: Record<string, string> }>("/me/alerts/test", { method: "POST" });
      const bad = Object.entries(r.failed ?? {});
      setTestNote(null);
      notify(`Test sent by ${r.sent.map((c) => names[c] ?? c).join(" and ")}.` + (bad.length ? ` Not sent by ${bad.map(([c, why]) => `${names[c] ?? c} (${why})`).join(", ")}.` : ""));
    } catch (e) {
      if ((e as ApiError).code === "no_channels" || (e as ApiError).code === "alert_failed") setTestNote((e as Error).message);
      else fail(e);
    }
  };

  return (
    <Card id="alerts" label="Alerts">
      <CardHead title="Alerts" info={HELP.alerts} actions={!canReport ? <Badge tone="warn">Basic</Badge> : undefined} />
      <FormGrid label="Alerts" onSubmit={(e) => { e.preventDefault(); void save(); }}>
        <FieldGroup label="What to send" wide>
          <div className="k-stack">
            {/* off and marked Basic on a plan without it, never ticked-and-grey as if it were on (DP2-030) */}
            <CheckField checked={canReport && alerts.daily} disabled={!canReport} onChange={(on) => setAlerts({ ...alerts, daily: on })}
              label={<>A short report after each market closes{!canReport && <span className="k-inline-badge"><Badge tone="warn">Basic</Badge></span>}</>} />
            <CheckField checked={alerts.enabled} disabled={!canAlert} onChange={(on) => setAlerts({ ...alerts, enabled: on })}
              label={<>A message for every paper trade{!canAlert && <span className="k-inline-badge"><Badge tone="warn">Basic</Badge></span>}</>} />  {/* on Basic, as Plans lists it (R6O-012) */}
          </div>
        </FieldGroup>
        {ch.telegram && <Field label="Telegram chat ID" optional info="Open the StratLab bot and press Start, then message @userinfobot to find your chat ID."
          value={alerts.tg} disabled={!canReport} inputMode="numeric" maxLength={40} onChange={(e) => setAlerts({ ...alerts, tg: e.target.value })} />}
        {ch.telegram && tgState === "verified" && <p className="k-small k-hint-line" data-testid="telegram-verified">Verified</p>}
        {ch.telegram && tgState === "unsaved" && !!alerts.tg.trim() && <p className="k-small k-muted k-hint-line">After you save, we'll send a code to this chat. Enter it here to turn on Telegram alerts.</p>}
        {ch.telegram && tgState === "confirm" && <div className="k-stack" data-testid="telegram-confirm">
          <p className="k-small k-muted k-hint-line">Confirm this chat to keep Telegram alerts: we'll send a code. Until then nothing is sent to it.</p>
          <Field label="Code from Telegram" value={code} inputMode="numeric" maxLength={6} onChange={(e) => setCode(e.target.value)} />
          <FormActions>
            <button type="button" className="btn" disabled={!/^\d{6}$/.test(code.trim())} onClick={() => void confirmCode()}>Confirm</button>
            <button type="button" className="btn outline" onClick={() => void sendCode()}>Send code again</button>
          </FormActions>
        </div>}
        {/* empty, alerts go to the address you sign in with: shown in the box, so an empty box doesn't read as "no email" (DP2-030) */}
        {ch.email && <Field label="Email" optional type="email" value={alerts.email} disabled={!canReport} maxLength={200} placeholder={me.email ?? ""}
          hint={!alerts.email.trim() && me.email ? "Empty: alerts go to the email you sign in with." : undefined} onChange={(e) => setAlerts({ ...alerts, email: e.target.value })} />}
        {/* which alerts this card holds and which are chosen elsewhere: an alert email's "Manage emails" opens the page its
            alerts were set on, and the rest land here (R69-002); across the form's width, not squeezed into one column (DP2-030) */}
        {ch.email && <p className="k-small k-muted k-hint-line k-form-wide" data-testid="alert-where">Price alerts, scan and filing alerts, event
          and money reminders and screen emails are each turned on or off on their own page; they all go to this email.</p>}
        {ch.email && me.alerts.email_off && <p className="k-small k-muted k-hint-line" data-testid="alert-emails-off">Alert emails are off: you used the unsubscribe link in one.{" "}
          {me.alerts.email && <button type="button" className="link" disabled={!canReport} onClick={() => void save(true)}>Turn alert emails back on</button>}</p>}
        <FormActions>
          <button type="submit" className="btn" disabled={!canReport}>Save</button>
          <button type="button" className="btn outline" disabled={!!testWhy} title={testWhy ?? undefined} aria-describedby={testWhy ? "alert-test-why" : undefined} onClick={() => void test()}>Send a test</button>
        </FormActions>
      </FormGrid>
      {/* a disabled test says why, right under the buttons, and only names what is on this page */}
      {testWhy && !testNote && <p id="alert-test-why" className="k-small k-muted k-hint-line" role="status">{testWhy}</p>}
      {!canReport && <PlanNote plan="basic">The report after each close, a message for every paper trade and sending them by Telegram or email are on the Basic plan.</PlanNote>}
      {testNote && <Notice tone="warn" role="status">{testNote}</Notice>}
      {ch.push && <p className="k-small k-muted k-hint-line">The simplest way is a notification on your phone: <Link className="link" to="/app">Get the app</Link> and turn them on.</p>}
    </Card>
  );
}
