import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { safeHref } from "../lib/format";
import { Badge, CheckField, EmptyState, ErrorState, Skeleton } from "./kit";

export type Severity = "red" | "amber" | "info";
export interface FilingItem { id: string; at: string; category: string; label: string; severity: Severity; subject: string; text: string; url: string | null }
export interface FilingSummary {
  days: number; total: number; red: number; amber: number; fund_raise: boolean; fund_raise_last: string | null;
  flags: { category: string; label: string; count: number }[];
}
export interface FilingReport { symbol: string; items: FilingItem[]; summary: FilingSummary; window_days: number; lookback_days: number }

const SEV_NAME: Record<Severity, string> = { red: "Red flag", amber: "Look closer", info: "Routine" };

function day(at: string) {
  return new Date(at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function SevBadge({ s, label }: { s: Severity; label: string }) {
  return <span title={SEV_NAME[s]}><Badge tone={s === "red" ? "warn" : "plain"} dot={false}>{s === "red" ? "⚑ " : ""}{label}</Badge></span>;
}

/** The last-3-months verdict in one line: what was found, stated as facts. */
export function SummaryLine({ s }: { s: FilingSummary }) {
  if (!s.total) return <span className="k-small k-muted">No filings in the last {s.days} days.</span>;
  return (
    <span className="k-small">
      Last {s.days} days: <b>{s.red} red flag{s.red === 1 ? "" : "s"}</b>, {s.amber} to look closer at, {s.total} filings in all.{" "}
      {s.fund_raise ? <b>Fund raise filed on {day(s.fund_raise_last!)}.</b> : <span className="k-muted">No fund raise filed.</span>}
    </span>
  );
}

export function FilingRow({ i }: { i: FilingItem }) {
  return (
    <div className="inv-filing">
      <span className="k-note">{day(i.at)}</span>
      <div className="k-stack">
        <div className="k-row"><SevBadge s={i.severity} label={i.label} /><span className="k-small">{i.subject}</span></div>
        {i.text && <span className="k-note inv-clamp">{i.text}</span>}
      </div>
      {i.url ? <a className="link k-small" href={safeHref(i.url)} target="_blank" rel="noopener noreferrer">Filing ↗</a> : <span />}
    </div>
  );
}

/** A company's exchange filings: the 3-month red-flag summary, then the timeline. India only. */
export function FilingsPanel({ symbol }: { symbol: string }) {
  const [rep, setRep] = useState<FilingReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [more, setMore] = useState(false);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setRep(null); setError(null);
    api<FilingReport>(`/research/filings/${encodeURIComponent(symbol)}`)
      .then((r) => live && setRep(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load the filings."));
    return () => { live = false; };
  }, [symbol, tries]);

  if (error) return <ErrorState title="The filings couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>;
  if (!rep) return <Skeleton label="Reading the exchange filings" lines={3} />;
  const shown = rep.items.filter((i) => all || i.severity !== "info");
  const list = more ? shown : shown.slice(0, 8);
  return (
    <div className="k-stack">
      <SummaryLine s={rep.summary} />
      {rep.summary.flags.length > 0 && (
        <div className="k-row">
          {rep.summary.flags.map((f) => <Badge key={f.category} tone="plain" dot={false}>{f.label} ×{f.count}</Badge>)}
        </div>
      )}
      <div className="k-row">
        <CheckField checked={all} onChange={setAll} label="Show routine filings too" />
        <span className="k-note">Last {Math.round(rep.lookback_days / 30)} months · {rep.items.length} filings</span>
      </div>
      {list.length === 0 ? <EmptyState title="Nothing to look at">No red flags or items to look closer at in the last year.</EmptyState>
        : <div className="inv-rows">{list.map((i) => <FilingRow key={i.id} i={i} />)}</div>}
      {shown.length > list.length && <button className="btn quiet sm k-btn-end" onClick={() => setMore(true)}>Show all {shown.length}</button>}
      <p className="k-note">From the company's filings with the exchange. Labels come from fixed keyword rules on each filing's subject; open the filing to read it. Not advice.</p>
    </div>
  );
}
