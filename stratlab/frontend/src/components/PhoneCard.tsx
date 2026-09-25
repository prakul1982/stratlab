import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { canInstall, disablePush, enablePush, install, installed, isIos, onInstallChange, pushOnHere, pushSupported } from "../lib/pwa";

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
    <section className="card stack" style={{ gap: 12 }}>
      <h2 className="h2">On your phone</h2>
      {installed() ? <p className="small muted">StratLab is installed on this device.</p> : (
        <>
          <p className="small muted">Install StratLab like an app: its own icon, full screen, and notifications without Telegram.</p>
          {canInstall() ? <button className="btn outline sm" style={{ alignSelf: "flex-start" }} onClick={() => install()}>Install StratLab</button>
            : <p className="small">{isIos() ? "On an iPhone: tap Share, then Add to Home Screen." : "In Chrome or Edge: open the browser menu and choose Install app (or Add to Home screen)."}</p>}
        </>
      )}
      <div className="stack" style={{ gap: 6 }}>
        <b style={{ fontSize: 14.5 }}>Notifications on this device</b>
        <span className="small muted">Sends {what}. Works in Chrome, Edge and Firefox, and on an iPhone once StratLab is on the Home Screen.</span>
        {on ? <div className="row wrap" style={{ gap: 8 }}>
            <button className="btn outline sm" disabled={busy} onClick={test}>Send a test</button>
            <button className="btn quiet sm" disabled={busy} onClick={turnOff}>Turn off here</button>
          </div>
          : <button className="btn sm" style={{ alignSelf: "flex-start" }} disabled={busy || (!pushSupported() && !isIos())} onClick={turnOn}>{busy ? "Turning on…" : "Turn on notifications"}</button>}
      </div>
    </section>
  );
}
