import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf, safeHref } from "../../lib/format";
import { evDay, evWhen, failedLine, happened, istHm, loadEvents, type EvKind, type EvPrefs, type EventsView, type IndexChange, type MarketEvent } from "../../lib/marketEvents";
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
      {e.url && <a className="link k-note" href={safeHref(e.url)} target="_blank" rel="noopener noreferrer">Official release ↗</a>}
    </div>
  );
}

function RemindCard({ v, onSave }: { v: EventsView; onSave: (p: Partial<EvPrefs>) => void }) {
  const p = v.prefs;
  const kinds = Object.keys(v.kinds) as EvKind[];
  // a kind with nothing on the calendar says so (DC-016: "Budget and government" with no event, no Union Budget yet)
  const none = (k: EvKind) => !v.events.some((e) => e.kind === k);
  return (
    <Card label="Reminders and your calendar">
      <CardHead level={2} title="Reminders and your calendar" />
      <div className="ev-remind">
        <div className="k-stack">
          {p.allowed ? (
            <CheckField checked={p.remind} onChange={(on) => onSave({ remind: on })}
              label={<>Remind me of the events I pick
                <Info>{"Sent once each morning (about 07:30 IST) by phone notification, Telegram or email, whichever you set up in Settings."}</Info></>} />
          ) : (
            <p className="k-small">Reminders of these events are on the {p.plan} plan. <Link className="link" to="/plans">See the {p.plan} plan</Link></p>
          )}
          {p.allowed && p.remind && !p.channels.length && <p className="k-note">Nowhere to send them yet: add a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link>.</p>}
          {/* a kind with no event on the calendar is not offered as a chip that can never fire (RC2A-040); it is named below, and a pick already
              saved for it stays saved */}
          <ChipSet label="Kinds of event" options={kinds.filter((k) => !none(k)).map((k) => ({ value: k, label: v.kinds[k] }))} on={p.kinds}
            onToggle={(k) => onSave({ kinds: p.kinds.includes(k as EvKind) ? p.kinds.filter((x) => x !== k) : [...p.kinds, k as EvKind] })} />
          {kinds.some(none) && <p className="k-note" data-testid="ev-empty-kinds">Nothing is on the calendar yet for {kinds.filter(none).map((k) => v.kinds[k]).join(", ")}; it can be picked once there is.</p>}
        </div>
        <div className="k-stack">
          {p.allowed && (
            <Field label="When" wide>{(id) => <Select id={id} label="When to remind" value={p.days} onChange={(d) => onSave({ days: Number(d) })} options={DAY_OPTS} />}</Field>
          )}
          <CheckField checked={p.money_calendar} onChange={(on) => onSave({ money_calendar: on })}
            label={<span>Also show the kinds I picked in my <Link className="link" to="/money/calendar">Money calendar</Link> and its calendar feed</span>} />
        </div>
      </div>
    </Card>
  );
}

function IndexChanges({ rows, failed }: { rows: IndexChange[]; failed: string | null }) {
  const shown = rows.filter((c) => c.sections.length);
  // a notice whose stocks couldn't be read is still listed, with its link, never dropped (DC-013: 9 of 12 hidden)
  const unread = rows.filter((c) => !c.sections.length);
  if (!shown.length && !unread.length && !failed) return null;
  const names = (list: [string, string][]) => list.length
    // each comma stays with the name before it, so a wrapped line never starts with one (R54-011)
    ? list.map(([sym, name], j) => <span key={sym}><span className="nowrap"><Link className="link tap" to={`/research/IN/${encodeURIComponent(sym)}`} title={name}>{sym}</Link>{j < list.length - 1 ? "," : ""}</span>{j < list.length - 1 ? " " : ""}</span>)
    : <span className="k-muted"><span aria-hidden="true">–</span><span className="sr-only">none</span></span>;   // a dash, not the word (R53-009)
  const cols: Column<IndexChange["sections"][number]>[] = [
    { key: "index", header: "Index", rowHeader: true, cell: (s) => s.index },
    // long lists wrap, and on a phone each index is a card, so "Coming out" is never off the side (R50-006)
    { key: "in", header: "Going in", wrap: true, cell: (s) => names(s.in) },
    { key: "out", header: "Coming out", wrap: true, cell: (s) => names(s.out) },
  ];
  const card = (c: IndexChange, n: number) => (
    <Card key={c.id} testId="ev-index-change">
      <CardHead level={3} title={c.effective ? `From ${evDay(c.effective, true)}` : c.title}
        actions={<span className="k-note">Announced {asOf(c.announced)} · <a className="link" href={safeHref(c.url)} target="_blank" rel="noopener noreferrer">Press release ↗</a></span>} />
      {/* each table names its own announcement: two changes on one date gave two landmarks with one name (R5O-030) */}
      <DataTable label={`Index changes ${c.effective ? `from ${evDay(c.effective, true)}` : c.title}, announcement ${n + 1} of ${Math.min(4, shown.length)}`} columns={cols} rows={c.sections} rowKey={(s) => s.index} stack />
    </Card>
  );
  return (
    <section className="k-stack" aria-labelledby="ev-idx-h">
      <h2 id="ev-idx-h" className="k-sub">Index changes</h2>
      {failed && <p className="k-callout k-small" role="status" data-testid="ev-failed">{failed}</p>}
      {unread.length > 0 && (
        <Card testId="ev-index-unread" label="Index notices not read into stocks">
          <CardHead level={3} title={`Notices not read into stocks here (${unread.length})`} />
          <ul className="k-list plain">
            {unread.slice(0, 8).map((c) => (
              <li key={c.id} className="k-small">{c.effective ? `From ${evDay(c.effective, true)}: ` : ""}{c.title} · announced {asOf(c.announced)} ·{" "}
                <a className="link" href={safeHref(c.url)} target="_blank" rel="noopener noreferrer">Press release ↗</a></li>
            ))}
          </ul>
          <p className="k-note">The press release has the stocks going in and out; they couldn't be read from it here.</p>
        </Card>
      )}
      {shown.slice(0, 1).map((c) => card(c, 0))}
      {/* the newest announcement open; the earlier ones folded, so the page isn't three full tables long on a phone
          (R70-013, R71-009: 27,000 px) */}
      {shown.length > 1 && (
        <Disclosure summary={`Earlier index changes (${Math.min(4, shown.length) - 1})`} testId="ev-index-earlier">
          <div className="k-stack">{shown.slice(1, 4).map((c, n) => card(c, n + 1))}</div>
        </Disclosure>
      )}
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
    // weekly expiries come every week, so only the nearest one is listed: tomorrow's NIFTY weekly expiry is the date an F&O
    // reader most needs, and leaving every weekly out dropped it (R49-007)
    // today's events whose time has passed are gone from the week, unless a published figure is the reason to look (R70-001)
    const nowHm = istHm();
    const ahead = v.events.filter((e) => e.date >= v.today && e.date < endIso && (!happened(e, v.today, nowHm) || !!e.figure));
    // the nearest one of each index's: NIFTY's and SENSEX's (R64-008: Thursday's SENSEX weekly was left out)
    const isWeekly = (e: (typeof ahead)[number]) => e.kind === "expiry" && e.title.includes("weekly");
    const firsts = new Set<(typeof ahead)[number]>();
    const seen = new Set<string>();
    for (const e of ahead) if (isWeekly(e) && !seen.has(e.title)) { seen.add(e.title); firsts.add(e); }
    return ahead.filter((e) => !isWeekly(e) || firsts.has(e));
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
      <PageHeader eyebrow="Trade · Calendar" title="Market events"
        lede="RBI policy, India's data releases, the US Fed and US data, index changes, F&O expiries and exchange holidays on one calendar. The repo rate, the Fed's range and India's CPI, IIP and GDP once published; the US reports as dates with a link. Never a forecast. Facts, not advice."
        info={v ? <span data-testid="ev-asof">{v.sources.map((s) => `${s.label} ${s.as_of ? `as of ${asOf(s.as_of)}` : "not read yet"}${s.failed ? " (couldn't be refreshed since)" : ""}`).join(" · ")}</span> : undefined}
        infoLabel="Where this comes from" />
      {error ? <ErrorState title="The market events couldn't be read" action={{ label: "Try again", onClick: () => { setError(null); reload(); } }}>{error}</ErrorState>
        : !v ? <Card><Skeleton label="Reading the market events" /></Card>
        : (
          <>
            {/* the index provider's failure is said over the index changes it affects, not above the whole calendar (LIVE1A-021) */}
            {failedLine(v.sources.filter((x) => x.id !== "index"), (d) => asOf(d) ?? d) && <p className="k-callout k-small" role="status" data-testid="ev-failed">{failedLine(v.sources.filter((x) => x.id !== "index"), (d) => asOf(d) ?? d)}</p>}
            {/* CK-2 (R1, R13): the week card is the full width, its events side by side and its three count lines in a column beside them, and the
                reminders card under it is full width with its controls in two columns: neither is stretched beside the other into a blank band */}
            <Card label="The next seven days">
              <CardHead level={2} title="The next seven days" />
              <div className="ev-weekgrid">
                {week.length ? (
                  <ul className="k-list plain ev-week" data-testid="ev-week">
                    {week.slice(0, 10).map((e) => (
                      <li key={e.id} data-kind={e.kind}>
                        <span className="k-note">{evWhen(e)}{e.time ? ` · ${e.time} IST` : ""}</span>{" "}
                        <span className="k-small"><b>{e.title}</b>{e.figure ? ` · ${e.figure}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="k-small k-muted">No scheduled events in the next seven days.</p>}
                <ul className="k-list plain ev-week-more">
                  <li className="k-note">Results this week: <Link className="link tap" to="/research/results">{v.week.results ?? "the results calendar"}</Link></li>
                  <li className="k-note">Dividends and other corporate actions: <Link className="link tap" to="/research/corporate-actions">{v.week.actions ?? "the calendar"}</Link></li>
                  <li className="k-note">Lot and expiry-day changes: <Link className="link" to="/trade/fo-changes">F&amp;O changes</Link></li>
                </ul>
              </div>
            </Card>
            <RemindCard v={v} onSave={save} />

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
            <IndexChanges rows={v.index_changes} failed={failedLine(v.sources.filter((x) => x.id === "index"), (d) => asOf(d) ?? d)} />
            {me?.is_admin && <AdminPanel v={v} reload={reload} />}
            <p className="k-note">{v.note}</p>
          </>
        )}
    </div>
  );
}
