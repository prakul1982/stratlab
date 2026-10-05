import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { asOf, price, signClass } from "../lib/format";
import { FUND_NAME, gapShort, loadEtfGaps, type EtfGaps, type Fund } from "../lib/etfGaps";
import { ResearchNav } from "../components/Research";
import { EtfGapDetailView } from "../components/EtfGap";
import { Info, Loading } from "../components/ui";

/* Indian ETFs' price against their NAV: every ETF on the exchange's list, the widest gap first, with each one's 30-day
 * range. Picking one opens its own view (the gap now and each day's close against that day's NAV). Facts only. */

type Sort = "wide" | "above" | "below";
const SORTS: [Sort, string][] = [["wide", "Widest gap"], ["above", "Most above"], ["below", "Most below"]];
const FUNDS: (Fund | "all")[] = ["all", "equity", "gold", "silver", "debt", "intl"];

export function EtfGapsPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("etf") ?? "").toUpperCase();
  const [data, setData] = useState<EtfGaps | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fund, setFund] = useState<Fund | "all">("all");
  const [sort, setSort] = useState<Sort>("wide");
  const [q, setQ] = useState("");

  useEffect(() => {
    let live = true;
    loadEtfGaps(true).then((x) => { if (!live) return; if (x) setData(x); else setError("The ETF list couldn't be opened just now. Try again in a few minutes."); });
    return () => { live = false; };
  }, []);

  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    const out = (data?.rows ?? []).filter((r) => (fund === "all" || r.fund === fund) && (!t || r.symbol.includes(t) || r.name.toUpperCase().includes(t)));
    const key = (g: number | null) => (g == null ? -Infinity : sort === "wide" ? Math.abs(g) : sort === "above" ? g : -g);
    return [...out].sort((a, b) => key(b.gap) - key(a.gap) || a.symbol.localeCompare(b.symbol));
  }, [data, fund, sort, q]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: data?.rows.length ?? 0 };
    for (const r of data?.rows ?? []) c[r.fund] = (c[r.fund] ?? 0) + 1;
    return c;
  }, [data]);
  // an indicative NAV shows only when the list has one: the exchange's list gives the last published NAV
  const hasInav = useMemo(() => (data?.rows ?? []).some((r) => r.inav != null), [data]);
  const open = (sym: string | null) => { const p = new URLSearchParams(params); if (sym) p.set("etf", sym); else p.delete("etf"); setParams(p, { replace: false }); };

  return (
    <div className="stack etf-gaps" style={{ gap: 24 }}>
      <ResearchNav region="IN" />
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Scans · India</span>
        <h1 className="page-title">ETF price against NAV</h1>
        <p className="page-sub">How far each ETF's price is from what one unit holds: its last published NAV, as a percent above or below, with
          the NAV's date. Facts with their times, not a view on any fund.</p>
      </div>

      {pick && <EtfGapDetailView key={pick} symbol={pick} />}

      {!data && !error ? <Loading label="Reading the ETF list" /> : !data ? <p className="small muted">{error}</p> : (
        <section className="card stack" style={{ gap: 14 }}>
          <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
            <div className="seg" role="group" aria-label="Kind of ETF">
              {FUNDS.filter((f) => f === "all" || counts[f]).map((f) => (
                <button key={f} aria-pressed={fund === f} onClick={() => setFund(f)}>{f === "all" ? "All" : FUND_NAME[f]}<span className="badge fact">{counts[f] ?? 0}</span></button>
              ))}
            </div>
            <span className="chip-select"><select aria-label="Order" value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              {SORTS.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select></span>
            <input className="input etf-gap-search" type="search" aria-label="Find an ETF" placeholder="Find an ETF" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <p className="tiny muted" style={{ margin: 0 }}>
            {data.as_of ? `Prices as of ${asOf(data.as_of)}` : "Prices as last read"}{data.nav_as_of ? ` · NAVs of ${asOf(data.nav_as_of)}` : ""} · {data.count} ETFs
            <Info label="What the numbers are">{data.note}</Info>
          </p>
          {rows.length === 0 ? <p className="small muted">No ETF matches that.</p> : (
            <div className="table-wrap">
              <table className="etf-gap-table" aria-label="ETFs by gap to NAV">
                <thead>
                  <tr><th style={{ textAlign: "left" }}>ETF</th><th>Price</th>{hasInav && <><th>iNAV</th><th>Gap to iNAV</th></>}<th>Last NAV</th><th>Price vs last NAV</th>
                    <th>30 trading days</th></tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.symbol} data-etf={r.symbol} className={pick === r.symbol ? "on" : undefined}>
                      <td style={{ textAlign: "left" }}>
                        <Link className="link" to={`/invest/etf-gaps?etf=${encodeURIComponent(r.symbol)}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></Link>
                        {" "}<span className={`badge kind-etf`}>{r.fund_label}</span>
                        <div className="tiny muted etf-gap-name">{r.name}</div>
                      </td>
                      <td className="num">{price(r.price, "INR")}</td>
                      {hasInav && <>
                        <td className="num">{r.inav == null ? "–" : price(r.inav, "INR")}</td>
                        <td className={`num ${signClass(r.inav_gap)}`}>{gapShort(r.inav_gap)}</td>
                      </>}
                      <td className="num">{r.nav == null ? "–" : price(r.nav, "INR")}{r.nav_date && <div className="tiny muted">{asOf(r.nav_date)}</div>}</td>
                      <td className={`num ${signClass(r.nav_gap)}`}>{gapShort(r.nav_gap)}</td>
                      <td className="num small">{r.days ? <>{r.days.low === r.days.high ? gapShort(r.days.low) : <>{gapShort(r.days.low)} to {gapShort(r.days.high)}</>}<div className="tiny muted">avg {gapShort(r.days.avg)}</div></> : "–"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="tiny muted" style={{ margin: 0 }}>{data.alerts ? <>Set an alert on a gap from an ETF's view, or on the <Link className="link" to="/alerts">Alerts page</Link>.</>
            : <>Alerts when a gap passes a level you set are on the <Link className="link" to="/plans">Basic plan</Link>.</>}</p>
        </section>
      )}
    </div>
  );
}
