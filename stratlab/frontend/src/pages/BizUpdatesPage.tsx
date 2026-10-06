import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { safeHref } from "../lib/format";
import { bizChange, bizValue, periodName } from "../components/BizUpdates";
import { Card, CardHead, ChipBar, DataTable, EmptyState, ErrorState, PageHeader, PlanNote, Seg, Skeleton } from "../components/kit";

/* Business updates side by side: the latest monthly (automakers) or quarterly (banks and lenders) headline figure each
 * company filed, with the change on the previous period and on the year, alphabetically. No ranking: each company's
 * total is its own, defined its own way. */

interface SectorRow {
  symbol: string; name: string; metric: string | null; unit: string | null; span: "month" | "quarter"; period: string | null; value: number | null;
  change_prev: number | null; change_year: number | null; step: "month" | "quarter" | null; filed: string | null; url: string | null;
}
interface Sector { sector: string; label: string; rows: SectorRow[]; sectors: { id: string; label: string }[]; note: string }

export function BizUpdatesPage() {
  const [params, setParams] = useSearchParams();
  const sector = params.get("sector") ?? "autos";
  const [d, setD] = useState<Sector | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [locked, setLocked] = useState(false);
  const [tries, setTries] = useState(0);

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
        lede="Monthly sales from automakers and quarterly deposits and advances from banks and lenders, as each company filed them with the exchange, read into numbers with the change on the previous period and on the year. Facts, not advice." />
      {locked ? (
        <PlanNote>The sector view of business updates is on the Basic plan. Each company page lists its own update filings for everyone.</PlanNote>
      ) : error ? <ErrorState title="The business updates couldn't be read" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState>
        : !d ? <Card><Skeleton label="Reading the business updates" lines={4} /></Card> : (
        <>
          <div className="k-toolbar">
            {choices.length <= 4 ? <Seg label="Sector" value={sector} onChange={pick} options={choices} /> : <ChipBar label="Sector" value={sector} onChange={pick} options={choices} />}
          </div>
          <Card>
            <CardHead title={d.label} info="Each filing is read once: the figures are copied from the company's own document and kept only when the line they come from is found in it. Each company's page shows the line, the page and its 24-month chart." infoLabel="How the figures are read" />
            {filed.length === 0 ? <EmptyState title="Nothing read into numbers yet">No update in this list has been read into numbers yet. They are read each evening after they're filed.</EmptyState> : (
              <DataTable label={d.label} rows={filed} rowKey={(r) => r.symbol} sticky={filed.length > 14} rowAttrs={(r) => ({ "data-company": r.symbol })}
                columns={[
                  { key: "c", header: "Company", rowHeader: true, wrap: true, cell: (r) => <><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#business-updates`}><b>{r.name}</b></Link><span className="k-sub-line">{r.metric}</span></> },
                  { key: "v", header: "Latest figure", numeric: true, cell: (r) => <>{bizValue(r.value, r.unit)}<span className="k-sub-line">{r.period ? periodName(r.period, r.span) : ""}</span></> },
                  { key: "p", header: "On the previous", numeric: true, cell: (r) => bizChange(r.change_prev, r.unit) },
                  { key: "y", header: "On the year", numeric: true, cell: (r) => bizChange(r.change_year, r.unit) },
                  { key: "f", header: "Filed", cell: (r) => (r.url ? <a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">{r.filed ? new Date(`${r.filed.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "Filing"} ↗</a> : "–") },
                ]} />
            )}
            {waiting.length > 0 && <p className="k-note">Not read yet: {waiting.map((r) => r.name).join(", ")}.</p>}
            <p className="k-note">{d.note}</p>
          </Card>
        </>
      )}
    </div>
  );
}
