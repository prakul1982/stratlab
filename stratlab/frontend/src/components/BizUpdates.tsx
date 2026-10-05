import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { safeHref } from "../lib/format";
import { LineChart } from "./Charts";
import { AlertButton } from "./AlertForm";
import { Loading } from "./ui";

/* Monthly and quarterly business updates read into numbers (biz_updates.py): the company's filed figures with the line
 * and page each comes from, the change on the previous month or quarter and on the year, and a 24-month chart. Filed
 * figures only; no estimates and no "beat" or "miss". */

export interface BizPoint { period: string; value: number; filed_later: boolean; source: { at: string; url: string; page: number | null; quote: string | null } }
export interface BizMetric {
  key: string; metric: string; segment: string | null; unit: string; basis: string; span: "month" | "quarter"; headline: boolean;
  latest: BizPoint; prev: BizPoint | null; year_ago: BizPoint | null; step: "month" | "quarter";
  change_prev: number | null; change_year: number | null; points: BizPoint[];
}
export interface BizFiling { id: string; at: string; title: string; url: string; read: boolean; period: string | null; problem: string | null }
export interface BizView {
  symbol: string; filings: BizFiling[]; unread: number; allowed: boolean; metrics: BizMetric[]; headline: string | null;
  problems: string[]; note: string; just_read?: number;
}

export const bizApi = {
  get: (symbol: string) => api<BizView>(`/research/business-updates/${encodeURIComponent(symbol)}`),
  read: (symbol: string) => api<BizView>(`/research/business-updates/${encodeURIComponent(symbol)}/read`, { method: "POST" }),
};

/** "Sep 2026", or "Q2 FY27" for a quarter (Indian financial year). */
export function periodName(p: string, span: "month" | "quarter" = "month") {
  const [y, m] = p.split("-").map(Number);
  if (!y || !m) return p;
  if (span === "quarter") {
    const q = ({ 6: 1, 9: 2, 12: 3, 3: 4 } as Record<number, number>)[m];
    if (q) return `Q${q} FY${String((m >= 4 ? y + 1 : y) % 100).padStart(2, "0")}`;
  }
  return new Date(y, m - 1, 1).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}

/** 2,36,013 units, ₹33,275 billion, 34.2%: the unit as filed, Indian digit grouping. */
export function bizValue(v: number | null | undefined, unit: string | null) {
  if (v == null || !Number.isFinite(v)) return "–";
  const n = v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  const u = (unit ?? "").trim();
  if (u === "%") return `${n}%`;
  if (u.startsWith("₹")) return `₹${n} ${u.slice(1).trim()}`.trim();
  return `${n} ${u}`.trim();
}

/** "+24.4%", or "+1.2 pts" for a figure that is itself a percent. Plain text, no colour: a change, not a verdict. */
export function bizChange(c: number | null | undefined, unit: string | null) {
  if (c == null) return "–";
  const s = c > 0 ? "+" : c < 0 ? "−" : "";
  return (unit ?? "").includes("%") ? `${s}${Math.abs(c).toFixed(2)} pts` : `${s}${Math.abs(c).toFixed(1)}%`;
}

function day(iso: string) {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function BizChart({ m, label }: { m: BizMetric; label?: string }) {
  const pts = m.points;
  if (pts.length < 2) return null;
  const name = `${label ? `${label}: ` : ""}${m.metric}${m.segment ? ` (${m.segment})` : ""}`;
  return (
    <LineChart lines={[{ values: pts.map((p) => p.value), color: "var(--blue)", width: 2, label: m.metric }]}
      labels={pts.map((p) => `${periodName(p.period, m.span)}${p.filed_later ? " (as stated a year later)" : ""}`)} height={200}
      format={(v) => bizValue(v, m.unit)} axisFormat={(v) => v.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 1 })}
      ariaLabel={`${name} by ${m.span === "quarter" ? "quarter" : "month"}, ${periodName(pts[0].period, m.span)} to ${periodName(pts[pts.length - 1].period, m.span)}`} />
  );
}

/** The company page's and the deep dive's panel. Nothing at all for a company that files no business updates. */
export function BizUpdatesPanel({ symbol, wrap }: { symbol: string; wrap: (body: React.ReactNode, right?: React.ReactNode) => React.ReactNode }) {
  const [v, setV] = useState<BizView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState<string | null>(null);
  const [more, setMore] = useState(false);

  useEffect(() => {
    let live = true;
    setV(null); setError(null); setPick(null);
    bizApi.get(symbol).then((x) => live && setV(x)).catch((e) => live && setError((e as Error).message));
    return () => { live = false; };
  }, [symbol]);

  if (error) return null;                       // a side panel: the filings panel already says when the exchange is down
  if (!v) return wrap(<Loading label="Looking for business updates" />);
  if (!v.filings.length && !v.metrics.length) return null;

  const read = async () => {
    setBusy(true);
    try { setV(await bizApi.read(symbol)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const chosen = v.metrics.find((m) => m.key === pick) ?? v.metrics[0];
  const right = v.allowed ? <AlertButton region="IN" symbol={symbol} label="Alert on new updates" condition="bizupdate" /> : null;
  const files = more ? v.filings : v.filings.slice(0, 6);

  return wrap(
    <div className="stack biz-updates" style={{ gap: 14 }}>
      {v.allowed && v.headline && <p className="small" style={{ margin: 0 }}><b>{v.headline}</b>.</p>}
      {v.allowed && v.metrics.length > 0 && (
        <>
          <div className="table-wrap">
            <table className="biz-table" aria-label={`${symbol} business update figures`}>
              <thead><tr><th style={{ textAlign: "left" }}>Figure</th><th>Latest</th><th>On the previous</th><th>On the year</th><th>Source</th></tr></thead>
              <tbody>{v.metrics.slice(0, 10).map((m) => (
                <tr key={m.key} className={chosen?.key === m.key ? "on" : undefined}>
                  <td style={{ textAlign: "left" }}>
                    <button className="link-btn" onClick={() => setPick(m.key)} aria-pressed={chosen?.key === m.key}>{m.metric}</button>
                    {m.segment && <span className="tiny muted"> {m.segment}</span>}
                    <div className="tiny muted">{m.basis === "period end" ? "at the period's end" : m.basis === "quarter" ? "for the quarter" : "for the month"}</div>
                  </td>
                  <td className="num">{bizValue(m.latest.value, m.unit)}<div className="tiny muted">{periodName(m.latest.period, m.span)}</div></td>
                  <td className="num">{bizChange(m.change_prev, m.unit)}{m.prev && <div className="tiny muted">vs {periodName(m.prev.period, m.span)}</div>}</td>
                  <td className="num">{bizChange(m.change_year, m.unit)}{m.year_ago && <div className="tiny muted">vs {periodName(m.year_ago.period, m.span)}</div>}</td>
                  <td className="small"><a className="link" href={safeHref(m.latest.source.url)} target="_blank" rel="noopener noreferrer">
                    Filing{m.latest.source.page ? `, p. ${m.latest.source.page}` : ""} ↗</a>
                    {m.latest.source.quote && <div className="tiny muted biz-quote" title={m.latest.source.quote}>“{m.latest.source.quote}”</div>}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          {chosen && <BizChart m={chosen} />}
        </>
      )}
      {!v.allowed && <p className="small" style={{ margin: 0 }}>The figures in these updates, read into a table and a 24-month chart with the
        change on the month and the year, are on the <Link className="link" to="/plans">Basic plan</Link>.</p>}
      {v.allowed && v.unread > 0 && (
        <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
          <span className="small muted">{v.unread} update{v.unread > 1 ? "s" : ""} not read into numbers yet.</span>
          <button className="btn quiet sm" onClick={read} disabled={busy}>{busy ? "Reading…" : "Read the newest"}</button>
        </div>
      )}
      <ul className="biz-filings small" aria-label="Business update filings">
        {files.map((f) => (
          <li key={f.id} className="spread" style={{ gap: 10 }}>
            <span><span className="mono tiny muted">{day(f.at)}</span> {f.title}</span>
            <a className="link" href={safeHref(f.url)} target="_blank" rel="noopener noreferrer">Filing ↗</a>
          </li>))}
      </ul>
      {v.filings.length > files.length && <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={() => setMore(true)}>Show all {v.filings.length}</button>}
      {v.problems.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>{v.problems.slice(0, 3).join(" · ")}</p>}
      <p className="tiny muted" style={{ margin: 0 }}>{v.note}</p>
    </div>, right);
}
