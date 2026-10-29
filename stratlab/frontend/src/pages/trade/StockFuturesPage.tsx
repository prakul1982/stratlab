import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError } from "../../lib/api";
import { dayShort, dayText, desksApi, plainPct, sharesShort, signedPct, statusText, type Buildup, type FutDetail, type FutRow, type FutTable } from "../../lib/stockDesks";
import { ChartEmpty, LineChart } from "../../components/Charts";
import { AlertButton } from "../../components/AlertForm";
import { Info } from "../../components/ui";
import { Search } from "../../components/Icons";
import { POSITIONING_VIEWS, RouteSeg } from "../../components/RouteSeg";
import { Card, CardHead, ChipBar, DataTable, EmptyState, ErrorState, FactTable, PageHeader, RangeChips, Select, Signed, Skeleton, useRange, type Column } from "../../components/kit";
import "./trade.css";
import "./positioning.css";

/* /trade/positioning/stocks: the stock futures desk, a view of Positioning. One row per F&O stock from the exchange's
 * evening files: price and open-interest change and the buildup words for them, OI by expiry, the share in later
 * expiries (rollover), the futures' basis (annualised) and MWPL use. Sorted and filtered by the reader; nothing is
 * ranked. Today on every plan; each stock's stored history and the MWPL alert on Basic. Facts, not advice. Built from the kit. */

/** The two Positioning views: the index view and the stock futures desk, as one switch on each page. */
export function PosTabs() {
  return <RouteSeg label="Positioning view" views={POSITIONING_VIEWS} />;
}

type Filter = "all" | Buildup | "mwpl" | "roll";
type SortKey = "symbol" | "pc" | "oc" | "m" | "r" | "ba";
const SORTS: [SortKey, string][] = [["symbol", "Stock (A–Z)"], ["pc", "Price change"], ["oc", "OI change"], ["m", "MWPL use"], ["r", "Rollover"], ["ba", "Basis, annualised"]];
const BUILDUPS: Buildup[] = ["LB", "SB", "SC", "LU"];
/** Rows shown before "Show more" (DC-009: 213 rows in one 14,815 px scroll). */
export const SF_PAGE = 50;

/** A stock's open interest in contracts (lots), as the participant table and the option chain count them (DC-009: shares
 * with the lot beside them); null without a lot. */
export const oiLots = (r: Pick<FutRow, "oi" | "lot">) => (r.oi != null && r.lot ? Math.round(r.oi / r.lot) : null);

/** The days to the near expiry, once for the table when every row shares them, else null (each row then says its own). */
export function commonDays(rows: Pick<FutRow, "td" | "e">[]): { td: number; e: string | null } | null {
  const tds = new Set(rows.map((r) => r.td));
  return rows.length && tds.size === 1 && rows[0].td != null ? { td: rows[0].td, e: rows[0].e } : null;
}

function BuildupTag({ b, labels, streak }: { b: Buildup | null; labels: Record<Buildup, string>; streak?: number | null }) {
  if (!b) return <span className="k-muted k-small">No change</span>;
  return (
    <span className="sf-buildup" data-buildup={b}>
      <span className="sf-tag">{labels[b]}</span>
      {streak != null && streak > 1 && <span className="k-note">{streak} days in a row</span>}
    </span>
  );
}

function Mwpl({ r, ban }: { r: FutRow; ban: number }) {
  if (r.m == null) return <span className="k-muted">–</span>;
  return (
    <span className="sf-mwpl">
      <svg className="sf-meter" viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true">
        <rect className="bg" width="100" height="8" rx="4" /><rect className="fg" width={Math.min(100, r.m)} height="8" rx="4" /><line className="ban" x1={ban} x2={ban} y1="0" y2="8" />
      </svg>
      <span>{plainPct(r.m)}</span>
      {(r.ban_next || r.ban_now) && <span className="sf-ban" title="No new F&O positions until open interest is back under 80% of the limit">F&amp;O ban</span>}
    </span>
  );
}

function Detail({ symbol, t, onClose }: { symbol: string; t: FutTable; onClose: () => void }) {
  const [d, setD] = useState<FutDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setError(null);
    // everything stored (about a year of days): the range is cut here, by the app's one range control (O4)
    desksApi.future(symbol, "1y").then((x) => live && setD(x)).catch((e) => live && setError(e instanceof ApiError ? e.message : "That stock couldn't be read."));
    return () => { live = false; };
  }, [symbol]);
  const r = d?.row;
  const everyDay = useMemo(() => (d?.history ?? []).map((p) => p.day.slice(0, 10)), [d]);
  const rng = useRange("stock-futures", everyDay, "6m");
  const h = (d?.history ?? []).slice(rng.from);
  const labels = h.map((p) => dayText(p.day)), times = h.map((p) => p.day);
  return (
    <Card id="sf-detail" label={`${symbol} futures`}>
      <CardHead title={`${symbol} futures`} actions={<>
        {d?.full && <AlertButton region="IN" symbol={symbol} condition="mwpl" label="Alert on MWPL use" />}
        <button type="button" className="btn quiet sm" onClick={onClose}>Close</button>
      </>} />
      {error ? <ErrorState title="That stock couldn't be read" action={{ label: "Close", onClick: onClose }}>{error}</ErrorState> : !r ? <Skeleton label={`Reading ${symbol}`} /> : (
        <>
          <p className="k-small">
            On {dayText(r.as_of)} the near futures closed at ₹{r.px?.toLocaleString("en-IN")} (<Signed value={r.pc}>{signedPct(r.pc)}</Signed>) and open interest
            {r.oc == null ? " was unchanged" : <> {r.oc >= 0 ? "rose" : "fell"} <Signed value={r.oc}>{Math.abs(r.oc).toFixed(2)}%</Signed></>}
            {r.b ? `: ${t.labels[r.b].toLowerCase()}${r.streak && r.streak > 1 ? `, ${r.streak} days in a row` : ""}` : ""}.
          </p>
          <FactTable label={`${symbol} figures`} itemHead="Figure" figureHead="Now" noteHead="What it is" rows={[
            { id: "oi", k: "Open interest", v: sharesShort(r.oi), n: `near ${sharesShort(r.n)} · next ${sharesShort(r.x)} · far ${sharesShort(r.f)}` },
            { id: "roll", k: "In later expiries", v: plainPct(r.r), n: `${r.td} trading day${r.td === 1 ? "" : "s"} to ${dayText(r.e)}` },
            { id: "basis", k: "Basis", v: signedPct(r.bp), n: `${signedPct(r.ba)} a year · share ₹${r.s?.toLocaleString("en-IN")}` },
            { id: "mwpl", k: "MWPL use", v: plainPct(r.m), n: r.ban_next ? "No fresh positions the next day" : `ban from ${t.ban_at}%` },
          ]} />
          {!d.full ? (
            <div className="k-stack" data-testid="sf-locked">
              <p className="k-small k-muted">Each day's open interest, buildup, rollover, basis and MWPL use for {symbol}, and an alert when MWPL use crosses 80%, are on the {d.plan_needed} plan.</p>
              <Link to="/plans" className="btn sm k-btn-end">See the {d.plan_needed} plan</Link>
            </div>
          ) : (
            <div className="k-stack">
              <RangeChips chart="stock-futures" times={everyDay} options={rng.options} value={rng.value} onChange={rng.pick} label="History range" />
              {h.length < 2 ? <ChartEmpty height={180}>Not enough days yet to draw.</ChartEmpty> : (
                <div className="k-two">
                  <div className="k-stack">
                    <h3 className="k-sub">Open interest (shares)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.oi), color: "var(--pos-call)", width: 2, label: "Open interest" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => sharesShort(v)} axisFormat={(v) => sharesShort(v)} height={180} ariaLabel={`${symbol} futures open interest by day`} />
                  </div>
                  <div className="k-stack">
                    <h3 className="k-sub">MWPL use (%)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.m), color: "var(--pos-put)", width: 2, label: "MWPL use" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => `${v.toFixed(1)}%`} height={180} levels={[{ v: t.ban_at, color: "var(--muted)", label: `${t.ban_at}%` }]}
                      ariaLabel={`${symbol} MWPL use by day`} />
                  </div>
                  <div className="k-stack">
                    <h3 className="k-sub">Basis, annualised (%)</h3>
                    <LineChart lines={[{ values: h.map((p) => p.ba), color: "var(--pos-call)", width: 2, label: "Basis a year" }]} labels={labels} times={times}
                      sync="sf" ranges={false} format={(v) => signedPct(v)} baseline={0} height={180} ariaLabel={`${symbol} annualised basis by day`} />
                  </div>
                  <div className="k-stack">
                    <h3 className="k-sub">Open interest in later expiries (%)</h3>
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
    </Card>
  );
}

export function StockFuturesPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("s") ?? "").toUpperCase();
  const [t, setT] = useState<FutTable | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [again, setAgain] = useState(0);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<SortKey>("symbol");
  const [desc, setDesc] = useState(true);
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(SF_PAGE);
  useEffect(() => {
    setError(null);
    desksApi.futures().then(setT).catch((e) => setError(e instanceof ApiError ? e.message : "The stock futures couldn't be read."));
  }, [again]);
  useEffect(() => { setLimit(SF_PAGE); }, [filter, sort, desc, q]);
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
  // the days to expiry once, above the table, when every stock shares them (DC-009: "2d to expiry" on all 213 rows)
  const same = commonDays(t?.rows ?? []);
  // a filter that keeps every stock (or none) filters nothing: the expiry-week chip shows only when it narrows (DC-009)
  const filters = (["all", ...BUILDUPS, "mwpl", "roll"] as Filter[]).filter((f) => f !== "roll" || (count(f) > 0 && count(f) < (t?.rows.length ?? 0)));
  const shown = rows.slice(0, limit);

  const cols: Column<FutRow>[] = t ? [
    { key: "stock", header: "Stock", rowHeader: true, cell: (r) => <>
      <a className="link" href={`?s=${r.symbol}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></a>
      <span className="k-sub-line">lot {r.lot?.toLocaleString("en-IN") ?? "–"}</span></> },
    { key: "px", header: "Futures price", numeric: true, cell: (r) => <>{r.px?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "–"}<span className="k-sub-line"><Signed value={r.pc}>{signedPct(r.pc)}</Signed></span></> },
    { key: "oi", header: "Open interest", info: `${t.about.oi} Shown in contracts (lots), with the shares under them.`, numeric: true, cell: (r) => <>{oiLots(r) != null ? `${oiLots(r)!.toLocaleString("en-IN")} lots` : sharesShort(r.oi)}
      <span className="k-sub-line">{oiLots(r) != null ? `${sharesShort(r.oi)} shares · ` : ""}<Signed value={r.oc}>{signedPct(r.oc)}</Signed></span></> },
    { key: "b", header: "Buildup", info: BUILDUPS.map((b) => `${t.labels[b]}: ${t.about[b]}`).join(" "), cell: (r) => <BuildupTag b={r.b} labels={t.labels} streak={r.streak} /> },
    { key: "r", header: "Later expiries", info: t.about.rollover, numeric: true, cell: (r) => <>{plainPct(r.r)}<span className="k-sub-line">{r.td != null && !same ? `${r.td}d to expiry` : ""}</span></> },
    { key: "ba", header: "Basis", info: t.about.basis, numeric: true, cell: (r) => <>{signedPct(r.bp)}<span className="k-sub-line">{signedPct(r.ba)} a yr</span></> },
    { key: "m", header: "MWPL use", info: t.about.mwpl, cell: (r) => <Mwpl r={r} ban={t.ban_at} /> },
  ] : [];

  return (
    <div className="k-page sf-page">
      <PageHeader eyebrow="Trade · F&O desk" title="Stock futures"
        lede="Every F&O stock's futures after the close: price and open interest together, open interest by expiry, the share in later expiries, the futures' premium over the share and how much of the market-wide position limit is used. The exchange's numbers as published: facts, not advice."
        actions={<PosTabs />} />
      {pick && t && <Detail key={pick} symbol={pick} t={t} onClose={() => open(null)} />}
      {error ? <ErrorState title="The stock futures couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !t ? <Card><Skeleton label="Reading the stock futures" /></Card> : (
        <Card label="Stock futures">
          <p className="k-note" data-testid="sf-status">
            {statusText(t.status, "the F&O files")}
            <Info label="Where the numbers come from">{t.note} Source: {t.source}.</Info>
          </p>
          {!t.rows.length ? <EmptyState title="Nothing yet">{t.status.reason ?? "The exchange's evening files appear here once they are read."}</EmptyState> : (
            <>
              <ChipBar label="Show" value={filter} onChange={(v) => setFilter(v as Filter)}
                options={filters.map((f) => ({ value: f, label: `${f === "all" ? "All" : f === "mwpl" ? `MWPL ${t.watch_at}%+` : f === "roll" ? "Expiry week" : t.labels[f]} (${count(f)})` }))} />
              <div className="k-toolbar">
                <Select small label="Sort by" value={sort} onChange={(v) => setSort(v as SortKey)} options={SORTS.map(([value, label]) => ({ value, label }))} />
                {sort !== "symbol" && <button type="button" className="btn quiet sm" onClick={() => setDesc(!desc)} aria-label="Order">{desc ? "Highest first" : "Lowest first"}</button>}
                <label className="k-search sf-search"><Search size={16} /><input type="search" aria-label="Find a stock" placeholder="Find a stock" value={q} onChange={(e) => setQ(e.target.value)} /></label>
                <span className="k-note">{rows.length} of {t.rows.length} stocks</span>
              </div>
              {same && <p className="k-note" data-testid="sf-expiry">Every stock's near futures expire {same.e ? dayText(same.e) : "on the same day"}: {same.td} trading day{same.td === 1 ? "" : "s"} to go{same.td <= t.roll_window ? ", so the share in later expiries is read as the rollover" : ""}.</p>}
              <DataTable label="Stock futures by stock" columns={cols} rows={shown} rowKey={(r) => r.symbol} rowAttrs={(r): Record<string, string> => ({ "data-stock": r.symbol, ...(pick === r.symbol ? { "data-on": "1" } : {}) })} empty="No stock matches that." />
              {rows.length > shown.length && (
                <div className="k-row"><button type="button" className="btn quiet sm" data-testid="sf-more" onClick={() => setLimit((n) => n + SF_PAGE)}>
                  Show {Math.min(SF_PAGE, rows.length - shown.length)} more ({rows.length - shown.length} not shown)</button></div>
              )}
              <p className="k-note">
                {t.full ? <>Pick a stock for its history and an alert when its MWPL use crosses 80%.</>
                  : <>Each stock's history and MWPL alerts are on the <Link className="link" to="/plans">{t.plan_needed} plan</Link>.</>}
                {" "}The buildup words describe what price and open interest did on the day, nothing more.
              </p>
            </>
          )}
        </Card>
      )}
    </div>
  );
}

export default StockFuturesPage;
