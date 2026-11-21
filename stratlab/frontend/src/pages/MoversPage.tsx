import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../lib/api";
import { bigMoney, fmtDate, pct, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { useRegion, type Region } from "../lib/research";
import { LISTS, LIST_META, countLine, figureOf, isList, times, type ListId, type MoverRow, type MoversView } from "../lib/movers";
import "./movers.css";
import { useApp } from "../lib/app";
import { marketState } from "../lib/marketHours";
import { dayLine } from "../lib/heatmap";
import { Card, CardHead, ChipBar, CsvButton, DataTable, EmptyState, ErrorState, Field, FieldGroup, PageHeader, PlanNote, Seg, Select, Signed, Working, type Column } from "../components/kit";

/* /invest/movers: a group's biggest gainers and losers at the last close, the most traded by value, the volume spikes and the 52-week
 * highs and lows, India and the US. The figures are the daily closes the heatmap already stores (one read gives every list; the tabs
 * change the list without another). Basic and up get every row, any index, a smallest market value and the CSV; Free gets the top 5 of
 * each list for the market's default index, and says which plan has the rest. Facts only: a list is sorted by a figure. */

const MIN_CAPS: Record<Region, { value: string; label: string }[]> = {
  IN: [{ value: "", label: "Any size" }, { value: "1000", label: "₹1,000 cr and up" }, { value: "5000", label: "₹5,000 cr and up" }, { value: "20000", label: "₹20,000 cr and up" }, { value: "100000", label: "₹1 lakh cr and up" }],
  US: [{ value: "", label: "Any size" }, { value: "2000", label: "$2B and up" }, { value: "10000", label: "$10B and up" }, { value: "50000", label: "$50B and up" }, { value: "200000", label: "$200B and up" }],
};
const UNIT: Record<Region, number> = { IN: 1e7, US: 1e6 };
const CCY: Record<Region, string> = { IN: "INR", US: "USD" };

export function MoversPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const list: ListId = isList(params.get("list")) ? (params.get("list") as ListId) : "gainers";
  const universe = params.get("u") ?? "";
  const minCap = MIN_CAPS[region].some((o) => o.value === params.get("min")) ? params.get("min")! : "";
  const set = (changes: Record<string, string | null>) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) { if (v) p.set(k, v); else p.delete(k); }
    setParams(p, { replace: true });
  };
  const [view, setView] = useState<MoversView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [again, setAgain] = useState(0);
  const seq = useRef(0);
  useEffect(() => {
    const mine = ++seq.current;
    setBusy(true); setError(null);
    setView((v) => (v && v.market === region ? v : null));      // another market's rows are not shown in this one's units
    const q = new URLSearchParams({ market: region });
    if (universe) q.set("universe", universe);
    if (minCap) q.set("min_cap", minCap);
    api<MoversView>(`/invest/movers?${q}`)
      .then((v) => { if (mine === seq.current) setView(v); })
      .catch((e) => {
        if (mine !== seq.current) return;
        if (e instanceof ApiError && e.status === 404 && universe) { set({ u: null }); return; }    // a group from an old link
        setError(e instanceof ApiError ? e.message : "The movers couldn't be read."); setView(null);
      })
      .finally(() => { if (mine === seq.current) setBusy(false); });
  }, [region, universe, minCap, again]);

  const ccy = CCY[region];
  const { markets, me } = useApp();
  // LIVE10A-030: during the session the lists are the last close's, said as the Heatmap says it
  const open = (() => { const m = markets.find((x) => x.id === region); return m ? marketState(m).open : false; })();
  // LIVE10A-041: a Free account's plan line is drawn while the first read is out, so the lists don't jump down when it arrives (CLS 0.186)
  const locked = !!view?.locked || (!view && (me?.paid_plan ?? me?.plan) === "free");
  const meta = LIST_META[list];
  const lst = view?.lists[list];
  const rows = lst?.rows ?? [];
  const asOf = view?.as_of ? fmtDate(view.as_of) : null;
  // LIVE13A-012/-029: the live round's prices in the session and the day's last trades after the bell, said as such
  const line = view ? dayLine(view, open, "lists", (d) => fmtDate(d), region === "IN" ? "IST" : "ET") : null;
  const what = view?.live && !view.live.close ? meta.what.replace("at the close", "so far today").replace("the closing price", "the latest price") : meta.what;
  const pxHead = line?.price === "Last close" || !line ? "Close" : line.price;
  const figureCell = (r: MoverRow) => (list === "traded" ? (r.tv == null ? "–" : bigMoney(r.tv, ccy)) : list === "highs" || list === "lows" ? price(figureOf(list, r), ccy) : times(r.vx));
  const cols: Column<MoverRow>[] = [
    { key: "n", header: "Company", rowHeader: true, wrap: true, cell: (r) => <Link className="link" to={`/research/${region}/${encodeURIComponent(r.s)}`}><b>{r.s}</b>{r.n && r.n.replace(/\s/g, "").toUpperCase() !== r.s.toUpperCase() && <> <span className="k-muted">{r.n}</span></>}</Link>,
      csv: (r) => r.n, csvHeader: "Company" },
    { key: "sym", header: "Symbol", csvOnly: true, cell: (r) => r.s, csv: (r) => r.s },
    { key: "px", header: pxHead, numeric: true, cell: (r) => (r.px == null ? "–" : price(r.px, ccy)), csv: (r) => r.px, csvHeader: `${pxHead} (${ccy})` },
    { key: "chg", header: "1 day", numeric: true, brief: true, cell: (r) => <Signed value={r.chg} fmt={(v) => pct(v, 2)} />, csv: (r) => r.chg, csvHeader: "1 day (%)" },
    { key: "fig", header: meta.figure, numeric: true, cell: figureCell, csv: (r) => figureOf(list, r),
      csvHeader: list === "traded" ? `Value traded (${ccy})` : list === "highs" || list === "lows" ? `${meta.figure} (${ccy})` : "Volume vs 20-session average (×)" },
    { key: "cap", header: "Market value", numeric: true, narrow: false, cell: (r) => (r.cap == null ? "–" : bigMoney(r.cap * UNIT[region], ccy)), csv: (r) => r.cap, csvHeader: `Market value (${view?.cap_unit ?? ""})` },
  ];
  const name = view?.universe_name ?? "";
  const counted = lst ? countLine(rows.length, lst.total) : "";
  const tableLabel = `${name}: ${meta.label}, ${view?.live && line ? line.source : `close of ${asOf ?? "the last day"}`}`;
  return (
    <div className="k-page mv-page">
      <PageHeader eyebrow={eyebrowOf("/invest/movers")} title="Movers"
        lede="The day's biggest gainers and losers, the most traded, volume spikes and new 52-week highs and lows, from each stock's daily close. Facts, not advice." />
      {locked && <PlanNote plan="basic">Free shows the top 5 of each list for {name || "the market's main index"}. Every row, any index, a smallest market value and the CSV are on the {view?.plan ?? "Basic"} plan.</PlanNote>}
      <Card label="Movers settings">
        <div className="k-row mv-controls" data-testid="mv-controls">
          <FieldGroup label="Market"><Seg label="Market" value={region} onChange={(v) => { setRegion(v as Region); set({ region: v, u: null, min: null }); }} options={[{ value: "IN", label: "₹ India" }, { value: "US", label: "$ United States" }]} /></FieldGroup>
          {/* LIVE12A-005: the field is drawn while the first read is out (disabled), so the list doesn't jump down when it comes (phone CLS 0.35) */}
          {(!view || view.universes.length > 0) && (
            <Field label="Stocks">{(id) => view
              ? <Select id={id} value={view.universe} disabled={locked} onChange={(v) => set({ u: v })} options={view.universes.map((u) => ({ value: u.id, label: u.name }))} />
              : <Select id={id} value="" disabled onChange={() => undefined} options={[{ value: "", label: "Reading…" }]} />}</Field>
          )}
          <Field label="Smallest market value">{(id) => <Select id={id} value={locked ? "" : minCap} disabled={locked} onChange={(v) => set({ min: v || null })} options={MIN_CAPS[region]} />}</Field>
        </div>
      </Card>
      {error ? <ErrorState title="The movers couldn't be read" action={{ label: "Try again", onClick: () => setAgain((x) => x + 1) }}>{error}</ErrorState>
        : !view ? <Card className="mv-wait"><Working label="Reading the market's closes" /></Card>
        : view.pending ? (
          <Card><EmptyState title="The movers fill in after the next market close">Each stock's day is worked out once a day from its daily close, after the market shuts. The lists appear here on their own once that has run.</EmptyState></Card>
        ) : (
          <Card label="The movers" testId="movers">
            {/* LIVE12A-005: "Download CSV" in the card's head, never alone on a row over the list (a phone showed "CSV" by itself) */}
            <CardHead title={`${name}: ${meta.label.toLowerCase()}`} infoLabel="About the movers"
              info={`From each stock's ${view.live && line ? line.source : `daily close${asOf ? ` of ${asOf}` : ""}`}. A stock with no trade on that day is left out. ${what}`}
              actions={!locked && rows.length > 0 ? <CsvButton name={`movers ${name} ${meta.label}`} label={tableLabel} columns={cols} rows={rows} /> : undefined} />
            <ChipBar label="List" wrap value={list} onChange={(v) => set({ list: v === "gainers" ? null : v })}
              options={LISTS.map((k) => ({ value: k, label: LIST_META[k].label }))} />
            <p className="mv-facts" data-testid="mv-facts">
              {line && <span data-testid="mv-day">{line.lead}<b>{line.day}</b>{line.tail}</span>}
              {counted && <span>{counted}</span>}
              <span><b>{view.matching.toLocaleString("en-IN")}</b> {view.matching === 1 ? "company" : "companies"} {view.live ? "traded that day" : "with a close that day"}</span>
            </p>
            {busy && <Working small label="Reading the new settings" />}
            <DataTable label={tableLabel} columns={cols} rows={rows}
              rowKey={(r) => r.s} stack compact
              empty={(list === "highs" || list === "lows") && !view.marks ? "The 52-week highs and lows appear after the next daily close run." : "None at this close."} />
            <p className="k-note">{what}{locked && lst && lst.total > rows.length ? ` ${(lst.total - rows.length).toLocaleString("en-IN")} more on the ${view.plan ?? "Basic"} plan.` : ""}</p>
          </Card>
        )}
      <p className="k-note">The same top 5 lists are on the public pages for <a className="link" href="/stocks/in/movers">India</a> and <a className="link" href="/stocks/us/movers">the US</a>. <a className="link" href="/status">When each dataset was last updated</a>.</p>
    </div>
  );
}
