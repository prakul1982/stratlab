import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { safeHref, fmtDate } from "../lib/format";
import { bizChange, bizValue, periodName } from "../lib/biz";
import { LineChart } from "./Charts";
import { AlertButton } from "./AlertForm";
import { DataTable, EmptyState, Notice, Skeleton } from "./kit";
import { PlanActions } from "./PlanInterest";

/* Monthly and quarterly business updates read into numbers (biz_updates.py): the company's filed figures with the line
 * and page each comes from, the change on the previous month or quarter and on the year, and a 24-month chart. Filed
 * figures only; no estimates and no "beat" or "miss". */

export type Exchange = "NSE" | "BSE";
export interface BizPoint { period: string; value: number; filed_later: boolean; source: { at: string; url: string; page: number | null; quote: string | null; exchange?: Exchange } }
export interface BizMetric {
  key: string; metric: string; segment: string | null; unit: string; basis: string; span: "month" | "quarter"; headline: boolean;
  latest: BizPoint; prev: BizPoint | null; year_ago: BizPoint | null; step: "month" | "quarter";
  change_prev: number | null; change_year: number | null; points: BizPoint[];
}
export interface BizFiling { id: string; at: string; title: string; url: string; read: boolean; period: string | null; problem: string | null; exchange?: Exchange }
export interface BizView {
  symbol: string; filings: BizFiling[]; unread: number; allowed: boolean; metrics: BizMetric[]; headline: string | null;
  problems: string[]; note: string; just_read?: number;
}

export const bizApi = {
  get: (symbol: string) => api<BizView>(`/research/business-updates/${encodeURIComponent(symbol)}`),
  read: (symbol: string) => api<BizView>(`/research/business-updates/${encodeURIComponent(symbol)}/read`, { method: "POST" }),
};

function day(iso: string) {
  const s = fmtDate(iso.slice(0, 10));
  return s === "–" ? iso : s;
}

/** "1 Oct": the day a filing was filed. */
export function filedOn(iso: string | null | undefined) {
  if (!iso) return "Filing";
  const s = fmtDate(iso.slice(0, 10), { year: false });
  return s === "–" ? "Filing" : s;
}

export { bizChange, bizValue, periodName };

export function BizChart({ m, label }: { m: BizMetric; label?: string }) {
  const pts = m.points;
  if (pts.length < 2) return null;
  const name = `${label ? `${label}: ` : ""}${m.metric}${m.segment ? ` (${m.segment})` : ""}`;
  return (
    <LineChart lines={[{ values: pts.map((p) => p.value), color: "var(--blue)", width: 2, label: m.metric }]}
      labels={pts.map((p) => `${periodName(p.period, m.span)}${p.filed_later ? " (as stated a year later)" : ""}`)} height={200}
      format={(v) => bizValue(v, m.unit)} axisFormat={(v) => v.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 })}
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
  if (!v) return wrap(<Skeleton label="Looking for business updates" lines={2} />);
  if (!v.filings.length && !v.metrics.length) return null;

  const read = async () => {
    setBusy(true);
    try { setV(await bizApi.read(symbol)); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const chosen = v.metrics.find((m) => m.key === pick) ?? v.metrics[0];
  const right = v.allowed ? <AlertButton region="IN" symbol={symbol} label="Alert on new updates" condition="bizupdate" /> : null;
  const files = more ? v.filings : v.filings.slice(0, 6);

  return wrap(
    <div className="k-stack biz-updates">
      {v.allowed && v.headline && <p className="k-small"><b>{v.headline}</b>.</p>}
      {v.allowed && v.metrics.length > 0 && (
        <>
          <DataTable label={`${symbol} business update figures`} rows={v.metrics.slice(0, 10)} rowKey={(m) => m.key} rowAttrs={(m) => ({ className: chosen?.key === m.key ? "on" : "" })}
            columns={[
              { key: "f", header: "Figure", rowHeader: true, wrap: true, cell: (m) => (
                <><button className="link-btn" onClick={() => setPick(m.key)} aria-pressed={chosen?.key === m.key}>{m.metric}</button>
                  {m.segment && <span className="k-note"> {m.segment}</span>}
                  <span className="k-sub-line">{m.basis === "period end" ? "at the period's end" : m.basis === "quarter" ? "for the quarter" : "for the month"}</span></>) },
              { key: "l", header: "Latest", numeric: true, cell: (m) => <>{bizValue(m.latest.value, m.unit)}<span className="k-sub-line">{periodName(m.latest.period, m.span)}</span></> },
              { key: "p", header: "On the previous", numeric: true, cell: (m) => <>{bizChange(m.change_prev, m.unit)}{m.prev && <span className="k-sub-line">vs {periodName(m.prev.period, m.span)}</span>}</> },
              { key: "y", header: "On the year", numeric: true, cell: (m) => <>{bizChange(m.change_year, m.unit)}{m.year_ago && <span className="k-sub-line">vs {periodName(m.year_ago.period, m.span)}</span>}</> },
              { key: "s", header: "Source", wrap: true, cell: (m) => (
                <><a className="link" href={safeHref(m.latest.source.url)} target="_blank" rel="noopener noreferrer">{m.latest.source.exchange ?? "Exchange"} filing{m.latest.source.page ? `, p. ${m.latest.source.page}` : ""} ↗</a>
                  {m.latest.source.quote && <span className="k-sub-line inv-clamp" title={m.latest.source.quote}>“{m.latest.source.quote}”</span>}</>) },
            ]} />
          {chosen && <BizChart m={chosen} />}
        </>
      )}
      {!v.allowed && <Notice actions={<PlanActions source="lock" />}>The figures in these updates, read into a table and a 24-month chart with the change on the month and the year, are on the Basic plan.</Notice>}
      {v.allowed && v.unread > 0 && (
        <div className="k-row">
          <span className="k-small k-muted">{v.unread} update{v.unread > 1 ? "s" : ""} not read into numbers yet.</span>
          <button className="btn quiet sm" onClick={read} disabled={busy}>{busy ? "Reading…" : "Read the newest"}</button>
        </div>
      )}
      {files.length > 0 ? (
        <ul className="k-list plain biz-filings k-small" aria-label="Business update filings">
          {files.map((f) => (
            <li key={f.id} className="k-spread">
              <span><span className="k-note">{day(f.at)}</span> {f.title}</span>
              <a className="link" href={safeHref(f.url)} target="_blank" rel="noopener noreferrer">{f.exchange ?? "Exchange"} filing ↗</a>
            </li>))}
        </ul>
      ) : <EmptyState title="No update filings yet">They are listed here as the company files them.</EmptyState>}
      {v.filings.length > files.length && <button className="btn quiet sm k-btn-end" onClick={() => setMore(true)}>Show all {v.filings.length}</button>}
      {v.problems.length > 0 && <p className="k-note">{v.problems.slice(0, 3).join(" · ")}</p>}
      <p className="k-note">{v.note}</p>
    </div>, right);
}
