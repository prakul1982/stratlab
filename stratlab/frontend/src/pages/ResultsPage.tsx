import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { ago, fmtDate, fmtTime, marketTz, pct, price, safeHref } from "../lib/format";
import { eyebrowOf } from "../lib/eyebrow";
import { LIVE_ROWS, useRowQuotes } from "../lib/rowQuotes";
import { REGION_NAME, screenCap, useRegion, type Region } from "../lib/research";
import { RegionSwitch } from "../components/Research";
import { CalendarFilters, NO_CAL, SIZE_NAME, calCount, keepFilters, keptFilters, type CalFilters, type Facets } from "../components/CalendarFilters";
import { Info } from "../components/ui";
import { Earlier } from "../components/Earlier";
import { Badge, Card, CardHead, CheckField, DataTable, EmptyState, ErrorState, Field, PageHeader, Seg, Signed, Skeleton, StockPicker, type Column } from "../components/kit";

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

/** A change as ▲ 4.0% or ▼ 5.0%, in the kit's colours: the arrow and the sign both say the direction. */
function Move({ v }: { v: number }) {
  return <Signed value={v}>{`${v > 0 ? "▲" : v < 0 ? "▼" : ""} ${Math.abs(v).toFixed(1)}%`.trim()}</Signed>;
}

function Growth({ v, of }: { v: number | null | undefined; of?: string | null }) {
  return v == null ? <span className="k-muted">–</span> : <span title={of ? `${of}` : undefined}><Signed value={v}>{pct(v)}</Signed></span>;
}

export function ResultsPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const { fail, notify } = useApp();
    const [q, setQ] = useState("");
  const [data, setData] = useState<ResultsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [filters, setFilters] = useState<Filters>(() => keptFilters(KEEP, NO_FILTERS));
  // the one day of "All companies" opened in full (DE-026: each day shows its first rows and says how many more it has)
  const [openDay, setOpenDay] = useState("");
  // another market or another set of companies is a different list: the find-a-company text and the old list don't carry over
  const [shownFor, setShownFor] = useState(`${region}|${scope}`);
  if (shownFor !== `${region}|${scope}`) { setShownFor(`${region}|${scope}`); setQ(""); setData(null); setOpenDay(""); }
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
        sector: filters.sector, index: filters.index, fo: filters.fo ? "true" : "", purpose: filters.purpose, on: filters.on, sort: sortName });
      for (const [k, v] of [...qs]) if (v === "") qs.delete(k);
      api<ResultsView>(`/research/results?${qs}`).then((x) => live && setData(x)).catch((e) => live && setError((e as Error).message));
    }, q ? 300 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [region, scope, q, openDay, tries, filters]);

  // ---- what is read for the rows in view (the first LIVE_ROWS), and nothing for the rest ----
  const inView = useMemo(() => (data?.weeks ?? []).flatMap((w) => w.rows).slice(0, LIVE_ROWS), [data]);
  const symbols = useMemo(() => [...new Set(inView.map((r) => r.symbol))], [inView]);
  const { quotes, quoteAt, live: isLive } = useRowQuotes(region, symbols);
  const [moves, setMoves] = useState<Record<string, MovesAnswer | null>>({});
  const [implied, setImplied] = useState<Record<string, Implied | null>>({});
  const [reading, setReading] = useState(false);
  const stamp = useRef(0);
  const pick = (sym: string) => inView.find((r) => r.symbol === sym);

  useEffect(() => {
    stamp.current += 1;
    setMoves({}); setImplied({});
    if (!symbols.length) return;
    const ticket = stamp.current;
    // earlier moves: six companies a call (the server reads that many price histories at a time), until every row in view has its answer
    void (async () => {
      setReading(true);
      for (let i = 0; i < symbols.length && ticket === stamp.current; i += 6) {
        const part = symbols.slice(i, i + 6);
        try {
          const got = (await api<{ moves: Record<string, MovesAnswer | null> }>(`/research/results/moves?region=${region}&symbols=${part.map(encodeURIComponent).join(",")}`)).moves ?? {};
          if (ticket !== stamp.current) return;
          setMoves((cur) => ({ ...cur, ...Object.fromEntries(part.map((s) => [s, got[s] ?? null])) }));
        } catch { if (ticket === stamp.current) setMoves((cur) => ({ ...cur, ...Object.fromEntries(part.map((s) => [s, null])) })); }
      }
      if (ticket === stamp.current) setReading(false);
      // the move the options price in: the stocks with futures and options, a day at a time, eight a call
      if (region !== "IN") return;
      const byDay = new Map<string, string[]>();
      for (const s of symbols) { const r = pick(s); if (r?.fo) byDay.set(r.date, [...(byDay.get(r.date) ?? []), s]); }
      for (const [day, list] of byDay) {
        for (let i = 0; i < list.length && ticket === stamp.current; i += 8) {
          const part = list.slice(i, i + 8);
          try {
            const got = (await api<{ implied: Record<string, Implied | null> }>(`/research/results/implied?symbols=${part.join(",")}&day=${day}`)).implied ?? {};
            if (ticket !== stamp.current) return;
            setImplied((cur) => ({ ...cur, ...Object.fromEntries(part.map((s) => [s, got[s] ?? null])) }));
          } catch { if (ticket === stamp.current) setImplied((cur) => ({ ...cur, ...Object.fromEntries(part.map((s) => [s, null])) })); }
        }
      }
    })();
    return () => { stamp.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbols.join(","), region]);

  const setScope = (s: string) => { const p = new URLSearchParams(params); p.set("scope", s); setParams(p, { replace: true }); };
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

  const columns: Column<ResultRow>[] = [
    { key: "co", header: "Company", rowHeader: true, wrap: true, cell: (r) => (
      <span className="k-stack">
        <span className="k-row">
          <Link className="link" to={`/research/${r.region}/${encodeURIComponent(r.symbol)}`}><b>{r.symbol}</b></Link>
          {scope === "all" && r.mine && <Badge tone="plain" dot={false}>Yours</Badge>}
          {r.fo && <Badge tone="plain" dot={false}>F&amp;O</Badge>}
        </span>
        {r.name && <span className="k-note k-muted">{r.name}</span>}
      </span>) },
    { key: "cap", header: "Market value", numeric: true, cell: (r) => (r.cap == null ? <span className="k-muted">–</span> : <span title={r.band ? `${SIZE_NAME[r.band]} company` : undefined}>{screenCap(r.cap, r.region)}</span>) },
    { key: "px", header: "Price now", numeric: true, cell: (r) => {
      const x = quotes[r.symbol];
      if (x?.price != null) return <span title={x.at ? `Read ${fmtTime(x.at, { tz: marketTz(region), zone: true })}` : undefined}>{price(x.price, cur)}</span>;
      return r.last == null ? <span className="k-muted">–</span> : <span className="k-muted" title={r.last_at ? `Last close, ${resultDay(r.last_at)}` : "Last close"}>{price(r.last, cur)}</span>;
    } },
    { key: "day", header: "Day", numeric: true, cell: (r) => {
      const x = quotes[r.symbol];
      return x?.change_pct == null ? <span className="k-muted">–</span> : <Signed value={x.change_pct}>{pct(x.change_pct, 2)}</Signed>;
    } },
    { key: "rev", header: "Revenue, a year on", numeric: true, info: "The latest reported quarter's revenue against the same quarter a year before, from the company's results as the app keeps them. Hover a figure for the quarters compared.", cell: (r) => <Growth v={r.q?.sales} of={r.q?.of} /> },
    { key: "pat", header: "Profit, a year on", numeric: true, info: "The latest reported quarter's net profit against the same quarter a year before. A quarter that came after a loss has no growth figure.", cell: (r) => <Growth v={r.q?.profit} of={r.q?.of} /> },
    { key: "mv", header: "Past results-day moves", wrap: true, info: "The change in the close from the session before a results day to the session after it, for this company's earlier results days the app has kept (up to six), from its daily prices. The figure is their average size; the arrows are the latest four.", cell: (r) => {
      const a = moves[r.symbol], m = a?.moves ?? r.moves;
      const since = a?.since;
      if (!m) return <span className="k-muted">{reading && a === undefined ? "Reading…" : "None kept yet"}</span>;
      return (
        <span className="k-stack">
          <b>±{m.avg.toFixed(1)}%</b>
          <span className="k-note k-muted">last {m.last.length}: {m.last.map((v, i) => <span key={i}><Move v={v} />{i < m.last.length - 1 ? " " : ""}</span>)}</span>
          {since && <span className="k-note k-muted">since results {resultDay(since.date)}: <Move v={since.pct} /></span>}
        </span>);
    } },
    ...(anyFo ? [{ key: "im", header: "Options imply", numeric: true, info: "For stocks with futures and options: the price of the at-the-money call and put together, as a share of the stock's price, for the first expiry on or after the results day. Read from the broker's option prices while it is connected.", cell: (r: ResultRow) => {
      if (!r.fo) return <span className="k-muted">–</span>;
      const i = implied[r.symbol];
      if (i === undefined) return <span className="k-muted">Reading…</span>;
      return i ? <span title={`At the ${i.strike.toLocaleString("en-IN")} strike, to the ${resultDay(i.expiry)} expiry`}>±{i.pct.toFixed(1)}%</span> : <span className="k-muted">Not available now</span>;
    } } as Column<ResultRow>] : []),
    { key: "mt", header: "Meeting", wrap: true, cell: (r) => (
      <span className="k-stack">
        <span>{r.purpose}{r.when ? `, ${r.when}` : ""}</span>
        {r.out && (
          <span className="k-note">
            Filed {resultDay(r.out.at)}{r.out.url ? <>: <a className="link" href={safeHref(r.out.url)} target="_blank" rel="noopener noreferrer">{r.out.title} ↗</a></> : `: ${r.out.title}`}
            {r.out.numbers.length > 0 && <span className="k-muted"> · {r.out.numbers.map((x) => `${x.label} ${x.value}`).join(" · ")} (as stated)</span>}
          </span>
        )}
      </span>) },
  ];

  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/research/results")} title="Results this week and next"
        lede={region === "IN" ? "Board meetings companies have called to consider their financial results, from their filings with the exchange."
          : "The dates US companies have set for their quarterly results, and the earnings release once it's filed."}
        asOf={data?.updated_at} asOfLabel="Updated" asOfTz={marketTz(region)} />
      <div className="k-toolbar">
        <RegionSwitch region={region} setRegion={setRegion} />
        <Seg label="Which companies" value={scope} onChange={setScope} options={[{ value: "mine", label: "My stocks" }, { value: "all", label: "All companies" }]} />
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
            {() => <Seg label="Purpose of the meeting" value={filters.purpose || "any"} onChange={(v) => set({ purpose: v === "any" ? "" : v })}
              options={[{ value: "any", label: "All" }, { value: "results", label: "Results only" }, { value: "more", label: "With other business" }]} />}
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
      {/* one table a day, each week under its heading; the days gone by this week fold away */}
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
              <DataTable label={`Results on ${resultDay(d)}`} rows={on} rowKey={(r) => `${r.symbol}-${r.date}`} columns={columns} stack phonePage={10} />
              {info.count > info.shown && (
                <div className="k-row">
                  <span className="k-note">Showing {info.shown} of {info.count.toLocaleString("en-IN")} on {resultDay(d)}.</span>
                  <button type="button" className="btn quiet sm" onClick={() => setOpenDay(d)}>Show all {info.count.toLocaleString("en-IN")}</button>
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
          {isLive ? `Prices as of ${fmtTime(quoteAt!, { tz: marketTz(region), zone: true })}, read for the first ${Math.min(symbols.length, LIVE_ROWS)} companies in view and again each minute while the market trades.`
            : symbols.length ? `Prices are each company's last close${data.weeks.flatMap((w) => w.rows).find((r) => r.last_at)?.last_at ? `, ${resultDay(data.weeks.flatMap((w) => w.rows).find((r) => r.last_at)!.last_at!)}` : ""}; the market is not trading now.` : ""}
          {" "}Past results-day moves are from the app's own daily prices; "Options imply" is the at-the-money straddle over the price. Facts, not a forecast.
        </p>
      )}
      {data && data.more > 0 && <p className="k-note">Each day shows its first {data.day_rows ?? 25} companies, yours first; {data.more.toLocaleString("en-IN")} more are a click away under their day, or find a company by name.</p>}
      {data && <p className="k-note inv-text">{data.note}{data.updated_at ? ` Updated ${ago(data.updated_at)}.` : ""}</p>}
    </div>
  );
}
