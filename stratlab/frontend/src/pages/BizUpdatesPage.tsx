import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { safeHref } from "../lib/format";
import { bizChange, bizValue, filedOn, periodName, type Exchange } from "../components/BizUpdates";
import { Badge, Card, CardHead, ChipBar, DataTable, EmptyState, ErrorState, PageHeader, PlanNote, Seg, Skeleton, type Column } from "../components/kit";

/* Business updates: the latest monthly or quarterly headline figure each company filed (NSE and BSE filings), with the change
 * on the previous period and on the year. First "My stocks" (your holdings, then your watchlist), then a sector side by side
 * and, under it, the same companies month by month with the change on the same month a year earlier. Alphabetical, never
 * ranked: each company's total is its own, defined its own way. Every figure links to the filing it was read from. */

interface SectorRow {
  symbol: string; name: string; metric: string | null; unit: string | null; span: "month" | "quarter" | null; period: string | null; value: number | null;
  change_prev: number | null; change_year: number | null; step: "month" | "quarter" | null; filed: string | null; url: string | null;
  page: number | null; exchange: Exchange | null; reads: number; read_ok: number;
}
interface CompareCell { value: number; year_change: number | null; year_ago: number | null; url: string; page: number | null; exchange: Exchange | null; filed: string }
interface CompareColumn { symbol: string; name: string; metric: string | null; unit: string | null; step: "month" | "quarter" | null; points: Record<string, CompareCell> }
interface Compare { periods: string[]; companies: CompareColumn[]; without: string[]; note: string }
interface Sector { sector: string; label: string; rows: SectorRow[]; sectors: { id: string; label: string }[]; note: string; compare: Compare }
interface MineRow extends SectorRow { kind: "holding" | "watchlist" }
interface Mine { rows: MineRow[]; without: { symbol: string; name: string; kind: "holding" | "watchlist" }[]; note: string }

const kindName = (k: "holding" | "watchlist") => (k === "holding" ? "Holding" : "Watchlist");

/** The company, its figure and the period it is for, the changes, and the filing it came from: the same columns in My stocks and in a sector. */
function figureColumns(extra?: Column<SectorRow>): Column<SectorRow>[] {
  const cols: Column<SectorRow>[] = [
    { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (r) => <><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#business-updates`}><b>{r.name}</b></Link><span className="k-sub-line">{r.metric}</span></> },
    { key: "v", header: "Latest figure", numeric: true, cell: (r) => <>{bizValue(r.value, r.unit)}<span className="k-sub-line">{r.period ? periodName(r.period, r.span ?? "month") : ""}</span></> },
    { key: "p", header: "On the previous", numeric: true, cell: (r) => bizChange(r.change_prev, r.unit) },
    { key: "y", header: "On the year", numeric: true, cell: (r) => bizChange(r.change_year, r.unit) },
    { key: "f", header: "Filing", cell: (r) => (r.url ? <a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">{filedOn(r.filed)}{r.exchange ? ` · ${r.exchange}` : ""}{r.page ? `, p. ${r.page}` : ""} ↗</a> : "–") },
  ];
  if (extra) cols.splice(1, 0, extra);
  return cols;
}

export function BizUpdatesPage() {
  const [params, setParams] = useSearchParams();
  const sector = params.get("sector") ?? "autos";
  const [d, setD] = useState<Sector | null>(null);
  const [mine, setMine] = useState<Mine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    api<Mine>("/invest/business-updates/mine").then((x) => live && setMine(x)).catch(() => live && setMine(null));
    return () => { live = false; };
  }, [tries]);
  useEffect(() => {
    let live = true;
    setD(null); setError(null);
    api<Sector>(`/invest/business-updates?sector=${encodeURIComponent(sector)}`)
      .then((x) => live && setD(x))
      .catch((e) => { if (!live) return; if ((e as ApiError).status === 402) setLocked(true); else setError((e as Error).message); });
    return () => { live = false; };
  }, [sector, tries]);

  const pick = (id: string) => { const p = new URLSearchParams(params); p.set("sector", id); setParams(p, { replace: true }); };
  const filed = (d?.rows ?? []).filter((r) => r.value != null);
  const waiting = (d?.rows ?? []).filter((r) => r.value == null);
  const choices = (d?.sectors ?? []).map((s) => ({ value: s.id, label: s.label }));

  return (
    <div className="k-page biz-page">
      <PageHeader eyebrow={eyebrowOf("/invest/business-updates")} title="Business updates"
        lede="Monthly and quarterly figures companies file with the exchanges (NSE and BSE): automakers' sales, banks' deposits and advances, cement, airlines and airports, power, telecom, metals and retail. Read into numbers, each linked to its filing. Facts, not advice." />
      {locked ? (
        <PlanNote>The sector view of business updates is on the Basic plan. Each company page lists its own update filings for everyone.</PlanNote>
      ) : error ? <ErrorState title="The business updates couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>
        : !d ? <Card><Skeleton label="Reading the business updates" lines={4} /></Card> : (
        <>
          {mine && (
            <Card label="My stocks" testId="biz-mine">
              <CardHead title="My stocks" info="Your holdings first, then your watchlist: the Indian stocks that have business updates read into numbers. A stock with none read yet is named below the table." infoLabel="About my stocks" />
              {mine.rows.length === 0
                ? <EmptyState title="None of your stocks has a business update read yet">{mine.without.length ? `${mine.without.length} of your stocks are waiting to be read: they are read each evening after they're filed.` : "Add holdings or star companies in Research and their updates appear here."}</EmptyState>
                : <DataTable label="My stocks' latest business updates" rows={mine.rows} rowKey={(r) => r.symbol} rowAttrs={(r) => ({ "data-company": r.symbol })}
                    columns={figureColumns({ key: "k", header: "From", cell: (r) => <Badge tone="plain" dot={false}>{kindName((r as MineRow).kind)}</Badge> })} />}
              {mine.rows.length > 0 && mine.without.length > 0 && <p className="k-note">Not read yet: {mine.without.map((x) => x.name).join(", ")}.</p>}
              <p className="k-note">{mine.note}</p>
            </Card>
          )}
          <div className="k-toolbar">
            {choices.length <= 4 ? <Seg label="Sector" value={sector} onChange={pick} options={choices} /> : <ChipBar label="Sector" value={sector} onChange={pick} options={choices} />}
          </div>
          <Card>
            <CardHead title={d.label} info="Each filing is read once: the figures are copied from the company's own document and kept only when the line they come from is found in it. Each company's page shows the line, the page and its 24-month chart." infoLabel="How the figures are read" />
            {filed.length === 0 ? <EmptyState title="Nothing read into numbers yet">No update in this list has been read into numbers yet. They are read each evening after they're filed.</EmptyState> : (
              <DataTable label={d.label} rows={filed} rowKey={(r) => r.symbol} sticky={filed.length > 14} rowAttrs={(r) => ({ "data-company": r.symbol })}
                columns={[...figureColumns(), { key: "r", header: "Filings read", numeric: true, info: "How many of this company's update filings were read into figures that could be checked against the document.", cell: (r) => `${r.read_ok} of ${r.reads}` }]} />
            )}
            {waiting.length > 0 && <p className="k-note">Not read yet: {waiting.map((r) => r.name).join(", ")}.</p>}
            <p className="k-note">{d.note}</p>
          </Card>
          <Compare c={d.compare} label={d.label} />
        </>
      )}
    </div>
  );
}

/** The sector's companies side by side, month by month (newest first): each cell its figure and the change on the same month a year earlier. */
function Compare({ c, label }: { c: Compare; label: string }) {
  const cols: Column<string>[] = [
    { key: "m", header: "Month", rowHeader: true, cell: (p) => periodName(p, "month") },
    ...c.companies.map((co) => ({
      key: co.symbol, numeric: true, header: <>{co.name}<span className="k-sub-line">{co.metric}{co.unit ? ` · ${co.unit}` : ""}</span></>,
      cell: (p: string) => {
        const x = co.points[p];
        if (!x) return <span className="k-muted">–</span>;
        return <>
          <a className="link" href={safeHref(x.url)} target="_blank" rel="noopener noreferrer" title={`Filed ${filedOn(x.filed)} on ${x.exchange ?? "the exchange"}${x.page ? `, page ${x.page}` : ""}`}>{bizValue(x.value, co.unit)}</a>
          <span className="k-sub-line">{x.year_change == null ? "no year-ago figure" : `${bizChange(x.year_change, co.unit)} on the year`}</span>
        </>;
      } })),
  ];
  return (
    <Card label="Month by month" testId="biz-compare">
      <CardHead title={`${label}: month by month`} info="Each company's own headline figure for each month, in its own unit, with the change on the same month a year earlier. Each figure links to the filing it was read from. Quarterly filers have a figure in the last month of each quarter." infoLabel="About this comparison" />
      {c.companies.length === 0
        ? <EmptyState title="No month to compare yet">Once companies in this list have updates read into numbers, they appear here side by side, month by month.</EmptyState>
        : <DataTable label={`${label}, month by month`} rows={c.periods} rowKey={(p) => p} columns={cols} sticky={c.periods.length > 14} />}
      {c.without.length > 0 && c.companies.length > 0 && <p className="k-note">No figures yet: {c.without.join(", ")}.</p>}
      <p className="k-note">{c.note}</p>
    </Card>
  );
}
