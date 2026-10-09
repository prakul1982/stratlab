import { useState } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { ago, dateOnly } from "../../lib/format";
import { holidaysSaved } from "./holidays";
import { Card, CardHead, DataTable, FormActions, Light, Notice, type Column } from "../../components/kit";

export type MarketCoverage = { market: string; name: string; source: string; known_until: string | null; days_left: number | null;
  next: string | null; next_name: string | null; state: "ok" | "warn" | "none"; hint: string | null };
export type CalendarStatus = { known_until: string | null; added: string[]; by_hand?: string[]; covered_until: string | null; days_left: number | null;
  auto?: { at: string | null; tried_at: string | null; error: string | null; count: number }; markets?: MarketCoverage[] };

const COLUMNS: Column<MarketCoverage>[] = [
  { key: "m", header: "Market", rowHeader: true, cell: (r) => r.name },
  { key: "s", header: "Source", wrap: true, cell: (r) => <span className="k-muted">{r.source}</span> },
  { key: "k", header: "Known until", cell: (r) => (r.state === "none" ? "–" : <>{r.known_until ? dateOnly(r.known_until) : "–"}{r.days_left != null && <span className="k-muted"> ({r.days_left} days)</span>}</>) },
  { key: "n", header: "Next holiday", wrap: true, cell: (r) => (r.state === "none" ? "–" : r.next ? <>{dateOnly(r.next)}{r.next_name && <span className="k-muted"> · {r.next_name}</span>}</> : "–") },
  { key: "st", header: "Status", wrap: true, cell: (r) => (r.state === "none" ? <span className="k-muted">–</span>
    : <span className="k-stack"><Light state={r.state === "ok" ? "ok" : "warn"} />{r.hint && <span className="k-note k-muted">{r.hint}</span>}</span>) },
];

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
    <Card label="Exchange holidays">
      <CardHead title="Exchange holidays" actions={<button type="button" className="btn quiet sm" disabled={busy} onClick={refresh}>Read the exchange's list now</button>} />
      {status.markets && status.markets.length > 0 && <DataTable label="Holidays by market" rows={status.markets} rowKey={(r) => r.market} columns={COLUMNS} />}
      <h3 className="adm-sub">India</h3>
      <p className={`k-small ${low ? "k-down" : "k-muted"}`}>
        {status.covered_until ? <>Known until <b>{dateOnly(status.covered_until)}</b>{status.days_left != null && ` (${status.days_left} days)`}. </> : "No holiday calendar loaded. "}
        The server reads the exchange's own holiday list every day, so next year's holidays arrive by themselves when the exchange
        publishes them (usually in December). Paper trading, alerts, expiries and the free trial count skip these days.
        {status.added.length > 0 && ` ${holidaysSaved(status.added.length, status.by_hand ? status.by_hand.length : null)}`}
      </p>
      <p className={`k-small ${a?.error ? "k-down" : "k-muted"}`}>
        {a?.at ? `Last read from the exchange ${ago(a.at)}: ${a.count} holidays.` : "Not read from the exchange yet."}
        {a?.error && ` Last try failed${a.tried_at ? ` ${ago(a.tried_at)}` : ""}: ${a.error}`}
      </p>
      {low && <Notice tone="warn">Holidays are known for less than 60 days ahead. If the exchange's list isn't out yet, that's expected; otherwise paste it below.</Notice>}
      <textarea className="k-input" rows={4} value={text} onChange={(e) => setText(e.target.value)} aria-label="Holiday list"
        placeholder={"Backup, if the exchange can't be reached: paste its list, e.g.\n26-Jan-2027  Republic Day\n06-Mar-2027  Mahashivratri"} />
      <FormActions><button type="button" className="btn quiet sm" disabled={busy || text.trim().length < 8} onClick={save}>{busy ? "Saving…" : "Save holidays"}</button></FormActions>
    </Card>
  );
}
