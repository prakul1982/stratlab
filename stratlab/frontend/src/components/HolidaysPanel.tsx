import { useState } from "react";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, dateOnly } from "../lib/format";

export type MarketCoverage = { market: string; name: string; source: string; known_until: string | null; days_left: number | null;
  next: string | null; next_name: string | null; state: "ok" | "warn" | "none"; hint: string | null };
export type CalendarStatus = { known_until: string | null; added: string[]; covered_until: string | null; days_left: number | null;
  auto?: { at: string | null; tried_at: string | null; error: string | null; count: number }; markets?: MarketCoverage[] };

/** Every market's holidays: where they come from, how far ahead they're known and the next one. */
function CoverageTable({ rows }: { rows: MarketCoverage[] }) {
  return (
    <div className="table-wrap"><table className="holiday-cover">
      <thead><tr><th>Market</th><th>Source</th><th>Known until</th><th>Next holiday</th><th>Status</th></tr></thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.market}>
            <td><b>{r.name}</b></td>
            {r.state === "none" ? <td colSpan={3} className="muted">{r.source}</td> : <>
              <td className="muted">{r.source}</td>
              <td>{r.known_until ? dateOnly(r.known_until) : "–"}{r.days_left != null && <span className="muted"> ({r.days_left} days)</span>}</td>
              <td>{r.next ? <>{dateOnly(r.next)}{r.next_name && <span className="muted"> · {r.next_name}</span>}</> : "–"}</td>
            </>}
            <td>{r.state === "none" ? <span className="muted">–</span>
              : <span className="stack" style={{ gap: 2 }}><span className={`badge ${r.state === "ok" ? "pass" : "warn"}`} style={{ alignSelf: "flex-start" }}>{r.state === "ok" ? "OK" : "Check"}</span>
                {r.hint && <span className="small muted">{r.hint}</span>}</span>}</td>
          </tr>
        ))}
      </tbody>
    </table></div>
  );
}

/** Exchange holidays: a row per market, then India's controls (read the exchange's list now, or paste it as a backup). */
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
      <h2 className="h2">Exchange holidays</h2>
      {status.markets && status.markets.length > 0 && <CoverageTable rows={status.markets} />}
      <h3 className="h3" style={{ margin: "6px 0 0" }}>India</h3>
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
