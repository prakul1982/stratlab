import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { useApp } from "../lib/app";
import { CAL_KEPT, CAL_SHOWS, askedShow, calDefault, calHref, keptShow, type CalKept, type CalShow } from "../lib/calendarShow";
import { fmtDate, istToday, price } from "../lib/format";
import { loadEvents, type EventsView } from "../lib/marketEvents";
import { useMenuSpace } from "../lib/menuSpace";
import { usePersisted } from "../lib/persist";
import { useRegion, useWatchlist, type Region } from "../lib/research";
import { MINE_NAME, SPACES } from "../lib/spaces";
import type { IpoList } from "../lib/ipo";
import { TYPES, TYPE_NAME, ipoRows, mergeRows, type CalRow, type CalType } from "../lib/calendarRows";
import type { ResultRow, ResultDay } from "./ResultsPage";
import type { ActionRow } from "./CorpActionsPage";
import { RegionSwitch } from "../components/Research";
import { EventsPage } from "./trade/EventsPage";
import { MoneyCalendarPage } from "./money/MoneyCalendarPage";
import { SIZE_NAME, type Facets } from "../components/CalendarFilters";
import { Card, ChipBar, ChipSet, DataTable, ErrorState, Field, PageHeader, Select, Skeleton, type Column } from "../components/kit";

/* The one Calendar (IA-1 item 3; cal94, owner 26 Nov: one Calendar, fixed in the sidebar). One row of filters switches what it shows:
 * every date, your stocks' results and ex-dates, the market's events and F&O expiries, results days, dividends and splits, IPO dates,
 * or the person's own money dates. It opens on the dates for where you are (lib/calendarShow); the filter is the address, and the last
 * one picked in each space is kept on this device. The market events and money dates are those pages' own full views (reminders, your
 * own dates, the calendar feed), at their old addresses; the others are one table of the days the results calendar covers (this week
 * and next), read from the same answers as the research tables (Results, Corporate actions, IPOs), so the two never disagree. */

type ResultsView = { weeks: { from: string; to: string; rows: ResultRow[]; days?: ResultDay[] }[]; facets: Facets; today: string };
type CorpView = { ahead: ActionRow[] };
type MoneyView = { events: { id: string; date: string; title: string; cat: string; detail: string }[] };

// in this page's own download: loaded on their own after it, the title was drawn twice and the page moved (CLS)

/** Each table filter: the kinds of date it lists, its title and line, and the research table it links to for the full picture. */
const VIEWS: Record<Exclude<CalShow, "events" | "money">, { types: CalType[]; title: string; lede: string; full?: [string, string] }> = {
  all: { types: TYPES, title: "All dates", lede: "Results days, corporate actions, IPO dates, the market's own events and your money dates, day by day, this week and next." },
  mine: { types: ["results", "action"], title: "My stocks' dates", lede: "Results days, dividends, splits and other corporate actions of your holdings, watchlist, notebooks and paper sessions, this week and next." },
  results: { types: ["results"], title: "Results days", lede: "The companies announcing results this week and next, day by day.", full: ["/research/results", "Results"] },
  actions: { types: ["action"], title: "Dividends & splits", lede: "Dividends, bonus issues, splits and other corporate actions by ex-date, this week and next.", full: ["/research/corporate-actions", "Corporate actions"] },
  ipos: { types: ["ipo"], title: "IPO dates", lede: "IPO openings, closings, allotments and listings, India's or the US's, this week and next.", full: ["/invest/ipos", "IPOs"] },
};

export function CalendarPage() {
  const space = useMenuSpace();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const { me } = useApp();
  const { items: watching } = useWatchlist();
  const [kept, setKept] = usePersisted<CalKept>(CAL_KEPT, {});
  const asked = askedShow(pathname, search);
  const remembered = keptShow(kept, space);
  // My space and Invest open on your stocks' dates when you have a watchlist or holdings: decided once the watchlist is read
  const waiting = !asked && !remembered && space !== "trade" && space !== "money" && !me?.has_holdings && watching === null;
  const show: CalShow | null = asked ?? remembered ?? (waiting ? null : calDefault(space, !!me?.has_holdings || !!watching?.length));
  const pick = (v: string) => {
    const next = v as CalShow;
    setKept((cur) => ({ ...(cur && typeof cur === "object" ? cur : {}), [space]: next }));
    if (next !== show || !asked) navigate(calHref(next));
  };
  const eyebrow = `${space === "mine" ? MINE_NAME : SPACES[space].label} · Calendar`;
  const chips = <ChipBar label="Which dates" value={show ?? ""} onChange={pick} wrap options={CAL_SHOWS} />;
  const row = <Card label="Which dates" className="cal-show" testId="cal-show">{chips}</Card>;
  if (show === "events") return <EventsPage top={row} eyebrow={eyebrow} />;
  if (show === "money") return <MoneyCalendarPage top={row} eyebrow={eyebrow} />;
  if (!show) return <div className="k-page"><PageHeader eyebrow={eyebrow} title="Calendar" />{row}<Card><Skeleton label="Reading the calendars" /></Card></div>;
  return <DatesTable key={show} show={show} eyebrow={eyebrow} chips={chips} />;
}

/** The table filters: one table of every dated thing of the kinds `show` lists, this week and next. */
function DatesTable({ show, eyebrow, chips }: { show: Exclude<CalShow, "events" | "money">; eyebrow: string; chips: ReactNode }) {
  const view = VIEWS[show];
  const types = view.types;
  const want = (t: CalType) => types.includes(t);
  const [region, setRegion] = useRegion();
  const scope = show === "mine" ? "mine" : "all";
  const [size, setSize] = useState<string[]>([]);
  const [sector, setSector] = useState("");
  // AUTO-LOAD (site87, owner: no "Show all N on <day>"): a day of "every company" with more results than the first answer holds is read in
  // full on its own as the reader nears the end of the table, one day at a time (DE-026); each day's whole list replaces its first rows
  const [fullDays, setFullDays] = useState<Record<string, ResultRow[]>>({});
  const [dayBusy, setDayBusy] = useState(false);
  const resetDays = () => setFullDays({});
  const [res, setRes] = useState<ResultsView | null | "error">(null);
  const [corp, setCorp] = useState<CorpView | null | "error">(null);
  const [ipos, setIpos] = useState<IpoList | null | "error">(null);
  const [ev, setEv] = useState<EventsView | null | "error">(null);
  const [money, setMoney] = useState<MoneyView | null | "error">(null);
  const [tries, setTries] = useState(0);
  // a sector of one market is not the other's
  const [sectorFor, setSectorFor] = useState(region);
  if (sectorFor !== region) { setSectorFor(region); setSector(""); resetDays(); }
  const qs = (extra: Record<string, string> = {}) => {
    const q = new URLSearchParams({ region, scope, size: scope === "all" ? size.join(",") : "", sector: scope === "all" ? sector : "", ...extra });
    for (const [k, v] of [...q]) if (!v) q.delete(k);
    return q.toString();
  };
  useEffect(() => {
    let live = true;
    setRes(null); setCorp(null); setFullDays({});
    api<ResultsView>(`/research/results?${qs()}`).then((x) => live && setRes(x)).catch(() => live && setRes("error"));
    // each filter reads only its own kinds of date; the results calendar always, as it says the days the table covers
    if (want("action")) api<CorpView>(`/research/corp-actions?${qs()}`).then((x) => live && setCorp(x)).catch(() => live && setCorp("error"));
    return () => { live = false; };
  }, [region, scope, size, sector, tries]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!want("ipo")) return;
    let live = true;
    setIpos(null);
    api<IpoList>(`/invest/ipos?market=${region}`).then((x) => live && setIpos(x)).catch(() => live && setIpos("error"));
    return () => { live = false; };
  }, [region, tries]);
  useEffect(() => { if (!want("event")) return; let live = true; loadEvents().then((x) => live && setEv(x ?? "error")); return () => { live = false; }; }, [tries]);
  // the window: today to the last day the results calendar covers (this week and next)
  const today = res && res !== "error" ? res.today : istToday();
  const until = res && res !== "error" && res.weeks.length ? res.weeks[res.weeks.length - 1].to : fmtIso(addDays(today, 13));
  // LIVE13A-011: read once the results calendar has said its window (read before it, on a guessed window, and again after it, the list
  // was drawn, emptied and drawn again: CLS 0.278 on a first load)
  const resReady = res !== null;
  useEffect(() => {
    if (!resReady || !want("money")) return;
    let live = true;
    setMoney(null);
    api<MoneyView>(`/money/calendar?start=${today}&end=${until}&cats=tax,money,custom`).then((x) => live && setMoney(x)).catch(() => live && setMoney("error"));
    return () => { live = false; };
  }, [today, until, tries, resReady]);

  const rows = useMemo(() => {
    const ok = <T,>(v: T | null | "error"): v is T => !!v && v !== "error";
    const parts: CalRow[][] = [];
    if (ok(res)) parts.push([...res.weeks.flatMap((w) => w.rows).filter((r) => !fullDays[r.date.slice(0, 10)]), ...Object.values(fullDays).flat()].filter((r) => r.date >= today).map((r) => ({
      id: `res:${r.region}:${r.symbol}:${r.date}`, date: r.date.slice(0, 10), type: "results" as const, name: r.name ?? r.symbol, mine: r.mine,
      to: `/research/${r.region}/${encodeURIComponent(r.symbol)}`, detail: [r.purpose, r.when].filter(Boolean).join(" · ") })));
    if (ok(corp)) parts.push(corp.ahead.filter((a) => a.ex_date <= until).map((a) => ({
      id: `act:${a.id}`, date: a.ex_date.slice(0, 10), type: "action" as const, name: a.name ?? a.symbol, mine: a.mine,
      to: `/research/${a.region}/${encodeURIComponent(a.symbol)}`,
      detail: [`Ex-date: ${a.label}`, a.kind === "dividend" && a.amount ? `${price(a.amount, a.currency, a.amount < 1 ? 4 : 2)} a share` : null, a.record_date ? `record date ${fmtDate(a.record_date.slice(0, 10), { year: false })}` : null].filter(Boolean).join(" · ") })));
    if (ok(ipos)) parts.push(ipoRows([...(ipos.tabs.upcoming ?? []), ...(ipos.tabs.open ?? []), ...(ipos.tabs.closed ?? [])], today, until));
    if (ok(ev)) parts.push(ev.events.filter((e) => e.date >= today && e.date <= until && (region === "US" ? e.kind === "us" : e.kind !== "us")).map((e) => ({
      id: `ev:${e.id}`, date: e.date, type: "event" as const, name: e.title, to: "/trade/events", detail: [e.time ? `${e.time} IST` : null, e.figure ?? null].filter(Boolean).join(" · ") || ev.kinds[e.kind] || "" })));
    if (ok(money)) parts.push(money.events.filter((e) => e.date >= today && e.date <= until).map((e) => ({
      id: `money:${e.id}`, date: e.date, type: "money" as const, name: e.title, to: "/money/calendar", detail: e.detail })));
    return mergeRows(parts).filter((r) => types.includes(r.type));
  }, [res, corp, ipos, ev, money, types, today, until, region, fullDays]);

  const failed = ([[res, "results"], [corp, "corporate actions"], [ipos, "IPOs"], [ev, "market events"], [money, "your money dates"]] as const).filter(([v]) => v === "error").map(([, w]) => w);
  const loading = res === null || (want("action") && corp === null) || (want("ipo") && ipos === null) || (want("event") && ev === null) || (want("money") && money === null);
  // size and sector narrow the companies' own dates (results, corporate actions), on every company
  const narrows = scope === "all" && (want("results") || want("action"));
  // a day of "every company" that has more results than came in this answer is read in full as the reader nears the end (DE-026)
  const cut = res && res !== "error" && scope === "all" ? res.weeks.flatMap((w) => w.days ?? []).filter((d) => d.count > d.shown && !fullDays[d.date]) : [];
  const loadDay = () => {
    const d = cut[0];
    if (!d || dayBusy) return;
    setDayBusy(true);
    api<ResultsView>(`/research/results?${qs({ day: d.date })}`)
      .then((x) => setFullDays((cur) => ({ ...cur, [d.date]: x.weeks.flatMap((w) => w.rows).filter((r) => r.date.slice(0, 10) === d.date) })))
      .catch(() => setFullDays((cur) => ({ ...cur, [d.date]: (res && res !== "error" ? res.weeks.flatMap((w) => w.rows) : []).filter((r) => r.date.slice(0, 10) === d.date) })))
      .finally(() => setDayBusy(false));
  };
  const hiddenResults = cut.reduce((a, d) => a + d.count - d.shown, 0);
  const facets = res && res !== "error" ? res.facets : null;
  const cols: Column<CalRow>[] = [
    { key: "date", header: "Day", rowHeader: true, cell: (r) => <span className="nowrap">{fmtDate(r.date, { weekday: true, year: false })}{r.date === today ? " · today" : ""}</span> },
    { key: "type", header: "Type", cell: (r) => TYPE_NAME[r.type] },
    { key: "name", header: "What", wrap: true, cell: (r) => <><Link className="link" to={r.to}>{r.name}</Link>{r.mine && <span className="k-note k-muted"> · yours</span>}</> },
    { key: "detail", header: "Detail", wrap: true, cell: (r) => r.detail || <span className="k-muted">–</span> },
  ];
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrow} title={view.title} lede={view.lede} />
      <Card label="Which dates" className="cal-filters" testId="cal-show">
        {chips}
        <div className="k-toolbar">
          <RegionSwitch region={region} setRegion={(r: Region) => setRegion(r)} />
        </div>
        {/* LIVE13A-011: the size and sector row holds its place while the first answer is out (it arrived with it and pushed the list down
            88px); disabled until then */}
        {narrows && !facets && res !== "error" && (
          <div className="k-toolbar" data-testid="cal-facets-wait" aria-busy="true">
            <div className="k-field">
              <span className="k-lbl">Company size</span>
              <div className="k-chipset" role="group" aria-label="Company size">{Object.values(SIZE_NAME).map((l) => <button key={l} type="button" className="k-chip" aria-pressed={false} disabled>{l}</button>)}</div>
            </div>
            <Field label={region === "IN" ? "Sector" : "Industry division"}>
              {(id) => <Select id={id} value="" disabled onChange={() => undefined} options={[{ value: "", label: "All" }]} />}
            </Field>
          </div>
        )}
        {narrows && facets && (
          <div className="k-toolbar">
            <div className="k-field">
              <span className="k-lbl">Company size</span>
              <ChipSet label="Company size" options={facets.sizes.map((s) => ({ value: s.id, label: SIZE_NAME[s.id] ?? s.label }))} on={size}
                onToggle={(v) => { resetDays(); setSize((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v])); }} />
            </div>
            <Field label={region === "IN" ? "Sector" : "Industry division"}>
              {(id) => <Select id={id} value={sector} onChange={(v) => { resetDays(); setSector(v); }}
                options={[{ value: "", label: "All" }, ...facets.sectors.map((s) => ({ value: s.name, label: s.name })), ...(sector && !facets.sectors.some((s) => s.name === sector) ? [{ value: sector, label: sector }] : [])]} />}
            </Field>
          </div>
        )}
        <p className="k-small k-muted" data-testid="cal-count">
          {loading ? "Reading the calendars…" : `${rows.length.toLocaleString("en-IN")} date${rows.length === 1 ? "" : "s"} from ${fmtDate(today, { weekday: true, year: false })} to ${fmtDate(until, { weekday: true, year: false })}`}
          {scope === "mine" ? ". Results and corporate actions for your holdings, watchlist, notebooks and paper sessions." : "."}
          {view.full && <> Each company's figures and every filter are on the <Link className="link" to={view.full[0]}>{view.full[1]}</Link> table.</>}
        </p>
      </Card>
      {failed.length > 0 && <ErrorState title={`Some dates couldn't be read: ${failed.join(", ")}`} action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>The rest are below.</ErrorState>}
      {/* LIVE13A-011: the list is drawn once, when every calendar has answered (drawn as each came, rows were added and taken away) */}
      {loading ? <Card><Skeleton label="Reading the calendars" /></Card> : (
        <Card label="Dates" testId="cal-all">
          <DataTable csv="money calendar" stack label="Every date, this week and next" columns={cols} rows={rows} rowKey={(r) => r.id}
            more={hiddenResults > 0 && types.includes("results") ? { total: rows.length + hiddenResults, load: loadDay, busy: dayBusy, noun: "dates" } : undefined}
            empty={show === "mine" ? "Nothing dated for your stocks in these two weeks." : "Nothing dated in these two weeks for this choice."} />
        </Card>
      )}
    </div>
  );
}

function addDays(iso: string, n: number): Date { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d; }
function fmtIso(d: Date): string { return d.toISOString().slice(0, 10); }
