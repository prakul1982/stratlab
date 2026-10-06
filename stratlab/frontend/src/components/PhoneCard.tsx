import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { canInstall, disablePush, enablePush, install, installed, isIos, onInstallChange, pushOnHere, pushSupported } from "../lib/pwa";
import { Badge, Card, CardHead } from "./kit";

/** Put StratLab on the home screen and get trade alerts and the daily report as phone notifications. */
export function PhoneCard() {
  const { notify, fail, me } = useApp();
  const [, tick] = useState(0);
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => onInstallChange(() => tick((x) => x + 1)), []);
  useEffect(() => { pushOnHere().then(setOn); }, []);
  const feats = me?.plan_info.features;
  const what = feats?.alerts ? "a message for each paper trade and the daily report" : feats?.daily_report ? "the daily report after each market closes" : "alerts, on plans that include them";

  const turnOn = async () => {
    setBusy(true);
    try {
      const problem = await enablePush();
      if (problem) notify(problem); else { setOn(true); notify("Notifications are on for this device."); }
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const test = async () => {
    try {
      const r = await api<{ sent: number }>("/push/test", { method: "POST" });
      notify(r.sent ? "Test sent. It should appear in a few seconds." : "Nothing was sent: turn notifications off and on again on this device.");
    } catch (e) { fail(e); }
  };
  const turnOff = async () => {
    setBusy(true);
    try { await disablePush(); setOn(false); notify("Notifications are off for this device."); } catch (e) { fail(e); } finally { setBusy(false); }
  };

  return (
    <>
      <Card label="Install StratLab">
        <CardHead title="Install StratLab" actions={installed() ? <Badge tone="ok">Installed</Badge> : undefined} />
        {installed() ? <p className="k-small k-muted">StratLab is installed on this device.</p> : (
          <>
            <p className="k-small k-muted">Install StratLab like an app: its own icon, full screen, and notifications without Telegram.</p>
            {canInstall() ? <button type="button" className="btn outline k-btn-end" onClick={() => void install()}>Install StratLab</button>
              : <p className="k-small">{isIos() ? "On an iPhone: tap Share, then Add to Home Screen." : "In Chrome or Edge: open the browser menu and choose Install app (or Add to Home screen)."}</p>}
          </>
        )}
      </Card>
      <Card label="Notifications on this device">
        <CardHead title="Notifications on this device" actions={on ? <Badge tone="ok">On</Badge> : undefined} />
        <p className="k-small k-muted">Sends {what}. Works in Chrome, Edge and Firefox, and on an iPhone once StratLab is on the Home Screen.</p>
        {on ? <div className="k-row">
            <button type="button" className="btn outline" disabled={busy} onClick={() => void test()}>Send a test</button>
            <button type="button" className="btn quiet" disabled={busy} onClick={() => void turnOff()}>Turn off here</button>
          </div>
          : <button type="button" className="btn k-btn-end" disabled={busy || (!pushSupported() && !isIos())} onClick={() => void turnOn()}>{busy ? "Turning on…" : "Turn on notifications"}</button>}
      </Card>
    </>
  );
}
