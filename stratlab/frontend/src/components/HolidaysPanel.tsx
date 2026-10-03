import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { dateOnly } from "../lib/format";

export type CalendarStatus = { known_until: string | null; added: string[]; covered_until: string | null; days_left: number | null };

/** India's exchange holidays: how far ahead they're known, and a box to paste the exchange's yearly list. */
export function HolidaysPanel({ status, onSaved }: { status: CalendarStatus; onSaved: (s: CalendarStatus) => void }) {
  const { fail, notify } = useApp();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const low = status.days_left != null && status.days_left < 60;
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
        {low ? "Paste the exchange's holiday list for next year below, or holidays after that date will be treated as trading days (paper trading, alerts, expiries and the trial count)."
          : "Paper trading, alerts, expiries and the free trial count skip these days. Paste next year's list when the exchange publishes it (usually in December)."}
        {status.added.length > 0 && ` ${status.added.length} added by you.`}
      </p>
      <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"Paste the exchange's list, e.g.\n26-Jan-2027  Republic Day\n06-Mar-2027  Mahashivratri"} aria-label="Holiday list" />
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} disabled={busy || text.trim().length < 8} onClick={save}>{busy ? "Saving…" : "Save holidays"}</button>
    </section>
  );
}
