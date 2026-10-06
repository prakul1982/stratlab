import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { safeHref } from "../lib/format";
import { RegionSwitch } from "../components/Research";
import { bizChange, bizValue, periodName } from "../components/BizUpdates";
import { Info, Loading } from "../components/ui";

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

  useEffect(() => {
    let live = true;
    setD(null); setError(null);
    api<Sector>(`/invest/business-updates?sector=${encodeURIComponent(sector)}`)
      .then((x) => live && setD(x))
      .catch((e) => { if (!live) return; if ((e as ApiError).status === 402) setLocked(true); else setError((e as Error).message); });
    return () => { live = false; };
  }, [sector]);

  const pick = (id: string) => { const p = new URLSearchParams(params); p.set("sector", id); setParams(p, { replace: true }); };
  const filed = (d?.rows ?? []).filter((r) => r.value != null);
  const waiting = (d?.rows ?? []).filter((r) => r.value == null);

  return (
    <div className="stack biz-page" style={{ gap: 24 }}>
      <RegionSwitch region="IN" />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Company news · India</span>
        <h1 className="page-title">Business updates</h1>
        <p className="page-sub">Monthly sales from automakers and quarterly deposits and advances from banks and lenders, as each company filed them
          with the exchange, read into numbers with the change on the previous period and on the year. Facts, not advice.</p>
      </div>
      {locked ? (
        <section className="card"><p className="small" style={{ margin: 0 }}>The sector view of business updates is on the <Link className="link" to="/plans">Basic plan</Link>.
          Each company page lists its own update filings for everyone.</p></section>
      ) : error ? <p className="small muted">{error}</p> : !d ? <Loading label="Reading the business updates" /> : (
        <section className="card stack" style={{ gap: 14 }}>
          <div className="seg" role="radiogroup" aria-label="Sector">
            {d.sectors.map((s) => <button key={s.id} role="radio" aria-checked={s.id === sector} aria-pressed={s.id === sector} onClick={() => pick(s.id)}>{s.label}</button>)}
          </div>
          {filed.length === 0 ? <p className="small muted">No update in this list has been read into numbers yet. They are read each evening after they're filed.</p> : (
            <div className="table-wrap">
              <table className="biz-table" aria-label={d.label}>
                <thead><tr><th style={{ textAlign: "left" }}>Company</th><th>Latest figure</th><th>On the previous</th><th>On the year</th><th>Filed</th></tr></thead>
                <tbody>{filed.map((r) => (
                  <tr key={r.symbol} data-company={r.symbol}>
                    <td style={{ textAlign: "left" }}><Link className="link" to={`/research/IN/${encodeURIComponent(r.symbol)}#business-updates`}><b>{r.name}</b></Link>
                      <div className="tiny muted">{r.metric}</div></td>
                    <td className="num">{bizValue(r.value, r.unit)}<div className="tiny muted">{r.period ? periodName(r.period, r.span) : ""}</div></td>
                    <td className="num">{bizChange(r.change_prev, r.unit)}</td>
                    <td className="num">{bizChange(r.change_year, r.unit)}</td>
                    <td className="small">{r.url ? <a className="link" href={safeHref(r.url)} target="_blank" rel="noopener noreferrer">{r.filed ? new Date(`${r.filed.slice(0, 10)}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "Filing"} ↗</a> : "–"}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
          {waiting.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Not read yet: {waiting.map((r) => r.name).join(", ")}.</p>}
          <p className="tiny muted" style={{ margin: 0 }}>{d.note}<Info label="How the figures are read">Each filing is read once: the figures are copied from the
            company's own document and kept only when the line they come from is found in it. Each company's page shows the line, the page and its 24-month chart.</Info></p>
        </section>
      )}
    </div>
  );
}
