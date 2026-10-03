import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";

type Prefs = { tips: boolean; email: string | null };

/** Account → Emails from StratLab: tips and reminders (a welcome, trial and offer reminders, what's new) can be
 *  turned off; receipts always go. Saves on each change. */
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
    <section className="card stack" style={{ gap: 12 }} id="emails">
      <h2 className="h2">Emails from StratLab</h2>
      <label className="row" style={{ gap: 10, fontWeight: 600, minHeight: 36 }}>
        <input type="checkbox" style={{ width: 20, height: 20 }} checked={prefs.tips} disabled={busy} onChange={(e) => set(e.target.checked)} />
        Tips and reminders
      </label>
      <p className="small muted" style={{ margin: 0 }}>
        A welcome, a nudge to test your first strategy, a reminder before your trial or the launch offer ends, and what's new
        if you've been away. Each comes once{prefs.email ? <>, to <b style={{ overflowWrap: "anywhere" }}>{prefs.email}</b></> : ""}.
        Payment receipts always come.
      </p>
    </section>
  );
}
