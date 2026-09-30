import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { Loading } from "./ui";

export type Severity = "red" | "amber" | "info";
export interface FilingItem { id: string; at: string; category: string; label: string; severity: Severity; subject: string; text: string; url: string | null }
export interface FilingSummary {
  days: number; total: number; red: number; amber: number; fund_raise: boolean; fund_raise_last: string | null;
  flags: { category: string; label: string; count: number }[];
}
export interface FilingReport { symbol: string; items: FilingItem[]; summary: FilingSummary; window_days: number; lookback_days: number }

export const SEV_NAME: Record<Severity, string> = { red: "Red flag", amber: "Look closer", info: "Routine" };

export function day(at: string) {
  return new Date(at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function SevBadge({ s, label }: { s: Severity; label: string }) {
  return <span className={`badge ${s === "red" ? "fail" : s === "amber" ? "warn" : "skip"}`} title={SEV_NAME[s]}>{s === "red" ? "⚑ " : ""}{label}</span>;
}

/** The last-3-months verdict in one line: what was found, stated as facts. */
export function SummaryLine({ s }: { s: FilingSummary }) {
  if (!s.total) return <span className="small muted">No filings in the last {s.days} days.</span>;
  return (
    <span className="small">
      Last {s.days} days: <b>{s.red} red flag{s.red === 1 ? "" : "s"}</b>, {s.amber} to look closer at, {s.total} filings in all.{" "}
      {s.fund_raise ? <b>Fund raise filed on {day(s.fund_raise_last!)}.</b> : <span className="muted">No fund raise filed.</span>}
    </span>
  );
}

export function FilingRow({ i }: { i: FilingItem }) {
  return (
    <div className="filing">
      <span className="tiny muted mono">{day(i.at)}</span>
      <div className="stack" style={{ gap: 3, minWidth: 0 }}>
        <div className="row wrap" style={{ gap: 8 }}><SevBadge s={i.severity} label={i.label} /><span className="small">{i.subject}</span></div>
        {i.text && <span className="tiny muted filing-text">{i.text}</span>}
      </div>
      {i.url ? <a className="link tiny" href={i.url} target="_blank" rel="noopener noreferrer">Filing ↗</a> : <span />}
    </div>
  );
}

/** A company's exchange filings: the 3-month red-flag summary, then the timeline. India only. */
export function FilingsPanel({ symbol }: { symbol: string }) {
  const { me } = useApp();
  const pro = !!me?.plan_info?.features?.filings;
  const [rep, setRep] = useState<FilingReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [all, setAll] = useState(false);
  const [more, setMore] = useState(false);

  useEffect(() => {
    if (!pro) return;
    let live = true;
    setRep(null); setError(null);
    api<FilingReport>(`/research/filings/${encodeURIComponent(symbol)}`)
      .then((r) => live && setRep(r))
      .catch((e) => live && setError(e instanceof Error ? e.message : "Couldn't load the filings."));
    return () => { live = false; };
  }, [symbol, pro]);

  if (!pro) return <p className="small muted">Filings and red flags (QIP and other fund raises, pledges, resignations, defaults) are on the Pro plan. <Link className="link" to="/plans">See plans</Link></p>;
  if (error) return <p className="small muted">{error}</p>;
  if (!rep) return <Loading label="Reading the exchange filings" />;
  const shown = rep.items.filter((i) => all || i.severity !== "info");
  const list = more ? shown : shown.slice(0, 8);
  return (
    <div className="stack" style={{ gap: 12 }}>
      <SummaryLine s={rep.summary} />
      {rep.summary.flags.length > 0 && (
        <div className="row wrap" style={{ gap: 6 }}>
          {rep.summary.flags.map((f) => <span key={f.category} className="chip-note">{f.label} ×{f.count}</span>)}
        </div>
      )}
      <div className="row wrap small" style={{ gap: 12 }}>
        <label className="row" style={{ gap: 6 }}><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />Show routine filings too</label>
        <span className="tiny muted">Last {Math.round(rep.lookback_days / 30)} months · {rep.items.length} filings</span>
      </div>
      {list.length === 0 ? <p className="small muted">No red flags or items to look closer at in the last year.</p>
        : <div className="filings">{list.map((i) => <FilingRow key={i.id} i={i} />)}</div>}
      {shown.length > list.length && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setMore(true)}>Show all {shown.length}</button>}
      <p className="tiny muted" style={{ margin: 0 }}>From the company's filings with the exchange. Labels come from fixed keyword rules on each filing's subject; open the filing to read it. Not advice.</p>
    </div>
  );
}
