import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { dayShort, dayText, desksApi, plainPct, sharesShort, signedPct, statusText, type Buildup, type FutDetail, type FutRow, type FutTable } from "../../lib/stockDesks";
import { ChartEmpty, LineChart } from "../../components/Charts";
import { AlertButton } from "../../components/AlertForm";
import { Info, Loading } from "../../components/ui";
import { POSITIONING_VIEWS, RouteSeg } from "../../components/RouteSeg";

/* /trade/positioning/stocks: the stock futures desk, a view of Positioning. One row per F&O stock from the exchange's
 * evening files: price and open-interest change and the buildup words for them, OI by expiry, the share in later
 * expiries (rollover), the futures' basis (annualised) and MWPL use. Sorted and filtered by the reader; nothing is
 * ranked. Today on every plan; each stock's stored history and the MWPL alert on Basic. Facts, not advice. */

/** The two Positioning views: the index view and the stock futures desk, as one switch on each page. */
export function PosTabs() {
  return <RouteSeg label="Positioning view" views={POSITIONING_VIEWS} />;
}

type Filter = "all" | Buildup | "mwpl" | "roll";
type SortKey = "symbol" | "pc" | "oc" | "m" | "r" | "ba";
const SORTS: [SortKey, string][] = [["symbol", "Stock (A–Z)"], ["pc", "Price change"], ["oc", "OI change"], ["m", "MWPL use"], ["r", "Rollover"], ["ba", "Basis, annualised"]];
const BUILDUPS: Buildup[] = ["LB", "SB", "SC", "LU"];

function BuildupTag({ b, labels, streak }: { b: Buildup | null; labels: Record<Buildup, string>; streak?: number | null }) {
  if (!b) return <span className="muted small">No change</span>;
  return (
    <span className="sf-buildup" data-buildup={b}>
      <span className="sf-tag">{labels[b]}</span>
      {streak != null && streak > 1 && <span className="tiny muted">{streak} days in a row</span>}
    </span>
  );
}

function Mwpl({ r, ban }: { r: FutRow; ban: number }) {
  if (r.m == null) return <span className="muted">–</span>;
  return (
    <span className="sf-mwpl">
      <span className="sf-bar" aria-hidden="true"><span style={{ width: `${Math.min(100, r.m)}%` }} /><i style={{ left: `${ban}%` }} /></span>
      <span className="num">{plainPct(r.m)}</span>
      {(r.ban_next || r.ban_now) && <span className="sf-ban" title="No new F&O positions until open interest is back under 80% of the limit">F&amp;O ban</span>}
    </span>
  );
}

function Detail({ symbol, t, onClose }: { symbol: string; t: FutTable; onClose: () => void }) {
  const [d, setD] = useState<FutDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [range, setRange] = useState("6m");
  useEffect(() => {
    let live = true;
    setError(null);
    desksApi.future(symbol, range).then((x) => live && setD(x)).catch((e) => live && setError(e instanceof ApiError ? e.message : "That stock couldn't be read."));
    return () => { live = false; };
  }, [symbol, range]);
  const r = d?.row;
  const h = d?.history ?? [];
  const labels = h.map((p) => dayText(p.day)), times = h.map((p) => p.day);
  return (
    <section className="card stack" style={{ gap: 14 }} id="sf-detail" aria-labelledby="sf-detail-h">
      <div className="spread" style={{ gap: 10, flexWrap: "wrap" }}>
        <h2 id="sf-detail-h" className="h3">{symbol} futures</h2>
        <div className="row" style={{ gap: 8 }}>
          {d?.full && <AlertButton region="IN" symbol={symbol} condition="mwpl" label="Alert on MWPL use" />}
          <button className="btn quiet sm" onClick={onClose}>Close</button>
        </div>
      </div>
      {error ? <p className="small muted">{error}</p> : !r ? <Loading label={`Reading ${symbol}`} /> : (
        <>
          <p className="small">
            On {dayText(r.as_of)} the near futures closed at ₹{r.px?.toLocaleString("en-IN")} ({signedPct(r.pc)}) and open interest
            {r.oc == null ? " was unchanged" : ` ${r.oc >= 0 ? "rose" : "fell"} ${Math.abs(r.oc).toFixed(2)}%`}
            {r.b ? `: ${t.labels[r.b].toLowerCase()}${r.streak && r.streak > 1 ? `, ${r.streak} stored days in a row` : ""}` : ""}.
          </p>
          <div className="space-figs">
            <div className="space-fig"><span className="tiny muted">Open interest</span><b className="num">{sharesShort(r.oi)}</b>
              <span className="tiny muted">near {sharesShort(r.n)} · next {sharesShort(r.x)} · far {sharesShort(r.f)}</span></div>
            <div className="space-fig"><span className="tiny muted">In later expiries</span><b className="num">{plainPct(r.r)}</b>
              <span className="tiny muted">{r.td} trading day{r.td === 1 ? "" : "s"} to {dayText(r.e)}</span></div>
            <div className="space-fig"><span className="tiny muted">Basis</span><b className="num">{signedPct(r.bp)}</b>
              <span className="tiny muted">{signedPct(r.ba)} a year · share ₹{r.s?.toLocaleString("en-IN")}</span></div>
            <div className="space-fig"><span className="tiny muted">MWPL use</span><b className="num">{plainPct(r.m)}</b>
              <span className="tiny muted">{r.ban_next ? "No fresh positions the next day" : `ban from ${t.ban_at}%`}</span></div>
          </div>
          {!d.full ? (
            <div className="stack" style={{ gap: 8 }} data-testid="sf-locked">
              <p className="small muted">Each day's open interest, buildup, rollover, basis and MWPL use for {symbol}, and an alert when MWPL use crosses 80%, are on the {d.plan_needed} plan.</p>
              <Link to="/plans" className="btn sm" style={{ alignSelf: "flex-start" }}>See the {d.plan_needed} plan</Link>
            </div>
          ) : (
            <div className="stack" style={{ gap: 12 }}>
              <div className="seg" role="group" aria-label="History range">
                {[["1m", "1M"], ["3m", "3M"], ["6m", "6M"], ["1y", "1Y"]].map(([k, l]) => <button key={k} aria-pressed={range === k} onClick={() => setRange(k)}>{l}</button>)}
              </div>
              {h.length < 2 ? <ChartEmpty height={180}>Not enough stored days to draw yet.</ChartEmpty> : (
                <div className="grid2" style={{ gap: 18 }}>
                  <div className="stack" style={{ gap: 6 }}>
                    <h3 className="small" style={{ fontWeight: 600 }}>Open interest (shares)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.oi), color: "var(--pos-call)", width: 2, label: "Open interest" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => sharesShort(v)} axisFormat={(v) => sharesShort(v)} height={180} ariaLabel={`${symbol} futures open interest by day`} />
                  </div>
                  <div className="stack" style={{ gap: 6 }}>
                    <h3 className="small" style={{ fontWeight: 600 }}>MWPL use (%)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.m), color: "var(--pos-put)", width: 2, label: "MWPL use" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => `${v.toFixed(1)}%`} height={180} levels={[{ v: t.ban_at, color: "var(--muted)", label: `${t.ban_at}%` }]}
                      ariaLabel={`${symbol} MWPL use by day`} />
                  </div>
                  <div className="stack" style={{ gap: 6 }}>
                    <h3 className="small" style={{ fontWeight: 600 }}>Basis, annualised (%)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.ba), color: "var(--pos-call)", width: 2, label: "Basis a year" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => signedPct(v)} baseline={0} height={180} ariaLabel={`${symbol} annualised basis by day`} />
                  </div>
                  <div className="stack" style={{ gap: 6 }}>
                    <h3 className="small" style={{ fontWeight: 600 }}>Open interest in later expiries (%)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.r), color: "var(--pos-put)", width: 2, label: "Later expiries" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => `${v.toFixed(1)}%`} height={180} ariaLabel={`${symbol} share of open interest in later expiries by day`} />
                  </div>
                </div>
              )}
              {h.length > 0 && (
                <div className="sf-days" aria-label={`${symbol}'s buildup by day`}>
                  {h.slice(-20).map((p) => <span key={p.day} className="sf-day" data-buildup={p.b ?? ""} title={`${dayText(p.day)}: ${p.b ? t.labels[p.b] : "no change"}`}>{dayShort(p.day)}<b>{p.b ?? "–"}</b></span>)}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}

export function StockFuturesPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [t, setT] = useState<FutTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<SortKey>("symbol");
  const [desc, setDesc] = useState(true);
  const [q, setQ] = useState("");
  useEffect(() => {
    desksApi.futures().then(setT).catch((e) => setError(e instanceof ApiError ? e.message : "The stock futures couldn't be read."));
  }, []);
  const rows = useMemo(() => {
    const s = q.trim().toUpperCase();
    const out = (t?.rows ?? []).filter((r) => (!s || r.symbol.includes(s))
      && (filter === "all" || (filter === "mwpl" ? (r.m ?? 0) >= (t?.watch_at ?? 80) : filter === "roll" ? r.roll_window : r.b === filter)));
    if (sort === "symbol") return out;
    const k = (r: FutRow) => r[sort] as number | null;
    return [...out].sort((a, b) => {
      const x = k(a), y = k(b);
      if (x == null) return 1;
      if (y == null) return -1;
      return desc ? y - x : x - y;
    });
  }, [t, filter, sort, desc, q]);
  const count = (f: Filter) => (t?.rows ?? []).filter((r) => (f === "all" || (f === "mwpl" ? (r.m ?? 0) >= (t?.watch_at ?? 80) : f === "roll" ? r.roll_window : r.b === f))).length;
  const open = (s: string | null) => { const p = new URLSearchParams(params); if (s) p.set("s", s); else p.delete("s"); setParams(p); };

  return (
    <div className="stack sf-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <span className="eyebrow">Trade · derivatives</span>
        <h1 className="page-title">Stock futures</h1>
        <p className="muted" style={{ maxWidth: "68ch" }}>Every F&amp;O stock's futures after the close: price and open interest together, open interest by expiry, the
          share in later expiries, the futures' premium over the share and how much of the market-wide position limit is used. The exchange's numbers as published: facts, not advice.</p>
      </div>
      <PosTabs />
      {pick && t && <Detail key={pick} symbol={pick} t={t} onClose={() => open(null)} />}
      {error ? <div className="banner">{error}</div> : !t ? <Loading label="Reading the stock futures" /> : (
        <section className="card stack" style={{ gap: 14 }}>
          <p className="tiny muted" style={{ margin: 0 }} data-testid="sf-status">
            {statusText(t.status, "the F&O files")}
            <Info label="Where the numbers come from">{t.note} Source: {t.source}.</Info>
          </p>
          {!t.rows.length ? <p className="small muted">{t.status.reason ?? "Nothing stored yet."}</p> : (
            <>
              <div className="seg sf-filters" role="group" aria-label="Show">
                {(["all", ...BUILDUPS, "mwpl", "roll"] as Filter[]).map((f) => (
                  <button key={f} aria-pressed={filter === f} onClick={() => setFilter(f)}>
                    {f === "all" ? "All" : f === "mwpl" ? `MWPL ${t.watch_at}%+` : f === "roll" ? "Expiry week" : t.labels[f]}<span className="badge fact">{count(f)}</span>
                  </button>
                ))}
              </div>
              <div className="row wrap" style={{ gap: 10, alignItems: "center" }}>
                <span className="chip-select"><select aria-label="Sort by" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  {SORTS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select></span>
                {sort !== "symbol" && <button className="btn quiet sm" onClick={() => setDesc(!desc)} aria-label="Order">{desc ? "Highest first" : "Lowest first"}</button>}
                <input className="input sf-search" type="search" aria-label="Find a stock" placeholder="Find a stock" value={q} onChange={(e) => setQ(e.target.value)} />
                <span className="tiny muted">{rows.length} of {t.rows.length} stocks</span>
              </div>
              <div className="table-wrap">
                <table className="nums sf-table" aria-label="Stock futures by stock">
                  <thead>
                    <tr>
                      <th scope="col" style={{ textAlign: "left" }}>Stock</th>
                      <th scope="col">Futures price</th>
                      <th scope="col">Open interest<Info label="Open interest">{t.about.oi}</Info></th>
                      <th scope="col" style={{ textAlign: "left" }}>Buildup<Info label="The buildup words">{BUILDUPS.map((b) => `${t.labels[b]}: ${t.about[b]}`).join(" ")}</Info></th>
                      <th scope="col">Later expiries<Info label="Rollover">{t.about.rollover}</Info></th>
                      <th scope="col">Basis<Info label="Basis">{t.about.basis}</Info></th>
                      <th scope="col" style={{ textAlign: "left" }}>MWPL use<Info label="MWPL use">{t.about.mwpl}</Info></th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.symbol} data-stock={r.symbol} className={pick === r.symbol ? "on" : undefined}>
                        <th scope="row" style={{ textAlign: "left" }}>
                          <a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
                          <div className="tiny muted">lot {r.lot?.toLocaleString("en-IN") ?? "–"}</div>
                        </th>
                        <td>{r.px?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "–"}<span className="tiny muted" style={{ display: "block" }}>{signedPct(r.pc)}</span></td>
                        <td>{sharesShort(r.oi)}<span className="tiny muted" style={{ display: "block" }}>{signedPct(r.oc)}</span></td>
                        <td style={{ textAlign: "left" }}><BuildupTag b={r.b} labels={t.labels} streak={r.streak} /></td>
                        <td>{plainPct(r.r)}<span className="tiny muted" style={{ display: "block" }}>{r.td != null ? `${r.td}d to expiry` : ""}</span></td>
                        <td>{signedPct(r.bp)}<span className="tiny muted" style={{ display: "block" }}>{signedPct(r.ba)} a yr</span></td>
                        <td style={{ textAlign: "left" }}><Mwpl r={r} ban={t.ban_at} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="tiny muted" style={{ margin: 0 }}>
                {t.full ? <>Pick a stock for its stored history and an alert when its MWPL use crosses 80%.</>
                  : <>Each stock's stored history and MWPL alerts are on the <Link className="link" to="/plans">{t.plan_needed} plan</Link>.</>}
                {" "}The buildup words describe what price and open interest did on the day, nothing more.
              </p>
            </>
          )}
        </section>
      )}
    </div>
  );
}

export default StockFuturesPage;
