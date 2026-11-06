import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { SCOPE_OPTIONS } from "../lib/companyScope";
import { useCompanyScope } from "../lib/useCompanyScope";
import { ago, fmtDate, fmtTime, marketTz, pct, price, safeHref } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { LIVE_ROWS, useRowQuotes } from "../lib/rowQuotes";
import { pricesNote, readRows, sessionDayOf, shownOrder } from "../lib/rowReads";
import { REGION_NAME, screenCap, useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { CalendarFilters, NO_CAL, SIZE_NAME, calCount, keepFilters, keptFilters, type CalFilters, type Facets } from "../components/CalendarFilters";
import { Info } from "../components/ui";
import { Earlier } from "../components/Earlier";
import { Card, CardHead, CheckField, DataTable, EmptyState, ErrorState, Field, PageHeader, Seg, Select, Signed, Skeleton, StockPicker, Working, type Column } from "../components/kit";

/* /research/results: the dates companies have called their board meetings to consider results (or, in the US, set for
 * their quarterly results), week by week, for your stocks or every company, narrowed by company size, sector, index, F&O and the
 * meeting's purpose, one table a day with the figures a person looks at on a results day (market value, the price now, the
 * latest quarter against a year before, what the price did over earlier results days, the move the options price in), and the
 * figures once they are filed. */

interface ResultNumber { label: string; value: string }
export interface Moves { avg: number; n: number; last: number[]; dates: string[] }
interface Quarter { sales: number | null; profit: number | null; of: string | null }
export interface ResultRow {
  region: Region; symbol: string; name: string | null; date: string; when: string | null; purpose: string; url: string | null;
  mine?: boolean; out?: { at: string; title: string; url: string | null; numbers: ResultNumber[] } | null;
  cap?: number | null; band?: string | null; sector?: string | null; last?: number | null; last_at?: string | null; fo?: boolean; indices?: string[];
  q?: Quarter | null; moves?: Moves | null;
}
/** One day of a week: how many companies it has and how many of them came in this answer (DE-026). */
export interface ResultDay { date: string; count: number; shown: number }
interface Filters extends CalFilters { purpose: string }
interface ResultsView {
  region: Region; scope: "mine" | "all"; today: string; updated_at: string | null; more: number; mine_count: number; alerts: boolean; note: string;
  day_rows?: number; weeks: { label: string; from: string; to: string; rows: ResultRow[]; days?: ResultDay[] }[];
  total: number; matching: number; unknown_size: number; filters: Filters; facets: Facets;
}
interface Since { date: string; pct: number }
interface MovesAnswer { moves: Moves | null; since: Since | null }
interface Implied { pct: number; strike: number; expiry: string; straddle: number }

const KEEP = "stratlab.results.filters.v1";
const MORE_ROWS = 50;                // rows "Show more" adds to a day
export const NO_FILTERS: Filters = { ...NO_CAL, sort: "cap", purpose: "" };
const SORT_NAME: Record<string, string> = {
  cap: "Market value, largest first", name: "Company name", move: "Usual move on a results day", sales: "Revenue growth, a year on", profit: "Profit growth, a year on",
};

/** "Sat 31 Oct · 66 companies": a day's heading says how many it has, so a long day can't end without saying so (DE-026). */
export function dayHeading(iso: string, count: number, today: string) {
  return `${resultDay(iso)}${iso === today ? " · today" : ""} · ${count.toLocaleString("en-IN")} compan${count === 1 ? "y" : "ies"}`;
}

/** "Thu 15 Oct", from an ISO date, without the browser's time zone moving it a day. */
export function resultDay(iso: string) {
  return fmtDate(iso.slice(0, 10), { weekday: true, year: false });
}

export const filterCount = (f: Filters) => calCount(f, "cap") + (f.purpose ? 1 : 0);

/** A change as ▲4.0% or ▼5.0%, in the kit's colours: the arrow and the sign both say the direction. */
function Move({ v, bare = false }: { v: number; /** without the % (a row of them under a heading that says percent) */ bare?: boolean }) {
  return <Signed value={v}>{`${v > 0 ? "▲" : v < 0 ? "▼" : ""}${Math.abs(v).toFixed(1)}${bare ? "" : "%"}`}</Signed>;
}

function Growth({ v, of }: { v: number | null | undefined; of?: string | null }) {
  return v == null ? <span className="k-muted">–</span> : <span title={of ? `${of}` : undefined}><Signed value={v}>{pct(v)}</Signed></span>;
}

export function ResultsPage() {
  const [region, setRegion] = useRegion();
  const [scope, setScope] = useCompanyScope();
  const { fail, notify } = useApp();
    const [q, setQ] = useState("");
  const [data, setData] = useState<ResultsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [filters, setFilters] = useState<Filters>(() => keptFilters(KEEP, NO_FILTERS));
  // the one day of "All companies" opened in full (DE-026: each day shows its first rows and says how many more it has)
  const [openDay, setOpenDay] = useState("");
  // how many of that day's rows to show: 50 more at each press, never a 200-company day in one go (owner, 5 Nov: the page was slow to open)
  const [dayRows, setDayRows] = useState(0);
  // another market or another set of companies is a different list: the find-a-company text and the old list don't carry over
  const [shownFor, setShownFor] = useState(`${region}|${scope}`);
  if (shownFor !== `${region}|${scope}`) { setShownFor(`${region}|${scope}`); setQ(""); setData(null); setOpenDay(""); setDayRows(0); }
  // a sector or an index of one market is not the other's
  const [filtersFor, setFiltersFor] = useState(region);
  if (filtersFor !== region) { setFiltersFor(region); setFilters((f) => ({ ...f, sector: "", index: "", fo: false })); }
  useEffect(() => { keepFilters(KEEP, filters); }, [filters]);
  const set = (p: Partial<Filters>) => { setOpenDay(""); setFilters((f) => ({ ...f, ...p })); };
  const sortName = filters.sort || "cap";

  useEffect(() => {
    let live = true;
    setError(null);
    const t = setTimeout(() => {
      const qs = new URLSearchParams({ region, scope, q: scope === "all" ? q : "", day: scope === "all" ? openDay : "", size: filters.size.join(","),
        sector: filters.sector, index: filters.index, fo: filters.fo ? "true" : "", purpose: filters.purpose, on: filters.on, sort: sortName,
        day_rows: scope === "all" && openDay && dayRows ? String(dayRows) : "" });
      for (const [k, v] of [...qs]) if (v === "") qs.delete(k);
      api<ResultsView>(`/research/results?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, q, openDay, dayRows, tries, filters]);

  // ---- what is read for the rows on the page, in the order a person sees them (LIVE4-001: the first 48 in the list's order were read, which
  // were often the folded days gone by, so today's rows and every row "Show 50 more" added sat on "Reading" for good) ----
  const shown = useMemo(() => (data ? shownOrder(data.weeks, data.today) : []), [data]);
  const symbols = useMemo(() => [...new Set(shown.map((r) => r.symbol))], [shown]);
  const quoted = useMemo(() => symbols.slice(0, LIVE_ROWS), [symbols]);
  const { quotes, quoteAt, live: isLive, reading: quotesReading } = useRowQuotes(region, quoted);
  const [moves, setMoves] = useState<Record<string, MovesAnswer | null>>({});
  const [implied, setImplied] = useState<Record<string, Implied | null>>({});
  // false once the server says option prices can't be read now (the broker not connected): the column is hidden and one line says why
  const [optionsOn, setOptionsOn] = useState(true);
  const asked = useRef({ moves: new Set<string>(), implied: new Set<string>() });
  const gen = useRef(0);
  // another market starts from nothing; a longer list of the same market keeps what was read and reads only the rows that are new
  useEffect(() => {
    gen.current += 1;
    asked.current = { moves: new Set(), implied: new Set() };
    setMoves({}); setImplied({}); setOptionsOn(true);
    return () => { gen.current += 1; };
  }, [region]);

  // the two extra columns are read at the same time, a few calls at once; a company the server could not get to in time (its price source
  // busy, or the call's few seconds spent) comes back "pending" and is asked again until READ_DEADLINE_MS, when what is left shows a dash
  // (owner, 5 Nov: never a cell stuck on its loading bar)
  useEffect(() => {
    if (!symbols.length) return;
    const ticket = gen.current;
    const alive = () => ticket === gen.current;
    const newMoves = symbols.filter((s) => !asked.current.moves.has(s));
    newMoves.forEach((s) => asked.current.moves.add(s));
    const merge = <T,>(set: (f: (cur: Record<string, T | null>) => Record<string, T | null>) => void) =>
      (got: Record<string, T | null>) => set((cur) => ({ ...cur, ...got }));
    // earlier moves: twelve companies a call (the server reads six price histories a call and answers the rest at once from what it keeps)
    if (newMoves.length) {
      void readRows<MovesAnswer>(newMoves, async (part) => {
        const r = await api<{ moves?: Record<string, MovesAnswer | null>; pending?: string[] }>(`/research/results/moves?region=${region}&symbols=${part.map(encodeURIComponent).join(",")}`);
        return { got: r.moves ?? {}, pending: r.pending ?? [] };
      }, merge(setMoves), { size: 12, parallel: 3, alive });
    }
    // the move the options price in: the stocks with futures and options, eight a call, each day's stocks to that day's expiry
    if (region === "IN") {
      const byDay = new Map<string, string[]>();
      for (const r of shown) {
        if (!r.fo || asked.current.implied.has(r.symbol)) continue;
        asked.current.implied.add(r.symbol);
        byDay.set(r.date, [...(byDay.get(r.date) ?? []), r.symbol]);
      }
      for (const [day, list] of byDay) {
        void readRows<Implied>(list, async (part) => {
          const r = await api<{ implied?: Record<string, Implied | null>; pending?: string[]; available?: boolean }>(`/research/results/implied?symbols=${part.map(encodeURIComponent).join(",")}&day=${day}`);
          if (r.available === false && alive()) setOptionsOn(false);
          return { got: r.implied ?? {}, pending: r.pending ?? [] };
        }, merge(setImplied), { size: 8, parallel: 1, alive });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(","), region]);

  const toggleAlerts = async () => {
    if (!data) return;
    try {
      const r = await api<{ alerts: boolean }>("/research/results/alerts", { method: "PUT", body: { on: !data.alerts } });
      setData({ ...data, alerts: r.alerts });
      notify(r.alerts ? "You'll get a message on the morning of each results day for your stocks, and when the results are filed." : "Results messages off.");
    } catch (e) { fail(e); }
  };
  const empty = data && data.weeks.every((w) => w.rows.length === 0);
  const n = filterCount(filters);
  const cur = region === "IN" ? "INR" : "USD";
  const anyFo = region === "IN" && !!data?.weeks.some((w) => w.rows.some((r) => r.fo));
  const showImplied = anyFo && optionsOn;

  // the line under the tables: the session the prices read are of, and the rows still on an older stored close (LIVE5-001: the
  // first row's stored close named the day, "Thu 5 Nov", under rows showing Fri 6 Nov's)
  const tz = marketTz(region);
  const closeDay = sessionDayOf(Object.values(quotes).map((x) => x?.at), tz) ?? shown.find((r) => r.last_at)?.last_at?.slice(0, 10) ?? null;
  const olderRows = closeDay ? [...new Map(shown.filter((r) => quotes[r.symbol]?.price == null && r.last != null && r.last_at && r.last_at.slice(0, 10) < closeDay)
    .map((r) => [r.symbol, r])).values()] : [];
  const pricesLine = pricesNote({ live: isLive, asOf: quoteAt ? fmtTime(quoteAt, { tz, zone: true }) : null, rows: symbols.length, cap: LIVE_ROWS, closeDay,
    older: olderRows.length, olderDay: olderRows.map((r) => r.last_at!.slice(0, 10)).sort()[0] ?? null, reading: quotesReading }, resultDay);

  const columns: Column<ResultRow>[] = [
    // two lines a row (owner, 5 Nov: "still shit ui", rows stacked company, name, purpose and filing link four lines high): the symbol and
    // its tags with the name beside it, then the meeting and a small link to the filing; a long line ends in "…" with the whole of it on hover
    { key: "co", header: "Company", rowHeader: true, cell: (r) => {
      const purpose = `${r.purpose}${r.when ? `, ${r.when}` : ""}`;
      const numbers = r.out?.numbers.length ? ` · ${r.out.numbers.map((x) => `${x.label} ${x.value}`).join(" · ")} (as stated)` : "";
      return (
        <span className="res-co">
          <span className="res-sym">
            <Link className="link" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
            {scope === "all" && r.mine && <span className="k-note k-muted">Yours</span>}
            {r.fo && <span className="k-note k-muted">F&amp;O</span>}
            {r.name && <span className="k-note k-muted res-name" title={r.name}>{r.name}</span>}
          </span>
          <span className={`k-note k-muted res-sub${!r.out && !r.when && /^financial results$/i.test(r.purpose.trim()) ? " res-plain" : ""}`} title={r.out ? `${purpose} · Filed ${resultDay(r.out.at)}: ${r.out.title}${numbers}` : purpose}>
            {purpose}
            {r.out && <> · {r.out.url
              ? <a className="link res-filed" href={safeHref(r.out.url)} target="_blank" rel="noopener noreferrer">Filed {resultDay(r.out.at)} ↗</a>
              : `Filed ${resultDay(r.out.at)}`}{numbers}</>}
          </span>
        </span>);
    } },
    // LIVE4-010: short headers that stay on one line at 1440 (the (i) says the rest); on a phone each company is two short lines (the table's
    // `compact`): the symbol with the price and the day's move at its right, then the usual move and what the options imply; market value,
    // revenue and profit stay on the desktop table and the company page (a fifth figure ran the line onto a third)
    { key: "cap", header: "Market value", numeric: true, phone: false, cell: (r) => (r.cap == null ? <span className="k-muted">–</span> : <span title={r.band ? `${SIZE_NAME[r.band]} company` : undefined}>{screenCap(r.cap, r.region)}</span>) },
    { key: "px", header: "Price", numeric: true, brief: true, csvHeader: "Price now", cell: (r) => {
      const x = quotes[r.symbol];
      if (x?.price != null) return <span title={x.at ? `Read ${fmtTime(x.at, { tz: marketTz(region), zone: true })}` : undefined}>{price(x.price, cur)}</span>;
      return r.last == null ? <span className="k-muted">–</span> : <span className="k-muted" title={r.last_at ? `Last close, ${resultDay(r.last_at)}` : "Last close"}>{price(r.last, cur)}</span>;
    } },
    { key: "day", header: "Day", numeric: true, brief: true, cell: (r) => {
      const x = quotes[r.symbol];
      return x?.change_pct == null ? <span className="k-muted">–</span> : <Signed value={x.change_pct}>{pct(x.change_pct, 2)}</Signed>;
    } },
    { key: "rev", header: "Revenue", csvHeader: "Revenue YoY", numeric: true, phone: false, info: "Year on year (YoY): the latest reported quarter's revenue against the same quarter a year before (YoY), from the company's results as the app keeps them. Hover a figure for the quarters compared.", cell: (r) => <Growth v={r.q?.sales} of={r.q?.of} /> },
    { key: "pat", header: "Profit", csvHeader: "Profit YoY", numeric: true, phone: false, info: "Year on year: the latest reported quarter's net profit against the same quarter a year before. A quarter that came after a loss has no growth figure.", cell: (r) => <Growth v={r.q?.profit} of={r.q?.of} /> },
    { key: "mv", header: "Usual move", cardLabel: "Usual move", csvHeader: "Past results-day moves", wrap: true, info: "Past results-day moves: the change in the close from the session before a results day to the session after it, for this company's earlier results days the app has kept (up to six), from its daily prices. The figure is their average size; the arrows under it are the latest four, newest first, in percent.", cell: (r) => {
      const a = moves[r.symbol], m = a?.moves ?? r.moves;
      const since = a?.since;
      if (!m && !since) return a === undefined ? <Working inline label="Reading earlier results days" /> : <span className="k-muted">–</span>;
      return (
        <span className="res-mv">
          <span className="res-mv-top">
            {m ? <b>±{m.avg.toFixed(1)}%</b> : <span className="k-muted">–</span>}
            {since && <span className="k-note k-muted" title={`Since the results of ${resultDay(since.date)}, close to latest close`}>since {resultDay(since.date)} <Move v={since.pct} /></span>}
          </span>
          {m && <span className="k-note res-moves" title="The latest four, newest first, in %">{m.last.map((v, i) => <Move key={i} v={v} bare />)}</span>}
        </span>);
    } },
    ...(showImplied ? [{ key: "im", header: "Options imply", cardLabel: "Implied", csvHeader: "Options imply", numeric: true, info: "For stocks with futures and options: the price of the at-the-money call and put together, as a share of the stock's price, for the first expiry on or after the results day. Read from the broker's option prices while it is connected.", cell: (r: ResultRow) => {
      if (!r.fo) return <span className="k-muted">–</span>;
      const i = implied[r.symbol];
      if (i === undefined) return <Working inline label="Reading the option prices" />;
      return i ? <span title={`At the ${i.strike.toLocaleString("en-IN")} strike, to the ${resultDay(i.expiry)} expiry`}>±{i.pct.toFixed(1)}%</span> : <span className="k-muted" title="No option prices for it now">–</span>;
    } } as Column<ResultRow>] : []),
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/results")} title="Results this week and next"
        lede={region === "IN" ? "Board meetings companies have called to consider their financial results, from their filings with the exchange."
          : "The dates US companies have set for their quarterly results, and the earnings release once it's filed."}
        asOf={data?.updated_at} asOfLabel="Updated" asOfTz={marketTz(region)} />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={setRegion} />
        <Seg label="Which companies" value={scope} onChange={setScope} options={SCOPE_OPTIONS} />
      </div>
      {(scope === "all" || data) && (
        <CalendarFilters region={region} facets={data?.facets ?? null} filters={filters} set={set} firstSort="cap" sorts={SORT_NAME} active={n}
          total={data?.total ?? null} matching={data?.matching ?? null} unknownSize={data?.unknown_size ?? 0} onClear={() => set(NO_FILTERS)} testId="results-count"
          days={[{ value: "", label: "Every day" }, { value: "today", label: "Today" }, { value: "tomorrow", label: "Tomorrow" },
            ...(data?.weeks ?? []).flatMap((w) => (w.days ?? []).map((d) => ({ value: d.date, label: resultDay(d.date) })))]}
          search={<>
            {scope === "all" && (
              <Field key={region} label="Find a company">
                {(id) => <StockPicker id={id} market={region} onText={setQ} onPick={(s) => setQ(s)} placeholder={region === "IN" ? "Like TCS or Infosys" : "Like AAPL or Apple"} />}
              </Field>
            )}
            {data && (
              <CheckField checked={data.alerts} onChange={toggleAlerts}
                label={<>Message me on the morning of a results day for my stocks, and when the results are filed
                  <Info>Sent by phone notification or Telegram, whichever you set up in Settings. If you get the My Stocks newsletter, it lists the week's results dates too.</Info></>} />
            )}
          </>}>
          <Field label="Meeting">
            {(id) => <Select id={id} value={filters.purpose || "any"} onChange={(v) => set({ purpose: v === "any" ? "" : v })}
              options={[{ value: "any", label: "All meetings" }, { value: "results", label: "Results only" }, { value: "more", label: "With other business" }]} />}
          </Field>
        </CalendarFilters>
      )}
      {error && <ErrorState title="The results calendar couldn't be opened" action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>{error}</ErrorState>}
      {!data && !error && <Card><Skeleton label="Opening the results calendar" lines={4} /></Card>}
      {data && empty && (
        <Card>
          <EmptyState title={n ? "No company matches these filters" : scope === "mine" ? (data.mine_count ? "None of your stocks has a results date in these two weeks" : "No stocks to show results dates for yet") : "No results dates found"}
            action={n ? { label: "Clear filters", onClick: () => set(NO_FILTERS) } : scope === "mine" ? { label: "See all companies", onClick: () => setScope("all") } : undefined}>
            {n ? `${data.total.toLocaleString("en-IN")} ${data.total === 1 ? "company has" : "companies have"} a results date in these two weeks; none meets every filter.`
              : scope === "mine"
              ? (data.mine_count ? `A later date, if a company has set one, shows on its own page.` : `You have no ${REGION_NAME[region]} stocks yet: they come from your watchlist, notebooks and paper sessions.`)
              : q ? "No company by that name has a results date in these two weeks." : "No results dates announced for these two weeks yet."}
          </EmptyState>
        </Card>
      )}
      {/* one table a day, each week under its heading, the weeks one above the other (a table of this width has no room beside another card, which
          is also what left a short week as a tall empty card beside a full one: ui-lint R1, 29 Oct); the days gone by this week fold away */}
      {data && !empty && data.weeks.map((w) => {
        const days = [...new Set(w.rows.map((r) => r.date))];
        const ahead = days.filter((d) => d >= data.today), past = days.filter((d) => d < data.today);
        const about = (d: string) => w.days?.find((x) => x.date === d);
        const day = (d: string) => {
          const on = w.rows.filter((r) => r.date === d);
          const info = about(d) ?? { date: d, count: on.length, shown: on.length };
          return (
            <div key={d} className="inv-day" data-testid="results-day">
              <span className="k-eyebrow">{dayHeading(d, info.count, data.today)}</span>
              <DataTable csv={`results ${d}`} label={`Results on ${resultDay(d)}`} rows={on} rowKey={(r) => `${r.symbol}-${r.date}`} columns={columns} stack compact phonePage={10} />
              {info.count > info.shown && (
                <div className="k-row">
                  <span className="k-note">Showing {info.shown} of {info.count.toLocaleString("en-IN")} on {resultDay(d)}.</span>
                  <button type="button" className="btn quiet sm" onClick={() => { setOpenDay(d); setDayRows(info.shown + MORE_ROWS); }}>
                    Show {Math.min(MORE_ROWS, info.count - info.shown).toLocaleString("en-IN")} more</button>
                </div>
              )}
            </div>
          );
        };
        return (
          <Card key={w.label}>
            <CardHead title={w.label} actions={<span className="k-note">{resultDay(w.from)} to {resultDay(w.to)}</span>} />
            {days.length === 0 ? <span className="k-small k-muted">{n ? "No company that meets the filters this week." : "Nothing announced for this week yet."}</span>
              : ahead.length ? ahead.map(day) : <span className="k-small k-muted">Nothing left this week.</span>}
            <Earlier label="Earlier this week" count={w.rows.filter((r) => r.date < data.today).length} className="in-card">
              {past.map(day)}
            </Earlier>
          </Card>
        );
      })}
      {data && !empty && (
        <p className="k-note" data-testid="results-prices">
          {pricesLine}
          {" "}Past results-day moves are from the app's own daily prices{showImplied ? `; "Options imply" is the at-the-money straddle over the price` : ""}.
          {anyFo && !optionsOn ? " Option prices can't be read right now, so the move they imply is not shown." : ""} Facts, not a forecast.
        </p>
      )}
      {data && data.more > 0 && <p className="k-note">Each day shows its first {data.day_rows ?? 25} companies, yours first; {data.more.toLocaleString("en-IN")} more are a click away under their day, or find a company by name.</p>}
      {data && <p className="k-note inv-text">{data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
