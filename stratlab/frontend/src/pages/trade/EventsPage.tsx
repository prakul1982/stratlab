import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf } from "../../lib/format";
import { evDay, loadEvents, type EvKind, type EvPrefs, type EventsView, type IndexChange, type MarketEvent } from "../../lib/marketEvents";
import { Info } from "../../components/ui";
import { Calendar, type CalEvent, Card, CardHead, CheckField, ChipBar, ChipSet, type Column, DataTable, DateField, Disclosure, EmptyState, ErrorState, Field, FormGrid, PageHeader, Select, Skeleton } from "../../components/kit";
import "./trade.css";
import "./events.css";

/* /trade/events: the market events calendar. RBI policy (the MPC), India's CPI, IIP and GDP releases, the US Fed and the
 * US CPI and jobs reports, index changes, F&O expiries and exchange holidays on a month calendar (a dot for each kind of
 * event, a click on a day lists what is on it) or as one dated list, each from the body that publishes it, with the
 * published figure once it is out. Results days, dividends and F&O contract changes have their own calendars, linked
 * from here. Free to view; reminders are on Basic; the events can also go into the Money calendar. Dates and published
 * figures only. Built from the kit (components/kit); the month grid is the kit's Calendar, shared with the Money calendar. */

type Filter = "all" | EvKind;
const DAY_OPTS = [{ value: 0, label: "On the morning of the day" }, { value: 1, label: "1 day before" }, { value: 2, label: "2 days before" }, { value: 7, label: "A week before" }];
const TAG: Record<EvKind, string> = { rbi: "RBI", india: "India data", us: "US", budget: "Government", index: "Index change", expiry: "Expiry", holiday: "Holiday" };

/** What goes under an event's title in the day panel and the list: its time, the published figure and the official release. */
function Detail({ e }: { e: MarketEvent }) {
  return (
    <div className="ev-row" data-kind={e.kind} data-event={e.id}>
      {e.time && <span className="k-note num">{e.time} IST</span>}
      {e.status === "scheduled" && e.title.endsWith("(due)") && <span className="k-note"> due</span>}
      {e.figure && <p className="k-small ev-figure" data-testid="ev-figure"><b>{e.figure}</b>{e.previous && <span className="k-muted"> · {e.previous}</span>}</p>}
      {e.detail && <p className="k-note">{e.detail}</p>}
      {e.url && <a className="link k-note" href={e.url} target="_blank" rel="noopener noreferrer">Official release ↗</a>}
    </div>
  );
}

function RemindCard({ v, onSave }: { v: EventsView; onSave: (p: Partial<EvPrefs>) => void }) {
  const p = v.prefs;
  const kinds = Object.keys(v.kinds) as EvKind[];
  return (
    <Card label="Reminders and your calendar">
      <CardHead level={2} title="Reminders and your calendar" />
      {p.allowed ? (
        <CheckField checked={p.remind} onChange={(on) => onSave({ remind: on })}
          label={<>Remind me of the events I pick
            <Info>{"Sent once each morning (about 7:30 am India time) by phone notification, Telegram or email, whichever you set up in Settings."}</Info></>} />
      ) : (
        <p className="k-small">Reminders of these events are on the {p.plan} plan. <Link className="link" to="/plans">See the {p.plan} plan</Link></p>
      )}
      {p.allowed && p.remind && !p.channels.length && <p className="k-note">Nowhere to send them yet: add a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link>.</p>}
      <ChipSet label="Kinds of event" options={kinds.map((k) => ({ value: k, label: v.kinds[k] }))} on={p.kinds}
        onToggle={(k) => onSave({ kinds: p.kinds.includes(k as EvKind) ? p.kinds.filter((x) => x !== k) : [...p.kinds, k as EvKind] })} />
      {p.allowed && (
        <Field label="When" wide>{(id) => <Select id={id} label="When to remind" value={p.days} onChange={(d) => onSave({ days: Number(d) })} options={DAY_OPTS} />}</Field>
      )}
      <CheckField checked={p.money_calendar} onChange={(on) => onSave({ money_calendar: on })}
        label={<span>Also show the kinds I picked in my <Link className="link" to="/money/calendar">Money calendar</Link> and its calendar feed</span>} />
    </Card>
  );
}

function IndexChanges({ rows }: { rows: IndexChange[] }) {
  const shown = rows.filter((c) => c.sections.length);
  if (!shown.length) return null;
  const names = (list: [string, string][]) => list.length
    ? list.map(([sym, name], j) => <span key={sym}>{j ? ", " : ""}<Link className="link" to={`/research/IN/${encodeURIComponent(sym)}`} title={name}>{sym}</Link></span>)
    : <span className="k-muted">None</span>;
  const cols: Column<IndexChange["sections"][number]>[] = [
    { key: "index", header: "Index", rowHeader: true, cell: (s) => s.index },
    { key: "in", header: "Going in", cell: (s) => names(s.in) },
    { key: "out", header: "Coming out", cell: (s) => names(s.out) },
  ];
  return (
    <section className="k-stack" aria-labelledby="ev-idx-h">
      <h2 id="ev-idx-h" className="k-sub">Index changes</h2>
      {shown.slice(0, 4).map((c) => (
        <Card key={c.id} testId="ev-index-change">
          <CardHead level={3} title={c.effective ? `From ${evDay(c.effective, true)}` : c.title}
            actions={<span className="k-note">Announced {asOf(c.announced)} · <a className="link" href={c.url} target="_blank" rel="noopener noreferrer">Press release ↗</a></span>} />
          <DataTable label={`Index changes ${c.effective ? `from ${evDay(c.effective, true)}` : c.title}`} columns={cols} rows={c.sections} rowKey={(s) => s.index} />
        </Card>
      ))}
      <p className="k-note">The provider's list of stocks going in and out of its main indices. No estimate of any flows.</p>
    </section>
  );
}

function AdminPanel({ v, reload }: { v: EventsView; reload: () => void }) {
  const { fail, notify } = useApp();
  const [f, setF] = useState({ date: "", kind: "budget", title: "", detail: "", time: "", url: "" });
  const custom = v.events.filter((e) => e.custom);
  const add = async () => {
    try {
      await api("/admin/events/custom", { method: "POST", body: { ...f, time: f.time || null, url: f.url || null } });
      setF({ ...f, title: "", detail: "", url: "" });
      reload();
    } catch (e) { fail(e); }
  };
  return (
    <Disclosure summary="Admin: sources and added events">
      <div className="k-stack">
        <p className="k-note">{v.sources.map((s) => `${s.label}: ${s.checked ? `read ${asOf(s.checked)}` : "not read yet"}${s.failed ? " (last read failed)" : ""}`).join(" · ")}</p>
        <div>
          <button type="button" className="btn quiet sm" onClick={async () => {
            try { await api("/admin/events/refresh", { method: "POST" }); notify("Reading the sources in the background. Reload in a minute or two."); } catch (e) { fail(e); }
          }}>Read the sources now</button>
        </div>
        <FormGrid>
          <DateField label="Date" value={f.date} onChange={(date) => setF({ ...f, date })} />
          <Field label="Kind">{(id) => <Select id={id} label="Kind" value={f.kind} onChange={(k) => setF({ ...f, kind: k })} options={Object.entries(v.custom_kinds).map(([k, l]) => ({ value: k, label: l }))} />}</Field>
          <Field label="Title" placeholder="Union Budget 2027-28" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <Field label="Time" optional placeholder="HH:MM" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} />
          <Field label="Link" optional placeholder="Official https link" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} />
          <Field label="Detail" optional value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} />
        </FormGrid>
        <div><button type="button" className="btn sm" disabled={!f.date || f.title.length < 3} onClick={add}>Add event</button></div>
        {custom.length > 0 && <ul className="k-list">
          {custom.map((e) => <li key={e.id}>{e.date} · {e.title} <button type="button" className="link" onClick={async () => {
            try { await api(`/admin/events/custom/${e.custom}`, { method: "DELETE" }); reload(); } catch (x) { fail(x); }
          }}>Remove</button></li>)}
        </ul>}
      </div>
    </Disclosure>
  );
}

export function EventsPage() {
  const { fail, me } = useApp();
  const [v, setV] = useState<EventsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const reload = () => loadEvents(true).then((x) => (x ? setV(x) : setError("The market events couldn't be read. Try again in a minute.")));
  useEffect(() => { reload(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const kinds = useMemo(() => (v ? (Object.keys(v.kinds) as EvKind[]).filter((k) => v.events.some((e) => e.kind === k)) : []), [v]);
  const byId = useMemo(() => new Map((v?.events ?? []).map((e) => [e.id, e])), [v]);
  const calEvents = useMemo<CalEvent[]>(() => (v?.events ?? []).filter((e) => filter === "all" || e.kind === filter)
    .map((e) => ({ id: e.id, date: e.date, title: e.title, kind: e.kind })), [v, filter]);
  const week = useMemo(() => {
    if (!v) return [];
    const [y, m, d] = v.today.split("-").map(Number);
    const end = new Date(y, m - 1, d + 7);
    const endIso = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
    return v.events.filter((e) => e.date >= v.today && e.date < endIso && !(e.kind === "expiry" && e.title.includes("weekly")));
  }, [v]);

  const save = async (p: Partial<EvPrefs>) => {
    if (!v) return;
    const next = { ...v.prefs, ...p };
    try {
      const got = await api<EvPrefs>("/trade/events/prefs", { method: "PUT", body: { remind: next.remind, kinds: next.kinds, days: next.days, money_calendar: next.money_calendar } });
      setV({ ...v, prefs: got });
    } catch (e) { fail(e); }
  };

  return (
    <div className="k-page ev-page">
      <PageHeader eyebrow="Trade · F&O desk" title="Market events"
        lede="RBI policy, India's data releases, the US Fed and US data, index changes, F&O expiries and exchange holidays on one calendar, with the published figure once it is out. Dates and figures only, never a forecast. Facts, not advice."
        info={v ? <span data-testid="ev-asof">{v.sources.map((s) => `${s.label} ${s.as_of ? `as of ${asOf(s.as_of)}` : "not read yet"}${s.failed ? " (couldn't be refreshed since)" : ""}`).join(" · ")}</span> : undefined}
        infoLabel="Where this comes from" />
      {error ? <ErrorState title="The market events couldn't be read" action={{ label: "Try again", onClick: () => { setError(null); reload(); } }}>{error}</ErrorState>
        : !v ? <Card><Skeleton label="Reading the market events" /></Card>
        : (
          <>
            <div className="k-two">
              <Card label="The next seven days">
                <CardHead level={2} title="The next seven days" />
                {week.length ? (
                  <ul className="k-list plain ev-week" data-testid="ev-week">
                    {week.slice(0, 10).map((e) => (
                      <li key={e.id} data-kind={e.kind}>
                        <span className="k-note">{evDay(e.date)}{e.time ? ` · ${e.time} IST` : ""}</span>{" "}
                        <span className="k-small"><b>{e.title}</b>{e.figure ? ` · ${e.figure}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="k-small k-muted">No scheduled events in the next seven days.</p>}
                <p className="k-note">
                  Results this week: <Link className="link" to="/research/results">{v.week.results ?? "the results calendar"}</Link> ·
                  Dividends and other corporate actions: <Link className="link" to="/research/corporate-actions">{v.week.actions ?? "the calendar"}</Link> ·
                  Lot and expiry-day changes: <Link className="link" to="/trade/fo-changes">F&amp;O changes</Link>
                </p>
              </Card>
              <RemindCard v={v} onSave={save} />
            </div>

            <Card label="Every event">
              <CardHead title="Every event" />
              <ChipBar label="Kind of event" value={filter} onChange={(f) => setFilter(f as Filter)}
                options={[{ value: "all", label: "All" }, ...kinds.map((k) => ({ value: k, label: v.kinds[k] }))]} />
              {!v.events.length ? (
                <EmptyState title="No events read yet">The official calendars are read twice a day; the events show here once they are.</EmptyState>
              ) : (
                <Calendar label="Market events" events={calEvents} kinds={kinds.map((k) => ({ id: k, label: TAG[k] }))} today={v.today}
                  listEmpty={`Nothing of this kind on the calendar.`}
                  render={(e) => { const m = byId.get(e.id); return m ? <Detail e={m} /> : null; }} />
              )}
            </Card>
            <IndexChanges rows={v.index_changes} />
            {me?.is_admin && <AdminPanel v={v} reload={reload} />}
            <p className="k-note">{v.note}</p>
          </>
        )}
    </div>
  );
}
