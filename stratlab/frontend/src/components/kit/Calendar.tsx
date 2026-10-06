import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Seg } from "./Seg";
import "./calendar.css";

export type CalKind = { id: string; label: string };
export type CalEvent = { id: string; date: string; title: string; kind: string; detail?: ReactNode; to?: string };

const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const longDay = (s: string) => parse(s).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const shortDay = (s: string) => parse(s).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
const monthName = (y: number, m: number) => new Date(y, m, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
const kindIndex = (kinds: CalKind[], id: string) => Math.max(0, kinds.findIndex((k) => k.id === id));

function EventItem({ e, kinds, past, render }: { e: CalEvent; kinds: CalKind[]; past: boolean; render?: (e: CalEvent) => ReactNode }) {
  const k = kinds.find((x) => x.id === e.kind);
  return (
    <li className={`k-cal-ev${past ? " past" : ""}`}>
      <span className={`k-cal-kind c${kindIndex(kinds, e.kind) % 6}`}><i className="k-cal-dot" aria-hidden="true" />{k?.label ?? e.kind}</span>
      <div className="k-cal-ev-body">
        <div className="k-cal-ev-title">{e.to ? <Link className="link" to={e.to}>{e.title}</Link> : e.title}</div>
        {render ? render(e) : e.detail && <div className="k-note">{e.detail}</div>}
      </div>
    </li>
  );
}

function DayGroups({ events, kinds, today, render, label }: { events: CalEvent[]; kinds: CalKind[]; today: string; render?: (e: CalEvent) => ReactNode; label: string }) {
  const days = useMemo(() => {
    const by = new Map<string, CalEvent[]>();
    for (const e of [...events].sort((a, b) => a.date.localeCompare(b.date))) by.set(e.date, [...(by.get(e.date) ?? []), e]);
    return [...by.entries()];
  }, [events]);
  return (
    <ol className="k-cal-days" aria-label={label}>
      {days.map(([d, evs]) => (
        <li key={d} className="k-cal-daygroup">
          <div className={`k-cal-date${d === today ? " today" : ""}`}><b>{shortDay(d)}</b>{d === today && <span className="k-note"> · today</span>}</div>
          <ul className="k-cal-evs">{evs.map((e) => <EventItem key={e.id} e={e} kinds={kinds} past={d < today} render={render} />)}</ul>
        </li>
      ))}
    </ol>
  );
}

/** A month calendar: a grid of days with one dot per kind of event, a click (or Enter) on a day lists its events under
 * the grid, and a Month / List switch shows the same events as a dated list. Keyboard: arrows move between days,
 * Home / End go to the week's ends, Page Up / Page Down change the month. Colours are never the only signal: the
 * legend names each kind and each listed event carries its kind's name. Reused by the market events and the money
 * calendar. `onMonth` tells the page which month is showing, to load its events. */
export function Calendar({ label, events, kinds, today, initialMonth, onMonth, view: viewProp, onView, render, listEmpty = "Nothing on the calendar for these dates." }: {
  label: string; events: CalEvent[]; kinds: CalKind[]; today: string;
  /** "YYYY-MM": the month to open on (this month when left out). */
  initialMonth?: string;
  onMonth?: (year: number, month: number) => void;
  view?: "month" | "list"; onView?: (v: "month" | "list") => void;
  /** The line(s) under an event's title, when `detail` is not enough. */
  render?: (e: CalEvent) => ReactNode;
  listEmpty?: ReactNode;
}) {
  const start = initialMonth ? parse(`${initialMonth}-01`) : parse(today);
  const [cursor, setCursor] = useState({ y: start.getFullYear(), m: start.getMonth() });
  const [own, setOwn] = useState<"month" | "list">("month");
  const view = viewProp ?? own;
  const setView = (v: "month" | "list") => { setOwn(v); onView?.(v); };
  const [picked, setPicked] = useState<string | null>(null);
  const [focus, setFocus] = useState<string>(today);
  const grid = useRef<HTMLDivElement>(null);
  const want = useRef(false);

  const by = useMemo(() => {
    const m = new Map<string, CalEvent[]>();
    for (const e of events) m.set(e.date, [...(m.get(e.date) ?? []), e]);
    return m;
  }, [events]);
  const first = new Date(cursor.y, cursor.m, 1);
  const lead = (first.getDay() + 6) % 7;                    // Monday first
  const n = new Date(cursor.y, cursor.m + 1, 0).getDate();
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: n }, (_, i) => iso(new Date(cursor.y, cursor.m, i + 1)))];
  while (cells.length % 7) cells.push(null);
  const rows = Array.from({ length: cells.length / 7 }, (_, r) => cells.slice(r * 7, r * 7 + 7));
  const inMonth = (d: string) => d.slice(0, 7) === `${cursor.y}-${String(cursor.m + 1).padStart(2, "0")}`;
  const stop = inMonth(focus) ? focus : cells.find((c) => c === today) ?? cells.find(Boolean)!;

  const go = (y: number, m: number, d?: string) => {
    const t = new Date(y, m, 1);
    setCursor({ y: t.getFullYear(), m: t.getMonth() });
    setPicked(null);
    if (d) setFocus(d);
    onMonth?.(t.getFullYear(), t.getMonth());
  };
  const step = (by_: number) => go(cursor.y, cursor.m + by_, iso(new Date(cursor.y, cursor.m + by_, 1)));
  const toToday = () => { const t = parse(today); go(t.getFullYear(), t.getMonth(), today); };

  useEffect(() => {
    if (!want.current) return;
    want.current = false;
    grid.current?.querySelector<HTMLElement>(`[data-d="${stop}"]`)?.focus();
  });

  const key = (e: KeyboardEvent, d: string) => {
    const at = parse(d);
    let to: Date | null = null;
    if (e.key === "ArrowRight") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() + 1);
    else if (e.key === "ArrowLeft") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() - 1);
    else if (e.key === "ArrowDown") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() + 7);
    else if (e.key === "ArrowUp") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() - 7);
    else if (e.key === "Home") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() - ((at.getDay() + 6) % 7));
    else if (e.key === "End") to = new Date(at.getFullYear(), at.getMonth(), at.getDate() + (6 - ((at.getDay() + 6) % 7)));
    else if (e.key === "PageDown") to = new Date(at.getFullYear(), at.getMonth() + 1, Math.min(at.getDate(), 28));
    else if (e.key === "PageUp") to = new Date(at.getFullYear(), at.getMonth() - 1, Math.min(at.getDate(), 28));
    if (!to) return;
    e.preventDefault();
    const next = iso(to);
    want.current = true;
    if (next.slice(0, 7) !== d.slice(0, 7)) go(to.getFullYear(), to.getMonth(), next); else setFocus(next);
  };

  const dayEvents = picked ? by.get(picked) ?? [] : [];
  return (
    <div className="k-cal" aria-label={label} role="group">
      <div className="k-cal-bar">
        {view === "month" ? (
          <div className="k-row">
            <button type="button" className="btn quiet sm" onClick={() => step(-1)} aria-label="Previous month">‹ Prev</button>
            <b className="k-cal-month" aria-live="polite">{monthName(cursor.y, cursor.m)}</b>
            <button type="button" className="btn quiet sm" onClick={() => step(1)} aria-label="Next month">Next ›</button>
            <button type="button" className="btn quiet sm" onClick={toToday}>Today</button>
          </div>
        ) : <b className="k-cal-month">All dates, in order</b>}
        <Seg label="Calendar view" options={[{ value: "month", label: "Month" }, { value: "list", label: "List" }]} value={view} onChange={(v) => setView(v as "month" | "list")} />
      </div>
      {kinds.length > 1 && (
        <ul className="k-cal-legend" aria-label="What the dots mean">
          {kinds.map((k, i) => <li key={k.id}><i className={`k-cal-dot c${i % 6}`} aria-hidden="true" />{k.label}</li>)}
        </ul>
      )}
      {view === "month" ? (
        <>
          <div className="k-cal-grid" role="grid" aria-label={monthName(cursor.y, cursor.m)} ref={grid}>
            <div className="k-cal-row head" role="row">{WEEK.map((w) => <div key={w} role="columnheader" className="k-cal-wd">{w}</div>)}</div>
            {rows.map((r, ri) => (
              <div className="k-cal-row" role="row" key={ri}>
                {r.map((d, ci) => {
                  if (!d) return <div key={ci} role="gridcell" className="k-cal-cell empty" aria-hidden="true" />;
                  const evs = by.get(d) ?? [];
                  const kindsHere = [...new Set(evs.map((e) => e.kind))];
                  return (
                    <div key={d} role="gridcell" aria-selected={d === picked} className="k-cal-cellwrap">
                      <button type="button" data-d={d} tabIndex={d === stop ? 0 : -1} className={`k-cal-cell${d === today ? " today" : ""}${d === picked ? " picked" : ""}${evs.length ? " has" : ""}`}
                        aria-label={`${longDay(d)}: ${evs.length ? `${evs.length} event${evs.length === 1 ? "" : "s"}, ${evs.map((e) => e.title).slice(0, 3).join(", ")}${evs.length > 3 ? " and more" : ""}` : "no events"}`}
                        onClick={() => { setPicked(d === picked ? null : d); setFocus(d); }} onKeyDown={(e) => key(e, d)}>
                        <span className="k-cal-n">{parse(d).getDate()}</span>
                        <span className="k-cal-dots" aria-hidden="true">{kindsHere.slice(0, 5).map((k) => <i key={k} className={`k-cal-dot c${kindIndex(kinds, k) % 6}`} />)}</span>
                        {evs.length > 1 && <span className="k-cal-count" aria-hidden="true">{evs.length}</span>}
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>
          <div className="k-cal-panel" aria-live="polite">
            {picked ? (
              dayEvents.length ? (
                <>
                  <b>{longDay(picked)}</b>
                  <ul className="k-cal-evs">{dayEvents.map((e) => <EventItem key={e.id} e={e} kinds={kinds} past={picked < today} render={render} />)}</ul>
                </>
              ) : <p className="k-small k-muted">Nothing on {longDay(picked)}.</p>
            ) : <p className="k-note">Pick a day to see what is on it.</p>}
          </div>
        </>
      ) : events.length ? <DayGroups events={events} kinds={kinds} today={today} render={render} label={`${label}, as a list`} /> : <p className="k-small k-muted">{listEmpty}</p>}
    </div>
  );
}
