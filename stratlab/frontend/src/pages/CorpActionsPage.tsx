import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, fmtTime, marketTz, pctPlain, price } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { LIVE_ROWS, useRowQuotes } from "../lib/rowQuotes";
import { REGION_NAME, saveRegion, savedRegion, screenCap, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { ActionCell, ActionFigure, KIND_NAME, exDay, recordCell, type ActionKind, type CorpAction } from "../components/CorpActions";
import { CalendarFilters, NO_CAL, SIZE_NAME, calCount, keepFilters, keptFilters, type CalFilters, type Facets } from "../components/CalendarFilters";
import { Info } from "../components/ui";
import { Earlier } from "../components/Earlier";
import { Card, CardHead, CheckField, DataTable, EmptyState, ErrorState, Field, PageHeader, Seg, Select, Skeleton, StockPicker, type Column } from "../components/kit";

/** A row of the calendar with what the app keeps about its company (the same facts the results calendar's table has). */
export interface ActionRow extends CorpAction {
  cap?: number | null; band?: string | null; sector?: string | null; last?: number | null; last_at?: string | null; fo?: boolean; indices?: string[]; yield_pct?: number | null;
}
interface CalendarView {
  region: Region; scope: "mine" | "all"; kind: string; today: string; updated_at: string | null; ahead: ActionRow[]; recent: ActionRow[];
  more: number; mine_count: number; alerts: boolean; kinds: ActionKind[]; ahead_known: boolean; ahead_note?: string | null; note: string;
  recent_days?: number; universe?: { companies: number | null; updated_at: string | null } | null;
  total: number; matching: number; unknown_size: number; filters: CalFilters; facets: Facets;
}

const KEEP = "stratlab.corp.filters.v1";
const NO_FILTERS: CalFilters = { ...NO_CAL, sort: "date" };
const SORT_NAME: Record<string, string> = { date: "Ex-date, soonest first", cap: "Market value, largest first", yield: "Yield of the payment, highest first", name: "Company name" };

export function CorpActionsPage() {
  const [params, setParams] = useSearchParams();
  const fromUrl = params.get("region")?.toUpperCase();
  const [region, setRegionState] = useState<Region>(fromUrl === "US" || fromUrl === "IN" ? fromUrl : savedRegion());
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const kind = params.get("kind") ?? "";
  const { fail, notify } = useApp();
  const [q, setQ] = useState("");
  const [data, setData] = useState<CalendarView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [filters, setFilters] = useState<CalFilters>(() => keptFilters(KEEP, NO_FILTERS));
  // another market or another set of companies is a different list: the find-a-company text and the old list don't carry over
  const [shownFor, setShownFor] = useState(`${region}|${scope}`);
  if (shownFor !== `${region}|${scope}`) { setShownFor(`${region}|${scope}`); setQ(""); setData(null); }
  // a sector or an index of one market is not the other's
  const [filtersFor, setFiltersFor] = useState(region);
  if (filtersFor !== region) { setFiltersFor(region); setFilters((f) => ({ ...f, sector: "", index: "", fo: false })); }
  useEffect(() => { keepFilters(KEEP, filters); }, [filters]);
  const set = (p: Partial<CalFilters>) => setFilters((f) => ({ ...f, ...p }));
  const sortName = filters.sort || "date";

  const setParam = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  const setRegion = (r: Region) => { setRegionState(r); saveRegion(r); setParam("region", r); };

  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ region, scope, kind, q: scope === "all" ? q : "", size: filters.size.join(","), sector: filters.sector, index: filters.index,
        fo: filters.fo ? "true" : "", on: filters.on, sort: sortName });
      for (const [k, v] of [...qs]) if (v === "") qs.delete(k);
      api<CalendarView>(`/research/corp-actions?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, kind, q, tries, filters, sortName]);

  // the prices of the rows in view (the first LIVE_ROWS), read each minute while the market trades
  const inView = useMemo(() => [...(data?.ahead ?? []), ...(data?.recent ?? [])].slice(0, LIVE_ROWS), [data]);
  const symbols = useMemo(() => [...new Set(inView.map((r) => r.symbol))], [inView]);
  const { quotes, quoteAt, live: isLive } = useRowQuotes(region, symbols);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/corp-actions/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message when one of your stocks announces a corporate action, and the evening before its ex-date." : "Corporate action messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && !data.ahead.length && !data.recent.length;
  const lookBack = (data?.recent_days ?? 14) >= 28 ? "Last four weeks" : "Last two weeks";
  const n = calCount(filters, "date") + (kind ? 1 : 0);
  const cur = region === "IN" ? "INR" : "USD";
  const showMine = scope === "all";
  const dayNames = [...new Set([...(data?.ahead ?? []), ...(data?.recent ?? [])].map((r) => r.ex_date))].sort();

  const columns: Column<ActionRow>[] = [
    { key: "co", header: "Company", rowHeader: true, wrap: true, cell: (r) => (
      <span className="k-stack">
        <span className="res-sym">
          <Link className="link" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
          {showMine && r.mine && <span className="k-note k-muted">Yours</span>}
          {r.fo && <span className="k-note k-muted">F&amp;O</span>}
        </span>
        {r.name && <span className="k-note k-muted">{r.name}</span>}
      </span>) },
    { key: "act", header: "Action", wrap: true, cell: (r) => <ActionCell a={r} cur={cur} /> },
    { key: "fig", header: "Amount or ratio", numeric: true, cell: (r) => <ActionFigure a={r} cur={cur} /> },
    { key: "rec", header: "Record date", cell: (r) => recordCell(r) },
    { key: "px", header: "Price now", numeric: true, cell: (r) => {
      const x = quotes[r.symbol];
      if (x?.price != null) return <span title={x.at ? `Read ${fmtTime(x.at, { tz: marketTz(region), zone: true })}` : undefined}>{price(x.price, cur)}</span>;
      return r.last == null ? <span className="k-muted">–</span> : <span className="k-muted" title={r.last_at ? `Last close, ${exDay(r.last_at)}` : "Last close"}>{price(r.last, cur)}</span>;
    } },
    { key: "yld", header: "Yield of this payment", numeric: true, info: "A dividend's amount over the price now (the last close when no live price is in): what this one payment is, as a share of the price. It is not the year's dividend yield. Only dividends have one.", cell: (r) => {
      const x = quotes[r.symbol]?.price ?? r.last;
      const y = r.kind === "dividend" && r.amount && x ? (r.amount / x) * 100 : null;
      return y == null ? <span className="k-muted">–</span> : <>{pctPlain(y, 2)}</>;
    } },
    { key: "cap", header: "Market value", numeric: true, cell: (r) => (r.cap == null ? <span className="k-muted">–</span> : <span title={r.band ? `${SIZE_NAME[r.band]} company` : undefined}>{screenCap(r.cap, r.region)}</span>) },
  ];

  const day = (rows: ActionRow[], d: string) => {
    const on = rows.filter((r) => r.ex_date === d);
    return (
      <div key={d} className="inv-day" data-testid="actions-day">
        <span className="k-eyebrow">Ex-date {exDay(d)}{d === data?.today ? " · today" : ""} · {on.length} {on.length === 1 ? "action" : "actions"}</span>
        <DataTable label={`Corporate actions going ex on ${exDay(d)}`} rows={on} rowKey={(r) => r.id} columns={columns} stack phonePage={10} />
      </div>
    );
  };
  const groups = (rows: ActionRow[]) => <div className="k-stack">{[...new Set(rows.map((r) => r.ex_date))].map((d) => day(rows, d))}</div>;

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/corporate-actions")} title="Dividends, bonuses and splits" asOf={data?.updated_at} asOfLabel="Updated" asOfTz={marketTz(region)}
        lede={region === "IN"
          ? "Dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date, as companies announced them to the exchange."
          : "Dividends and splits of the S&P 500 and the US companies you follow, by ex-date: dividends companies have declared for the next four weeks, and those that have gone ex."}
        info={region === "US" ? <>Dividends ahead are the ones companies have declared, from the US market calendar, for the next four weeks, with the record and pay dates the company gave.
          Past ex-dates, and splits, are read once a day from each company's price history: the S&P 500 and StratLab's own groups{data?.universe?.companies ? ` (${data.universe.companies.toLocaleString("en-IN")} companies read)` : ""}, plus any US stock you follow. A split ahead isn't listed until its ex-date. Amounts are per share.</> : undefined}
        infoLabel="About the US list" />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={setRegion} />
        <Seg label="Which companies" value={scope} onChange={(v) => setParam("scope", v)} options={[{ value: "mine", label: "My stocks" }, { value: "all", label: "All" }]} />
      </div>
      <CalendarFilters region={region} facets={data?.facets ?? null} filters={filters} set={set} firstSort="date" sorts={SORT_NAME} active={n}
        total={data?.total ?? null} matching={data?.matching ?? null} unknownSize={data?.unknown_size ?? 0} testId="actions-count" noun="action"
        onClear={() => { setFilters(NO_FILTERS); setParam("kind", ""); }}
        days={[{ value: "", label: "Every day" }, { value: "today", label: "Today" }, { value: "tomorrow", label: "Tomorrow" }, ...dayNames.map((d) => ({ value: d, label: exDay(d) }))]}
        search={<>
          {scope === "all" && (
            <Field key={region} label="Find a company">
              {(id) => <StockPicker id={id} market={region} onText={setQ} onPick={(s) => setQ(s)} placeholder={region === "IN" ? "Like TCS or Infosys" : "Like AAPL or Apple"} />}
            </Field>
          )}
          {data && (
            <CheckField checked={data.alerts} onChange={toggleAlerts}
              label={<>Message me when my stocks announce a corporate action, and the evening before an ex-date
                <Info>Sent by phone notification or Telegram, whichever you set up in Settings. Your stocks are your watchlist, holdings, notebooks and paper sessions. The My Stocks newsletter lists the week's ex-dates too.</Info></>} />
          )}
        </>}>
        <Field label="Kind of action">
          {(id) => <Select id={id} value={kind} onChange={(v) => setParam("kind", v)}
            options={[{ value: "", label: "Every kind" }, ...(Object.keys(KIND_NAME) as ActionKind[]).map((k) => ({ value: k, label: KIND_NAME[k] }))]} />}
        </Field>
      </CalendarFilters>
      {error && <ErrorState title="The calendar couldn't be opened" action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>{error}</ErrorState>}
      {!data && !error && <Card><Skeleton label="Opening the corporate actions calendar" lines={4} /></Card>}
      {data && empty && (
        <Card>
          <EmptyState title={n ? "No action matches these filters" : scope === "mine" ? (data.mine_count ? "None of your stocks has an ex-date in this window" : "No stocks to show ex-dates for yet") : "Nothing announced for this window"}
            action={n ? { label: "Clear filters", onClick: () => { setFilters(NO_FILTERS); setParam("kind", ""); } } : scope === "mine" ? { label: "See all companies", onClick: () => setParam("scope", "all") } : undefined}>
            {n ? `${data.total.toLocaleString("en-IN")} ${data.total === 1 ? "action is" : "actions are"} listed in this window; none meets every filter.`
              : scope === "mine"
              ? (data.mine_count ? `None of your ${REGION_NAME[region]} stocks has an ex-date in this window.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, holdings, notebooks and paper sessions.`)
              : q ? "No company by that name has an action in this window." : (data.ahead_note ?? "Nothing announced for this window yet.")}
          </EmptyState>
        </Card>
      )}
      {data && !empty && (
        <>
          {/* always there, and when it has nothing it says why (RC1-006: the US list was empty with no word) */}
          <Card>
            <CardHead title="Coming up" />
            {data.ahead.length === 0 ? <span className="k-small k-muted" data-testid="ahead-note">{n ? "Nothing ahead meets the filters." : data.ahead_note ?? "Nothing announced with an ex-date ahead."}</span> : groups(data.ahead)}
          </Card>
          {/* ex-dates gone by fold under one line, open only when there is nothing ahead to show */}
          {data.recent.length > 0 && (
            <Card label={lookBack}>
              <Earlier label={lookBack} count={data.recent.length} open={!data.ahead_known && !data.ahead.length}>
                {groups(data.recent)}
              </Earlier>
            </Card>
          )}
          <p className="k-note" data-testid="actions-prices">
            {isLive ? `Prices as of ${fmtTime(quoteAt!, { tz: marketTz(region), zone: true })}, read for the first ${Math.min(symbols.length, LIVE_ROWS)} companies in view and again each minute while the market trades.`
              : symbols.length ? "Prices are each company's last close; the market is not trading now." : ""} The yield is one payment over the price now, not the year's.
          </p>
        </>
      )}
      {data && data.more > 0 && <p className="k-note">And {data.more} more.{scope === "all" ? " Find a company by name to narrow the list." : ""}</p>}
      {data && <p className="k-note inv-text">The ex-date is the first day the shares trade without the entitlement; the record date (on each row when it's another day) is when the company reads its list of holders. {data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
