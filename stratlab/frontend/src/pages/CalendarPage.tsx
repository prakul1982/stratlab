import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../lib/api";
import { eyebrowOf } from "../lib/eyebrow";
import { fmtDate, istToday, price } from "../lib/format";
import { loadEvents, type EventsView } from "../lib/marketEvents";
import { useRegion, type Region } from "../lib/research";
import type { IpoList } from "../lib/ipo";
import { TYPES, TYPE_CHIP, TYPE_NAME, ipoRows, mergeRows, type CalRow, type CalType } from "../lib/calendarRows";
import type { ResultRow, ResultDay } from "./ResultsPage";
import type { ActionRow } from "./CorpActionsPage";
import { RegionSwitch } from "../components/Research";
import { SIZE_NAME, type Facets } from "../components/CalendarFilters";
import { Card, ChipSet, DataTable, ErrorState, Field, PageHeader, Seg, Select, Skeleton, type Column } from "../components/kit";

/* /calendar (IA-1 item 3): the one Calendar's "All dates" tab. Every dated thing in the days the results calendar covers (this
 * week and next), in one table: results days and corporate actions (for your stocks or every company, by size and sector),
 * IPO openings, closings, allotments and listings, the market's own events (RBI, the Fed, data, expiries, holidays) and your own
 * tax and money dates. Each type's own tab (Results, Corporate actions, IPOs, Market events, My money dates) keeps its full
 * page; this one reads the same answers, so the two never disagree. Facts only. */

type ResultsView = { weeks: { from: string; to: string; rows: ResultRow[]; days?: ResultDay[] }[]; facets: Facets; today: string };
type CorpView = { ahead: ActionRow[] };
type MoneyView = { events: { id: string; date: string; title: string; cat: string; detail: string }[] };

export function CalendarPage() {
  const [region, setRegion] = useRegion();
  const [params, setParams] = useSearchParams();
  const scope = params.get("scope") === "all" ? "all" : "mine";
  const typeParam = (params.get("type") ?? "").split(",").filter((t): t is CalType => (TYPES as string[]).includes(t));
  const [types, setTypes] = useState<CalType[]>(typeParam.length ? typeParam : TYPES);
  const [size, setSize] = useState<string[]>([]);
  const [sector, setSector] = useState("");
  const [openDay, setOpenDay] = useState("");
  const [res, setRes] = useState<ResultsView | null | "error">(null);
  const [corp, setCorp] = useState<CorpView | null | "error">(null);
  const [ipos, setIpos] = useState<IpoList | null | "error">(null);
  const [ev, setEv] = useState<EventsView | null | "error">(null);
  const [money, setMoney] = useState<MoneyView | null | "error">(null);
  const [tries, setTries] = useState(0);
  const setParam = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p, { replace: true }); };
  // a sector of one market is not the other's
  const [sectorFor, setSectorFor] = useState(region);
  if (sectorFor !== region) { setSectorFor(region); setSector(""); setOpenDay(""); }
  const qs = (extra: Record<string, string> = {}) => {
    const q = new URLSearchParams({ region, scope, size: scope === "all" ? size.join(",") : "", sector: scope === "all" ? sector : "", ...extra });
    for (const [k, v] of [...q]) if (!v) q.delete(k);
    return q.toString();
  };
  useEffect(() => {
    let live = true;
    setRes(null); setCorp(null);
    api<ResultsView>(`/research/results?${qs({ day: scope === "all" ? openDay : "" })}`).then((x) => live && setRes(x)).catch(() => live && setRes("error"));
    api<CorpView>(`/research/corp-actions?${qs()}`).then((x) => live && setCorp(x)).catch(() => live && setCorp("error"));
    return () => { live = false; };
  }, [region, scope, size, sector, openDay, tries]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let live = true;
    setIpos(null);
    api<IpoList>(`/invest/ipos?market=${region}`).then((x) => live && setIpos(x)).catch(() => live && setIpos("error"));
    return () => { live = false; };
  }, [region, tries]);
  useEffect(() => { let live = true; loadEvents().then((x) => live && setEv(x ?? "error")); return () => { live = false; }; }, [tries]);
  // the window: today to the last day the results calendar covers (this week and next)
  const today = res && res !== "error" ? res.today : istToday();
  const until = res && res !== "error" && res.weeks.length ? res.weeks[res.weeks.length - 1].to : fmtIso(addDays(today, 13));
  useEffect(() => {
    let live = true;
    setMoney(null);
    api<MoneyView>(`/money/calendar?start=${today}&end=${until}&cats=tax,money,custom`).then((x) => live && setMoney(x)).catch(() => live && setMoney("error"));
    return () => { live = false; };
  }, [today, until, tries]);

  const rows = useMemo(() => {
    const ok = <T,>(v: T | null | "error"): v is T => !!v && v !== "error";
    const parts: CalRow[][] = [];
    if (ok(res)) parts.push(res.weeks.flatMap((w) => w.rows).filter((r) => r.date >= today).map((r) => ({
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
  }, [res, corp, ipos, ev, money, types, today, until, region]);

  const failed = ([[res, "results"], [corp, "corporate actions"], [ipos, "IPOs"], [ev, "market events"], [money, "your money dates"]] as const).filter(([v]) => v === "error").map(([, w]) => w);
  const loading = res === null || corp === null || ipos === null || ev === null || money === null;
  // a day of "every company" that has more results than came in this answer opens in full (DE-026), one day at a time
  const cut = res && res !== "error" && scope === "all" ? res.weeks.flatMap((w) => w.days ?? []).filter((d) => d.count > d.shown && d.date !== openDay) : [];
  const facets = res && res !== "error" ? res.facets : null;
  const toggle = (t: CalType) => setTypes((cur) => (cur.includes(t) ? cur.filter((x) => x !== t) : TYPES.filter((x) => x === t || cur.includes(x))));
  const cols: Column<CalRow>[] = [
    { key: "date", header: "Day", rowHeader: true, cell: (r) => <span className="nowrap">{fmtDate(r.date, { weekday: true, year: false })}{r.date === today ? " · today" : ""}</span> },
    { key: "type", header: "Type", cell: (r) => TYPE_NAME[r.type] },
    { key: "name", header: "What", wrap: true, cell: (r) => <><Link className="link" to={r.to}>{r.name}</Link>{r.mine && <span className="k-note k-muted"> · yours</span>}</> },
    { key: "detail", header: "Detail", wrap: true, cell: (r) => r.detail || <span className="k-muted">–</span> },
  ];
  return (
    <div className="k-page">
      <PageHeader eyebrow={eyebrowOf("/calendar")} title="All dates"
        lede="Results days, corporate actions, IPO dates, the market's own events and your money dates, day by day, this week and next. Each type's own tab has its full table and its filters." />
      <Card label="What to show" className="cal-filters">
        <div className="k-toolbar">
          <RegionSwitch region={region} setRegion={(r: Region) => setRegion(r)} />
          <Seg label="Companies" value={scope} onChange={(v) => { setOpenDay(""); setParam("scope", v === "all" ? "all" : ""); }}
            options={[{ value: "mine", label: "My stocks" }, { value: "all", label: "Every company" }]} />
        </div>
        <div className="k-field wide">
          <span className="k-lbl">Type</span>
          <ChipSet label="Type" options={TYPES.map((t) => ({ value: t, label: TYPE_CHIP[t] }))} on={types} onToggle={(v) => toggle(v as CalType)} />
        </div>
        {scope === "all" && facets && (
          <div className="k-toolbar">
            <div className="k-field">
              <span className="k-lbl">Company size</span>
              <ChipSet label="Company size" options={facets.sizes.map((s) => ({ value: s.id, label: SIZE_NAME[s.id] ?? s.label }))} on={size}
                onToggle={(v) => { setOpenDay(""); setSize((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v])); }} />
            </div>
            <Field label={region === "IN" ? "Sector" : "Industry division"}>
              {(id) => <Select id={id} value={sector} onChange={(v) => { setOpenDay(""); setSector(v); }}
                options={[{ value: "", label: "All" }, ...facets.sectors.map((s) => ({ value: s.name, label: s.name })), ...(sector && !facets.sectors.some((s) => s.name === sector) ? [{ value: sector, label: sector }] : [])]} />}
            </Field>
          </div>
        )}
        <p className="k-small k-muted" data-testid="cal-count">
          {loading ? "Reading the calendars…" : `${rows.length.toLocaleString("en-IN")} date${rows.length === 1 ? "" : "s"} from ${fmtDate(today, { weekday: true, year: false })} to ${fmtDate(until, { weekday: true, year: false })}`}
          {scope === "mine" ? ". Results and corporate actions for your holdings, watchlist, notebooks and paper sessions." : "."}
        </p>
      </Card>
      {failed.length > 0 && <ErrorState title={`Some dates couldn't be read: ${failed.join(", ")}`} action={{ label: "Try again", onClick: () => setTries((x) => x + 1) }}>The rest are below.</ErrorState>}
      {loading && !rows.length ? <Card><Skeleton label="Reading the calendars" /></Card> : (
        <Card label="Dates" testId="cal-all">
          <DataTable stack label="Every date, this week and next" columns={cols} rows={rows} rowKey={(r) => r.id}
            empty={types.length ? "Nothing dated in these two weeks for this choice." : "Pick at least one type above."} />
          {cut.length > 0 && (
            <div className="k-row cal-more">
              <span className="k-small k-muted">Days with more results than the table holds at first:</span>
              {cut.map((d) => <button key={d.date} type="button" className="btn quiet sm" onClick={() => setOpenDay(d.date)}>Show all {d.count.toLocaleString("en-IN")} on {fmtDate(d.date, { weekday: true, year: false })}</button>)}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function addDays(iso: string, n: number): Date { const d = new Date(`${iso}T00:00:00Z`); d.setUTCDate(d.getUTCDate() + n); return d; }
function fmtIso(d: Date): string { return d.toISOString().slice(0, 10); }
