import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { asOf, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { FUND_NAME, gapShort, loadEtfGaps, type EtfGap, type EtfGaps, type Fund } from "../lib/etfGaps";
import { EtfGapDetailView } from "../components/EtfGap";
import { Badge, Card, CardHead, ChipBar, DataTable, ErrorState, Field, FieldGroup, FormGrid, PageHeader, Select, Skeleton, StockPicker, type Column } from "../components/kit";

/* Indian ETFs' price against their NAV: every ETF on the exchange's list, the widest gap first, with each one's 30-day
 * range. Picking one opens its own view (the gap now and each day's close against that day's NAV). Facts only. */

type Sort = "wide" | "above" | "below";
const SORTS: { value: Sort; label: string }[] = [{ value: "wide", label: "Widest gap" }, { value: "above", label: "Most above" }, { value: "below", label: "Most below" }];
const FUNDS: (Fund | "all")[] = ["all", "equity", "gold", "silver", "debt", "intl"];
const TOP = 50;

export function EtfGapsPage() {
  const [params, setParams] = useSearchParams();
  const pick = (params.get("etf") ?? "").toUpperCase();
  const [data, setData] = useState<EtfGaps | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fund, setFund] = useState<Fund | "all">("all");
  const [sort, setSort] = useState<Sort>("wide");
  const [q, setQ] = useState("");
  const [tries, setTries] = useState(0);
  // the widest gaps first, a page of them: all 350-odd made a 38,000 px page on a phone (R5O-017)
  const [all, setAll] = useState(false);

  useEffect(() => {
    let live = true;
    setError(null);
    loadEtfGaps(true).then((x) => { if (!live) return; if (x) setData(x); else setError("The ETF list couldn't be opened just now. Try again in a few minutes."); });
    return () => { live = false; };
  }, [tries]);

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

  const columns: Column<EtfGap>[] = [
    { key: "etf", header: "ETF", rowHeader: true, wrap: true, cell: (r) => (
      <><Link className="link" to={`/invest/etf-gaps?etf=${encodeURIComponent(r.symbol)}`} onClick={(e) => { e.preventDefault(); open(r.symbol); window.scrollTo({ top: 0 }); }}><b>{r.symbol}</b></Link>
        {" "}<Badge tone="plain" dot={false}>{r.fund_label}</Badge>
        <span className="k-sub-line">{r.name}</span></>) },
    { key: "px", header: "Price", numeric: true, cell: (r) => price(r.price, "INR") },
    ...(hasInav ? [
      { key: "inav", header: "iNAV", numeric: true, cell: (r: EtfGap) => (r.inav == null ? "–" : price(r.inav, "INR")) },
      { key: "ig", header: "Gap to iNAV", numeric: true, cell: (r: EtfGap) => gapShort(r.inav_gap) }] : []),
    { key: "nav", header: "Last NAV", numeric: true, cell: (r) => <>{r.nav == null ? "–" : price(r.nav, "INR")}{r.nav_date && <span className="k-sub-line">{asOf(r.nav_date)}</span>}</> },
    { key: "ng", header: "Price vs last NAV", numeric: true, cell: (r) => gapShort(r.nav_gap) },
    { key: "d30", header: "30 trading days", numeric: true, wrap: true, cell: (r) => (r.days
      ? <>{r.days.low === r.days.high ? gapShort(r.days.low) : <>{gapShort(r.days.low)} to {gapShort(r.days.high)}</>}<span className="k-sub-line">avg {gapShort(r.days.avg)}</span></> : "–") },
  ];

  return (
    <div className="k-page etf-gaps">
      <PageHeader eyebrow={eyebrowOf("/invest/etf-gaps")} title="ETF price against NAV" asOf={data?.as_of} asOfLabel="Prices as of"
        info={data ? <>{data.nav_as_of ? `NAVs of ${asOf(data.nav_as_of)}. ` : ""}{data.count} ETFs. {data.note}</> : undefined} infoLabel="What the numbers are"
        lede="How far each ETF's price is from what one unit holds: its last published NAV, as a percent above or below, with the NAV's date. Facts with their times, not a view on any fund." />

      {pick && <EtfGapDetailView key={pick} symbol={pick} />}

      {!data && !error ? <Card><Skeleton label="Reading the ETF list" lines={4} /></Card> : !data ? <ErrorState title="The ETF list couldn't be opened" action={{ label: "Try again", onClick: () => setTries((n) => n + 1) }}>{error}</ErrorState> : (
        <Card>
          <CardHead title="Every ETF, by gap to its NAV" />
          <FormGrid label="Filter the ETFs">
            <FieldGroup label="Kind of ETF" wide>
              <ChipBar label="Kind of ETF" value={fund} onChange={(v) => setFund(v as Fund | "all")}
                options={FUNDS.filter((f) => f === "all" || counts[f]).map((f) => ({ value: f, label: `${f === "all" ? "All" : FUND_NAME[f]} ${counts[f] ?? 0}` }))} />
            </FieldGroup>
            <Field label="Order">{(id) => <Select id={id} value={sort} onChange={(v) => setSort(v as Sort)} options={SORTS} />}</Field>
            <Field label="Find an ETF">{(id) => <StockPicker id={id} placeholder="e.g. NIFTYBEES" onText={setQ} onPick={(s) => { setQ(""); open(s); }} />}</Field>
          </FormGrid>
          {/* stack: on a phone each ETF is a card with every figure labelled, instead of columns cut off at the edge */}
          <DataTable label="ETFs by gap to NAV" rows={all || q.trim() ? rows : rows.slice(0, TOP)} rowKey={(r) => r.symbol} stack sticky={rows.length > 14} empty="No ETF matches that."
            rowAttrs={(r) => ({ "data-etf": r.symbol, className: pick === r.symbol ? "on" : "" })} columns={columns} />
          {!all && !q.trim() && rows.length > TOP && (
            <div className="k-row"><span className="k-note">Showing {TOP} of {rows.length} ETFs, in the order above.</span>
              <button type="button" className="btn quiet sm" onClick={() => setAll(true)}>Show all {rows.length}</button></div>)}
          <p className="k-note">{data.alerts ? <>Set an alert on a gap from an ETF's view, or on the <Link className="link" to="/alerts">Alerts page</Link>.</>
            : <>Alerts when a gap passes a level you set are on the <Link className="link" to="/plans">Basic plan</Link>.</>}</p>
        </Card>
      )}
    </div>
  );
}
