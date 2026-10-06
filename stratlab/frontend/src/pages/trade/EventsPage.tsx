import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import { asOf } from "../../lib/format";
import { evDay, loadEvents, type EvKind, type EvPrefs, type EventsView, type IndexChange, type MarketEvent } from "../../lib/marketEvents";
import { Empty, Info, Loading } from "../../components/ui";
import { Earlier } from "../../components/Earlier";

/* /trade/events: the market events calendar. RBI policy (the MPC), India's CPI, IIP and GDP releases, the US Fed and the
 * US CPI and jobs reports, index changes, F&O expiries and exchange holidays in one dated list, each from the body that
 * publishes it, with the published figure once it is out. Results days, dividends and F&O contract changes have their
 * own calendars, linked from here. Free to view; reminders are on Basic; the events can also go into the Money calendar.
 * Dates and published figures only. */

type Filter = "all" | EvKind;
const DAY_OPTS: [number, string][] = [[0, "On the morning of the day"], [1, "1 day before"], [2, "2 days before"], [7, "A week before"]];

function EventRow({ e }: { e: MarketEvent }) {
  return (
    <li className="fo-row ev-row" data-kind={e.kind} data-event={e.id}>
      <div className="row wrap" style={{ gap: 8, alignItems: "center" }}>
        <span className={`fo-tag ev-tag ev-${e.kind}`}>{TAG[e.kind]}</span>
        <b className="ev-title">{e.title}</b>
        {e.time && <span className="tiny muted num">{e.time} IST</span>}
        {e.status === "scheduled" && e.title.endsWith("(due)") && <span className="tiny muted">due</span>}
      </div>
      {e.figure && <p className="small ev-figure" data-testid="ev-figure"><b>{e.figure}</b>{e.previous && <span className="muted"> · {e.previous}</span>}</p>}
      {e.detail && <p className="small muted">{e.detail}</p>}
      {e.url && <a className="link tiny" href={e.url} target="_blank" rel="noopener noreferrer">Official release ↗</a>}
    </li>
  );
}

const TAG: Record<EvKind, string> = { rbi: "RBI", india: "India data", us: "US", budget: "Government", index: "Index change", expiry: "Expiry", holiday: "Holiday" };

function Day({ day, rows }: { day: string; rows: MarketEvent[] }) {
  return (
    <div className="stack fo-day" style={{ gap: 6 }}>
      <h3 className="eyebrow">{evDay(day, true)}</h3>
      <ul className="fo-list">{rows.map((e) => <EventRow key={e.id} e={e} />)}</ul>
    </div>
  );
}

function group(rows: MarketEvent[]): [string, MarketEvent[]][] {
  const out: [string, MarketEvent[]][] = [];
  for (const e of rows) {
    const last = out[out.length - 1];
    if (last && last[0] === e.date) last[1].push(e);
    else out.push([e.date, [e]]);
  }
  return out;
}

function RemindCard({ v, onSave }: { v: EventsView; onSave: (p: Partial<EvPrefs>) => void }) {
  const p = v.prefs;
  const kinds = (Object.keys(v.kinds) as EvKind[]);
  return (
    <section className="card stack" style={{ gap: 10 }} aria-labelledby="ev-remind-h">
      <h2 id="ev-remind-h" className="h3">Reminders and your calendar</h2>
      {p.allowed ? (
        <label className="row small fo-alert" style={{ gap: 10 }}>
          <input type="checkbox" checked={p.remind} onChange={(e) => onSave({ remind: e.target.checked })} />
          Remind me of the events I pick
          <Info>{"Sent once each morning (about 7:30 am India time) by phone notification, Telegram or email, whichever you set up on the Account page."}</Info>
        </label>
      ) : (
        <p className="small">Reminders of these events are on the {p.plan} plan. <Link className="link" to="/plans">See the {p.plan} plan</Link></p>
      )}
      {p.allowed && p.remind && !p.channels.length && <p className="tiny muted">Nowhere to send them yet: add a phone, Telegram or a confirmed email in <Link className="link" to="/settings#notifications">Settings</Link>.</p>}
      <div className="row wrap" style={{ gap: 6 }} role="group" aria-label="Kinds of event">
        {kinds.map((k) => (
          <label key={k} className="row tiny ev-kind" style={{ gap: 6 }}>
            <input type="checkbox" checked={p.kinds.includes(k)}
              onChange={(e) => onSave({ kinds: e.target.checked ? [...p.kinds, k] : p.kinds.filter((x) => x !== k) })} />{v.kinds[k]}
          </label>
        ))}
      </div>
      {p.allowed && (
        <label className="row small" style={{ gap: 8 }}>When
          <select className="input" style={{ maxWidth: 220 }} value={p.days} onChange={(e) => onSave({ days: Number(e.target.value) })} aria-label="When to remind">
            {DAY_OPTS.map(([d, l]) => <option key={d} value={d}>{l}</option>)}
          </select>
        </label>
      )}
      <label className="row small fo-alert" style={{ gap: 10 }}>
        <input type="checkbox" checked={p.money_calendar} onChange={(e) => onSave({ money_calendar: e.target.checked })} data-testid="ev-money-cal" />
        Also show the kinds I picked in my <Link className="link" to="/money/calendar">Money calendar</Link> and its calendar feed
      </label>
    </section>
  );
}

function IndexChanges({ rows }: { rows: IndexChange[] }) {
  const shown = rows.filter((c) => c.sections.length);
  if (!shown.length) return null;
  return (
    <section className="stack" style={{ gap: 12 }} aria-labelledby="ev-idx-h">
      <h2 id="ev-idx-h" className="h3">Index changes</h2>
      {shown.slice(0, 4).map((c) => (
        <div key={c.id} className="card stack" style={{ gap: 8 }} data-testid="ev-index-change">
          <div className="spread wrap" style={{ gap: 8 }}>
            <b>{c.effective ? `From ${evDay(c.effective, true)}` : c.title}</b>
            <span className="tiny muted">Announced {asOf(c.announced)} · <a className="link" href={c.url} target="_blank" rel="noopener noreferrer">Press release ↗</a></span>
          </div>
          <div className="ev-idx-wrap">
            <table className="ev-idx">
              <thead><tr><th>Index</th><th>Going in</th><th>Coming out</th></tr></thead>
              <tbody>
                {c.sections.map((s) => (
                  <tr key={s.index}>
                    <td>{s.index}</td>
                    {[s.in, s.out].map((list, i) => (
                      <td key={i}>{list.length ? list.map(([sym, name], j) => (
                        <span key={sym}>{j ? ", " : ""}<Link className="link" to={`/research/IN/${encodeURIComponent(sym)}`} title={name}>{sym}</Link></span>
                      )) : <span className="muted">None</span>}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
      <p className="tiny muted">The provider's list of stocks going in and out of its main indices. No estimate of any flows.</p>
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
    <details className="card stack" style={{ gap: 8 }}>
      <summary className="small"><b>Admin: sources and added events</b></summary>
      <p className="tiny muted">{v.sources.map((s) => `${s.label}: ${s.checked ? `read ${asOf(s.checked)}` : "not read yet"}${s.failed ? " (last read failed)" : ""}`).join(" · ")}</p>
      <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={async () => {
        try { await api("/admin/events/refresh", { method: "POST" }); notify("Reading the sources in the background. Reload in a minute or two."); } catch (e) { fail(e); }
      }}>Read the sources now</button>
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} aria-label="Date" />
        <select className="input" value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} aria-label="Kind">
          {Object.entries(v.custom_kinds).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        <input className="input" placeholder="Title (Union Budget 2027-28)" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} aria-label="Title" />
        <input className="input" placeholder="HH:MM (optional)" value={f.time} onChange={(e) => setF({ ...f, time: e.target.value })} aria-label="Time" style={{ maxWidth: 140 }} />
        <input className="input" placeholder="Official https link" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} aria-label="Link" />
        <input className="input" placeholder="Detail" value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} aria-label="Detail" />
        <button className="btn sm" disabled={!f.date || f.title.length < 3} onClick={add}>Add event</button>
      </div>
      {custom.length > 0 && <ul className="tiny" style={{ margin: 0, paddingLeft: 18 }}>
        {custom.map((e) => <li key={e.id}>{e.date} · {e.title} <button className="link" onClick={async () => {
          try { await api(`/admin/events/custom/${e.custom}`, { method: "DELETE" }); reload(); } catch (x) { fail(x); }
        }}>Remove</button></li>)}
      </ul>}
    </details>
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
  const groups = useMemo(() => {
    if (!v) return { ahead: [], past: [] };
    const rows = v.events.filter((e) => filter === "all" || e.kind === filter);
    return { ahead: group(rows.filter((e) => e.date >= v.today)), past: group(rows.filter((e) => e.date < v.today)).reverse() };
  }, [v, filter]);
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
    <div className="stack fo-page" style={{ gap: 20 }}>
      <div className="stack" style={{ gap: 6 }}>
        <h1 className="page-title">Market events</h1>
        <p className="muted" style={{ maxWidth: "70ch" }}>RBI policy, India's data releases, the US Fed and US data, index changes, F&amp;O expiries and exchange holidays in one dated list, with the published figure once it is out. Dates and figures only, never a forecast. Facts, not advice.</p>
        {v && <p className="tiny muted as-of" data-testid="ev-asof">
          {v.sources.map((s) => `${s.label} ${s.as_of ? `as of ${asOf(s.as_of)}` : "not read yet"}${s.failed ? " (couldn't be refreshed since)" : ""}`).join(" · ")}
        </p>}
      </div>
      {error ? <div className="banner">{error}</div>
        : !v ? <Loading label="Reading the market events" />
        : (
          <>
            <div className="grid2" style={{ alignItems: "start" }}>
              <section className="card stack" style={{ gap: 10 }} aria-labelledby="ev-week-h">
                <h2 id="ev-week-h" className="h3">The next seven days</h2>
                {week.length ? (
                  <ul className="fo-list" data-testid="ev-week">
                    {week.slice(0, 10).map((e) => (
                      <li key={e.id} className="fo-row" data-kind={e.kind}>
                        <span className="tiny muted">{evDay(e.date)}{e.time ? ` · ${e.time} IST` : ""}</span>
                        <span className="small"><b>{e.title}</b>{e.figure ? ` · ${e.figure}` : ""}</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="small muted">No scheduled events in the next seven days.</p>}
                <p className="tiny muted">
                  Results this week: <Link className="link" to="/research/results">{v.week.results ?? "the results calendar"}</Link> ·
                  Dividends and other corporate actions: <Link className="link" to="/research/corporate-actions">{v.week.actions ?? "the calendar"}</Link> ·
                  Lot and expiry-day changes: <Link className="link" to="/trade/fo-changes">F&amp;O changes</Link>
                </p>
              </section>
              <RemindCard v={v} onSave={save} />
            </div>

            <section className="stack" style={{ gap: 12 }} aria-labelledby="ev-all-h">
              <h2 id="ev-all-h" className="h3">Every event</h2>
              <div className="seg ev-seg" role="group" aria-label="Kind of event">
                <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All</button>
                {kinds.map((k) => <button key={k} type="button" aria-pressed={filter === k} onClick={() => setFilter(k)}>{v.kinds[k]}</button>)}
              </div>
              {!v.events.length ? (
                <Empty title="No events read yet">The official calendars are read twice a day; the events show here once they are.</Empty>
              ) : (
                <div className="stack" style={{ gap: 14 }}>
                  {groups.ahead.length ? groups.ahead.map(([day, rows]) => <Day key={day} day={day} rows={rows} />)
                    : <p className="small muted">Nothing ahead of this kind.</p>}
                  <Earlier key={filter} label="Earlier events" count={groups.past.reduce((n, [, r]) => n + r.length, 0)}>
                    {groups.past.map(([day, rows]) => <Day key={day} day={day} rows={rows} />)}
                  </Earlier>
                </div>
              )}
            </section>
            <IndexChanges rows={v.index_changes} />
            {me?.is_admin && <AdminPanel v={v} reload={reload} />}
            <p className="tiny muted">{v.note}</p>
          </>
        )}
    </div>
  );
}
