import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { money } from "../../lib/format";
import { AsOf, Info, Loading } from "../../components/ui";
import { Copy, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Earlier } from "../../components/Earlier";

type Cat = "tax" | "holdings" | "money" | "custom";
type Ev = { id: string; date: string; title: string; cat: Cat; kind: string; detail: string; amount: number | null; symbol: string | null;
  url: string | null; event_id?: string; repeat?: Repeat };
type Repeat = "none" | "monthly" | "yearly";
type Own = { id: string; date: string; title: string; note: string; amount: number | null; repeat: Repeat };
type Feed = { path: string; amounts: boolean; created_at: string | null };
type Reminders = { on: boolean; days: number; channel: "email" | "push" | "both"; cats: Cat[] };
type View = {
  events: Ev[]; start: string; end: string; today: string; as_of: string; cats: { id: Cat; label: string }[]; own: Own[]; own_max: number;
  feed: Feed | null; reminders: Reminders; reminders_allowed: boolean; reminders_plan: string; remind_days: number[]; notes: string[];
};

const CAT_LABEL: Record<Cat, string> = { tax: "Tax", holdings: "Holdings", money: "Money", custom: "Yours" };
const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const REPEAT: Record<Repeat, string> = { none: "Once", monthly: "Every month", yearly: "Every year" };
const inr = (v: number | null | undefined) => money(v, "INR", 0);

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s: string) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const addDays = (s: string, n: number) => { const d = parse(s); d.setDate(d.getDate() + n); return iso(d); };
const longDay = (s: string) => parse(s).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
const monthName = (y: number, m: number) => new Date(y, m, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

/** The feed's full address, for a calendar app (webcal:// opens the subscribe dialog on Apple devices). */
function feedUrl(path: string): string {
  const base = (CFG.API_BASE || window.location.origin).replace(/\/$/, "");
  return base + path;
}

function EventRow({ e, past }: { e: Ev; past: boolean }) {
  return (
    <li className={`mc-ev${past ? " past" : ""}`}>
      <span className={`badge mc-cat mc-${e.cat}`}>{CAT_LABEL[e.cat]}</span>
      <div className="mc-ev-body">
        <div className="mc-ev-title">{e.url ? <Link className="link" to={e.url}>{e.title}</Link> : e.title}
          {e.amount != null && <span className="num mc-amount"> {inr(e.amount)}</span>}</div>
        {e.detail && <div className="tiny muted">{e.detail}</div>}
      </div>
    </li>
  );
}

function DayList({ events, today, label = "Money dates" }: { events: Ev[]; today: string; label?: string }) {
  const days = useMemo(() => {
    const by = new Map<string, Ev[]>();
    for (const e of events) by.set(e.date, [...(by.get(e.date) ?? []), e]);
    return [...by.entries()];
  }, [events]);
  if (!days.length) return <p className="small muted" style={{ margin: 0 }}>Nothing in these dates.</p>;
  return (
    <ol className="mc-days" aria-label={label}>
      {days.map(([d, evs]) => (
        <li key={d} className="mc-day">
          <div className={`mc-date${d === today ? " today" : ""}`}><b>{longDay(d)}</b>{d === today && <span className="tiny"> · today</span>}</div>
          <ul className="mc-evs">{evs.map((e) => <EventRow key={e.id} e={e} past={d < today} />)}</ul>
        </li>
      ))}
    </ol>
  );
}

/** The person's own dates, each with Change and Delete. */
function OwnDates({ rows, edit, remove }: { rows: Own[]; edit: (o: Own) => void; remove: (o: Own) => void }) {
  return (
    <ul className="mc-own" aria-label="Your dates">
      {rows.map((o) => (
        <li key={o.id} className="spread" style={{ gap: 8 }}>
          <span className="small"><b>{o.title}</b> · {longDay(o.date)}{o.repeat !== "none" && <span className="muted"> · {REPEAT[o.repeat].toLowerCase()}</span>}{o.amount != null && <span className="num"> · {inr(o.amount)}</span>}</span>
          <span className="row" style={{ gap: 6, flex: "none" }}>
            <button className="btn quiet sm" onClick={() => edit(o)} aria-label={`Change ${o.title}`}>Change</button>
            <button className="btn quiet sm" onClick={() => remove(o)} aria-label={`Delete ${o.title}`}><Trash size={16} /></button>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Month({ y, m, events, today, picked, onPick }: { y: number; m: number; events: Ev[]; today: string; picked: string | null; onPick: (d: string) => void }) {
  const first = new Date(y, m, 1);
  const lead = (first.getDay() + 6) % 7;                 // Monday first
  const n = new Date(y, m + 1, 0).getDate();
  const by = new Map<string, Ev[]>();
  for (const e of events) by.set(e.date, [...(by.get(e.date) ?? []), e]);
  const cells: (string | null)[] = [...Array(lead).fill(null), ...Array.from({ length: n }, (_, i) => iso(new Date(y, m, i + 1)))];
  while (cells.length % 7) cells.push(null);
  return (
    <div className="mc-month" role="group" aria-label={monthName(y, m)}>
      {WEEK.map((w) => <div key={w} className="mc-wd" aria-hidden>{w}</div>)}
      {cells.map((d, i) => {
        if (!d) return <div key={i} className="mc-cell empty" aria-hidden />;
        const evs = by.get(d) ?? [];
        return (
          <button key={d} className={`mc-cell${d === today ? " today" : ""}${d === picked ? " picked" : ""}`} aria-pressed={d === picked}
            aria-label={`${longDay(d)}: ${evs.length ? `${evs.length} date${evs.length === 1 ? "" : "s"}` : "nothing"}`} onClick={() => onPick(d)}>
            <span className="mc-n">{parse(d).getDate()}</span>
            <span className="mc-dots" aria-hidden>{evs.slice(0, 4).map((e) => <i key={e.id} className={`mc-dot mc-${e.cat}`} />)}</span>
            <span className="mc-titles" aria-hidden>{evs.slice(0, 2).map((e) => <span key={e.id} className={`mc-t mc-${e.cat}`}>{e.title}</span>)}
              {evs.length > 2 && <span className="mc-more">+{evs.length - 2} more</span>}</span>
          </button>
        );
      })}
    </div>
  );
}

export function MoneyCalendarPage() {
  const { fail, notify } = useApp();
  const [mode, setMode] = useState<"list" | "month">(() => { try { return localStorage.getItem("stratlab.moneycal.mode") === "month" ? "month" : "list"; } catch { return "list"; } });
  const [cats, setCats] = useState<Cat[]>(["tax", "holdings", "money", "custom"]);
  const [view, setView] = useState<View | null>(null);
  const [cursor, setCursor] = useState<{ y: number; m: number }>(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() }; });
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const blank = { date: "", title: "", note: "", amount: "", repeat: "none" as Repeat };
  const [form, setForm] = useState<typeof blank & { id?: string }>(blank);
  const [amounts, setAmounts] = useState(false);
  const [rem, setRem] = useState<Reminders | null>(null);

  const range = useCallback((): [string, string] => {
    if (mode === "month") return [iso(new Date(cursor.y, cursor.m, 1)), iso(new Date(cursor.y, cursor.m + 1, 0))];
    const t = iso(new Date());
    return [addDays(t, -7), addDays(t, 90)];
  }, [mode, cursor]);

  const load = useCallback(() => {
    const [s, e] = range();
    return api<View>(`/money/calendar?start=${s}&end=${e}`).then((v) => { setView(v); setRem((r) => r ?? v.reminders); }).catch(fail);
  }, [range, fail]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { try { localStorage.setItem("stratlab.moneycal.mode", mode); } catch { /* storage off */ } }, [mode]);

  const shown = (view?.events ?? []).filter((e) => cats.includes(e.cat));
  const today = view?.today ?? iso(new Date());
  // a one-off date that has passed folds away; repeating ones come round again, so they stay
  const ownPast = (view?.own ?? []).filter((o) => o.repeat === "none" && o.date < today);
  const ownNow = (view?.own ?? []).filter((o) => !ownPast.includes(o));
  const toggleCat = (c: Cat) => setCats((x) => (x.includes(c) ? (x.length > 1 ? x.filter((y) => y !== c) : x) : [...x, c]));
  const step = (n: number) => { setPicked(null); setCursor(({ y, m }) => { const d = new Date(y, m + n, 1); return { y: d.getFullYear(), m: d.getMonth() }; }); };

  const saveEvent = async () => {
    const amount = form.amount.trim() ? Number(form.amount.replace(/,/g, "")) : null;
    if (!form.date || !form.title.trim() || (amount != null && !(amount >= 0))) { notify("Enter a date and a name; the amount is optional."); return; }
    setBusy(true);
    try {
      const body = { date: form.date, title: form.title.trim(), note: form.note.trim(), amount, repeat: form.repeat };
      if (form.id) await api(`/money/calendar/events/${form.id}`, { method: "PUT", body });
      else { await api("/money/calendar/events", { method: "POST", body }); track("money calendar event added", { repeat: form.repeat }); }
      notify(form.id ? "Saved." : `${form.title.trim()} added to your calendar.`);
      setForm(blank);
      await load();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const removeEvent = async (o: Own) => {
    if (!confirm(`Delete "${o.title}" from your calendar?`)) return;
    try { await api(`/money/calendar/events/${o.id}`, { method: "DELETE" }); await load(); } catch (e) { fail(e); }
  };

  const makeFeed = async (fresh: boolean) => {
    if (fresh && view?.feed && !confirm("Make a new link? The current one stops working, so calendars subscribed to it stop updating.")) return;
    setBusy(true);
    try {
      const f = await api<Feed>("/money/calendar/feed", { method: "POST", body: { amounts } });
      setView((v) => (v ? { ...v, feed: f } : v));
      track("money calendar feed made", { amounts: f.amounts });
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const setFeedAmounts = async (on: boolean) => {
    setAmounts(on);
    if (!view?.feed) return;
    try {
      const f = await api<Feed>("/money/calendar/feed", { method: "PUT", body: { amounts: on } });
      setView((v) => (v ? { ...v, feed: f } : v));
    } catch (e) { fail(e); }
  };
  const stopFeed = async () => {
    if (!confirm("Turn the link off? Calendars subscribed to it stop getting updates.")) return;
    try { await api("/money/calendar/feed", { method: "DELETE" }); setView((v) => (v ? { ...v, feed: null } : v)); notify("The link is off."); } catch (e) { fail(e); }
  };
  const copy = async (text: string) => {
    try { await navigator.clipboard.writeText(text); notify("Link copied. Keep it private: anyone with it can see your calendar."); } catch { notify("Select the link and copy it."); }
  };

  const saveReminders = async () => {
    if (!rem) return;
    setBusy(true);
    try {
      const r = await api<{ reminders: Reminders }>("/money/calendar/reminders", { method: "PUT", body: rem });
      setRem(r.reminders);
      notify(r.reminders.on ? `Reminders on: ${r.reminders.days} day${r.reminders.days === 1 ? "" : "s"} before.` : "Reminders off.");
    } catch (e) { fail(e); } finally { setBusy(false); }
  };

  const deleteAll = async () => {
    if (!confirm("Delete my money calendar? Your own events, the feed link and the reminder settings are removed. Tax and holdings dates come back on their own.")) return;
    try { await api("/money/calendar", { method: "DELETE" }); setRem(null); await load(); notify("Your money calendar is deleted."); } catch (e) { fail(e); }
  };

  useEffect(() => { if (view?.feed) setAmounts(view.feed.amounts); }, [view?.feed]);

  if (!view) return <Loading label="Opening your money calendar" />;
  const url = view.feed ? feedUrl(view.feed.path) : "";
  const dayEvents = picked ? shown.filter((e) => e.date === picked) : [];

  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="stack" style={{ gap: 8 }}>
        <span className="eyebrow">Money</span>
        <h1 className="serif" style={{ fontSize: "clamp(32px, 4vw, 46px)", fontWeight: 400, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Money calendar</h1>
        <p className="muted" style={{ fontSize: 17, maxWidth: 760 }}>Tax due dates, results and dividends for your holdings and watchlist, and your own dates, in one place. Subscribe from Google Calendar or Apple Calendar with a private link. Dates only, not advice.</p>
      </div>

      <section className="card stack" style={{ gap: 14 }}>
        <div className="spread" style={{ flexWrap: "wrap", gap: 10 }}>
          <div className="seg" role="group" aria-label="View">
            <button aria-pressed={mode === "list"} onClick={() => setMode("list")}>List</button>
            <button aria-pressed={mode === "month"} onClick={() => setMode("month")}>Month</button>
          </div>
          <div className="seg" role="group" aria-label="Show">
            {view.cats.map((c) => <button key={c.id} aria-pressed={cats.includes(c.id)} onClick={() => toggleCat(c.id)}>{c.label}</button>)}
          </div>
        </div>
        {mode === "month" ? (
          <div className="stack" style={{ gap: 12 }}>
            <div className="spread" style={{ gap: 8 }}>
              <button className="btn quiet sm" onClick={() => step(-1)} aria-label="Previous month">‹ Prev</button>
              <h2 className="h2" style={{ textAlign: "center" }}>{monthName(cursor.y, cursor.m)}</h2>
              <button className="btn quiet sm" onClick={() => step(1)} aria-label="Next month">Next ›</button>
            </div>
            <Month y={cursor.y} m={cursor.m} events={shown} today={today} picked={picked} onPick={(d) => setPicked(d === picked ? null : d)} />
            {picked ? <DayList events={dayEvents} today={today} /> : <p className="tiny muted" style={{ margin: 0 }}>Pick a day to see its dates.</p>}
          </div>
        ) : (
          <>
            <p className="tiny muted" style={{ margin: 0 }}>The next 90 days.</p>
            <DayList events={shown.filter((e) => e.date >= today)} today={today} />
            <Earlier label="The past week" count={shown.filter((e) => e.date < today).length}>
              <DayList events={shown.filter((e) => e.date < today)} today={today} label="The past week's dates" />
            </Earlier>
          </>
        )}
        <AsOf parts={[["Dates", view.as_of]]} />
      </section>

      <div className="grid2 mc-grid">
        <section className="card stack" style={{ gap: 12 }} aria-label="Your own dates">
          <h2 className="h2">{form.id ? "Change your date" : "Add your own date"}</h2>
          <p className="small muted" style={{ margin: 0 }}>A fixed deposit maturing, an insurance premium, an EMI, a rent increase: once, or every month or year.</p>
          <div className="mc-form">
            <label className="field">Date<input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
            <label className="field">Name<input value={form.title} maxLength={80} placeholder="e.g. FD matures" onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
            <label className="field">Amount, ₹ (optional)<input inputMode="decimal" value={form.amount} placeholder="e.g. 250000" onChange={(e) => setForm({ ...form, amount: e.target.value })} /></label>
            <label className="field">Repeats<select value={form.repeat} onChange={(e) => setForm({ ...form, repeat: e.target.value as Repeat })}>
              {(Object.keys(REPEAT) as Repeat[]).map((r) => <option key={r} value={r}>{REPEAT[r]}</option>)}</select></label>
            <label className="field mc-wide">Note (optional)<input value={form.note} maxLength={200} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button className="btn" disabled={busy} onClick={saveEvent}>{form.id ? "Save changes" : "Add to calendar"}</button>
            {form.id && <button className="btn quiet" onClick={() => setForm(blank)}>Cancel</button>}
          </div>
          {ownNow.length > 0 && <OwnDates rows={ownNow} edit={(o) => setForm({ id: o.id, date: o.date, title: o.title, note: o.note, amount: o.amount == null ? "" : String(o.amount), repeat: o.repeat })} remove={removeEvent} />}
          <Earlier label="Past dates" count={ownPast.length}>
            <OwnDates rows={ownPast} edit={(o) => setForm({ id: o.id, date: o.date, title: o.title, note: o.note, amount: o.amount == null ? "" : String(o.amount), repeat: o.repeat })} remove={removeEvent} />
          </Earlier>
        </section>

        <div className="stack" style={{ gap: 16 }}>
          <section className="card stack" style={{ gap: 12 }} aria-label="Calendar feed">
            <div className="row" style={{ gap: 6 }}><h2 className="h2">In your calendar app</h2>
              <Info label="About the calendar link">The link works without signing in, so treat it like a password. Make a new one if it's been shared, or turn it off. Calendar apps check it every few hours.</Info></div>
            <p className="small muted" style={{ margin: 0 }}>A private link with these dates for the past month and the next year. In Google Calendar: Other calendars, then From URL. On an iPhone or Mac: add a calendar subscription.</p>
            <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={amounts} onChange={(e) => setFeedAmounts(e.target.checked)} />Include my amounts (left out unless ticked)</label>
            {view.feed ? (
              <>
                <input className="input mc-url" readOnly value={url} aria-label="Your calendar link" onFocus={(e) => e.target.select()} />
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <button className="btn" onClick={() => copy(url)}><Copy size={16} />Copy link</button>
                  <a className="btn quiet" href={url.replace(/^https?:\/\//, "webcal://")}>Open in calendar app</a>
                  <button className="btn quiet" disabled={busy} onClick={() => makeFeed(true)}>New link</button>
                  <button className="btn quiet" onClick={stopFeed}>Turn off</button>
                </div>
              </>
            ) : <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={() => makeFeed(false)}>Make a private link</button>}
          </section>

          <section className="card stack" style={{ gap: 12 }} aria-label="Reminders">
            <h2 className="h2">Reminders</h2>
            {!view.reminders_allowed ? (
              <p className="small" style={{ margin: 0 }}>A reminder by email or phone a few days before each date is on the {view.reminders_plan} plan. <Link className="link" to="/plans">See plans</Link></p>
            ) : rem && (
              <>
                <label className="row small" style={{ gap: 8 }}><input type="checkbox" checked={rem.on} onChange={(e) => setRem({ ...rem, on: e.target.checked })} />Remind me before my dates</label>
                <div className="mc-form">
                  <label className="field">How early<select value={rem.days} onChange={(e) => setRem({ ...rem, days: Number(e.target.value) })}>
                    {view.remind_days.map((d) => <option key={d} value={d}>{d === 1 ? "The day before" : `${d} days before`}</option>)}</select></label>
                  <label className="field">By<select value={rem.channel} onChange={(e) => setRem({ ...rem, channel: e.target.value as Reminders["channel"] })}>
                    <option value="both">Email and phone</option><option value="email">Email</option><option value="push">Phone notification</option></select></label>
                </div>
                <div className="row small" style={{ gap: 14, flexWrap: "wrap" }} role="group" aria-label="Remind me about">
                  {view.cats.map((c) => (
                    <label key={c.id} className="row" style={{ gap: 6 }}><input type="checkbox" checked={rem.cats.includes(c.id)}
                      onChange={(e) => setRem({ ...rem, cats: e.target.checked ? [...rem.cats, c.id] : rem.cats.filter((x) => x !== c.id) })} />{c.label}</label>
                  ))}
                </div>
                <p className="tiny muted" style={{ margin: 0 }}>Sent through the email and phone notifications set up in <Link className="link" to="/account">Account</Link>. Reminders list the dates, not your amounts.</p>
                <button className="btn" style={{ alignSelf: "flex-start" }} disabled={busy} onClick={saveReminders}>Save reminders</button>
              </>
            )}
          </section>
        </div>
      </div>

      <section className="stack" style={{ gap: 8 }}>
        <ul className="tiny muted" style={{ margin: 0, paddingLeft: 20 }}>{view.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        <p className="tiny muted" style={{ margin: 0 }}>Only you can see your calendar. Your own dates and amounts are kept with your account and deleted with the button below.</p>
        <button className="btn quiet sm" style={{ alignSelf: "flex-start" }} onClick={deleteAll}><Trash size={16} />Delete my money calendar</button>
      </section>
    </div>
  );
}
