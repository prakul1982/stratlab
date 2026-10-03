import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";

export type CalendarStatus = { known_until: string | null; added: string[]; covered_until: string | null; days_left: number | null;
  auto?: { at: string | null; tried_at: string | null; error: string | null; count: number } };

/** India's exchange holidays: how far ahead they're known, and a box to paste the exchange's yearly list. */
export function HolidaysPanel({ status, onSaved }: { status: CalendarStatus; onSaved: (s: CalendarStatus) => void }) {
  const { fail, notify } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const low = status.days_left != null && status.days_left < 60;
  const refresh = async () => {
    setBusy(true);
    try { onSaved(await api<CalendarStatus>("/admin/holidays/refresh", { method: "POST" })); } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const a = status.auto;
  const save = async () => {
    setBusy(true);
    try {
      const s = await api<CalendarStatus>("/admin/holidays", { method: "POST", body: { text } });
      onSaved(s); setText(""); notify(`${s.added.length} holidays saved.`);
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  return (
    <section className="card stack" style={{ gap: 10 }}>
      <h2 className="h2">Exchange holidays (India)</h2>
      <p className={`small ${low ? "neg" : "muted"}`} style={{ margin: 0, maxWidth: "80ch" }}>
        {status.covered_until ? <>Known until <b>{dateOnly(status.covered_until)}</b>{status.days_left != null && ` (${status.days_left} days)`}. </> : "No holiday calendar loaded. "}
        The server reads the exchange's own holiday list every day, so next year's holidays arrive by themselves when the exchange
        publishes them (usually in December). Paper trading, alerts, expiries and the free trial count skip these days.
        {status.added.length > 0 && ` ${status.added.length} added by you.`}
      </p>
      <p className={`small ${a?.error ? "neg" : "muted"}`} style={{ margin: 0 }}>
        {a?.at ? `Last read from the exchange ${ago(a.at)}: ${a.count} holidays.` : "Not read from the exchange yet."}
        {a?.error && ` Last try failed${a.tried_at ? ` ${ago(a.tried_at)}` : ""}: ${a.error}`}
        {low && " Holidays are known for less than 60 days ahead: if the exchange's list isn't out yet, that's expected; otherwise paste it below."}
      </p>
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={refresh}>Read the exchange's list now</button>
      <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Backup, if the exchange can't be reached: paste its list, e.g.\n26-Jan-2027  Republic Day\n06-Mar-2027  Mahashivratri"} aria-label="Holiday list" />
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy || text.trim().length < 8} onClick={save}>{busy ? "Saving…" : "Save holidays"}</button>
    </section>
  );
}
