import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { Card, CardHead, CheckField } from "./kit";

type Prefs = { tips: boolean; email: string | null };

/** Settings → Notifications → Emails from StratLab: tips and reminders (a welcome, trial and offer reminders, what's new)
 *  can be turned off; receipts always go. Saves on each change. */
export function TipsCard() {
  const { notify, fail } = useApp();
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let live = true;
    api<Prefs>("/me/emails").then((p) => { if (live && p && typeof p.tips === "boolean") setPrefs(p); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  if (!prefs) return null;

  const set = async (tips: boolean) => {
    const before = prefs;
    setPrefs({ ...prefs, tips });
    setBusy(true);
    try {
      const p = await api<Prefs>("/me/emails", { method: "PUT", body: { tips } });
      if (p && typeof p.tips === "boolean") setPrefs(p);
      notify(tips ? "Tips and reminders are on." : "Tips and reminders are off. Receipts still come.");
    } catch (e) { setPrefs(before); fail(e); } finally { setBusy(false); }
  };

  return (
    <Card id="emails" label="Emails from StratLab">
      <CardHead title="Emails from StratLab" />
      <CheckField label="Tips and reminders" checked={prefs.tips} disabled={busy} onChange={(on) => void set(on)} />
      <p className="k-small k-muted k-hint-line">
        A welcome, a nudge to test your first strategy, a reminder before your trial or the launch offer ends, and what's new
        if you've been away. Each comes once{prefs.email ? <>, to <b>{prefs.email}</b></> : ""}.
        Payment receipts always come.
      </p>
    </Card>
  );
}
