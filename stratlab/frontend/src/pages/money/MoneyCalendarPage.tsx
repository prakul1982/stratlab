import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { inr } from "../../lib/format";
import { Copy, Trash } from "../../components/Icons";
import { track } from "../../lib/analytics";
import { Earlier } from "../../components/Earlier";
import { Card, CardHead, CheckField, ChipSet, ConfirmDialog, EmptyState, ErrorState, Field, FormActions, FormGrid, PageHeader, PlanNote, Seg, Select, Skeleton } from "../../components/kit";

/* /money/calendar: tax due dates, results and dividends for your holdings and watchlist, plus your own dates, as a list
 * or a month, with a private link for any calendar app and reminders. Built from the kit (components/kit). */

type Cat = "tax" | "holdings" | "money" | "custom" | "market";
type Ev = { id: string; date: string; title: string; cat: Cat; kind: string; detail: string; amount: number | null; symbol: string | null;
  url: string | null; event_id?: string; repeat?: Repeat };
type Repeat = "none" | "monthly" | "yearly";
type Own = { id: string; date: string; title: string; note: string; amount: number | null; repeat: Repeat };
type Feed = { path: string; amounts: boolean; created_at: string | null };
type Reminders = { on: boolean; days: number; channel: "email" | "push" | "both"; cats: Cat[] };
type View = {
  events: Ev[]; start: string; end: string; today: string; as_of: string; cats: { id: Cat; label: string }[]; own: Own[]; own_max: number;
  feed: Feed | null; reminders: Reminders; reminders_allowed: boolean; market_on?: boolean; reminders_plan: string; remind_days: number[]; notes: string[];
};
type Ask = { title: string; body: string; label: string; run: () => Promise<void> };

const CAT_LABEL: Record<Cat, string> = { tax: "Tax", holdings: "Holdings", money: "Money", custom: "Yours", market: "Market" };
const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const REPEAT: Record<Repeat, string> = { none: "Once", monthly: "Every month", yearly: "Every year" };

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
          {e.amount != null && <span className="mc-amount"> {inr(e.amount)}</span>}</div>
        {e.detail && <div className="k-note">{e.detail}</div>}
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
  if (!days.length) return <p className="k-small k-muted">Nothing in these dates.</p>;
  return (
    <ol className="mc-days" aria-label={label}>
      {days.map(([d, evs]) => (
        <li key={d} className="mc-day">
          <div className={`mc-date${d === today ? " today" : ""}`}><b>{longDay(d)}</b>{d === today && <span className="k-note"> · today</span>}</div>
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
        <li key={o.id} className="k-spread">
          <span className="k-small"><b>{o.title}</b> · {longDay(o.date)}{o.repeat !== "none" && <span className="k-muted"> · {REPEAT[o.repeat].toLowerCase()}</span>}{o.amount != null && <span> · {inr(o.amount)}</span>}</span>
          <span className="k-row">
            <button type="button" className="btn quiet sm" onClick={() => edit(o)} aria-label={`Change ${o.title}`}>Change</button>
            <button type="button" className="btn quiet sm" onClick={() => remove(o)} aria-label={`Delete ${o.title}`}><Trash size={16} /></button>
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
          <button key={d} type="button" className={`mc-cell${d === today ? " today" : ""}${d === picked ? " picked" : ""}`} aria-pressed={d === picked}
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
  const [cats, setCats] = useState<Cat[]>(["tax", "holdings", "money", "custom", "market"]);
  const [view, setView] = useState<View | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cursor, setCursor] = useState<{ y: number; m: number }>(() => { const d = new Date(); return { y: d.getFullYear(), m: d.getMonth() }; });
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const blank = { date: "", title: "", note: "", amount: "", repeat: "none" as Repeat };
  const [form, setForm] = useState<typeof blank & { id?: string }>(blank);
  const [amounts, setAmounts] = useState(false);
  const [rem, setRem] = useState<Reminders | null>(null);
  const [ask, setAsk] = useState<Ask | null>(null);

  const range = useCallback((): [string, string] => {
    if (mode === "month") return [iso(new Date(cursor.y, cursor.m, 1)), iso(new Date(cursor.y, cursor.m + 1, 0))];
    const t = iso(new Date());
    return [addDays(t, -7), addDays(t, 90)];
  }, [mode, cursor]);

  const load = useCallback(() => {
    const [s, e] = range();
    setError(null);
    return api<View>(`/money/calendar?start=${s}&end=${e}`).then((v) => { setView(v); setRem((r) => r ?? v.reminders); })
      .catch((err) => { setError(err instanceof Error ? err.message : "The calendar couldn't be read."); fail(err); });
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
  const removeEvent = (o: Own) => setAsk({
    title: `Delete "${o.title}"?`, body: "It is removed from your calendar and its link.", label: "Delete this date",
    run: async () => { await api(`/money/calendar/events/${o.id}`, { method: "DELETE" }); await load(); },
  });

  const makeFeed = async (fresh: boolean) => {
    setBusy(true);
    try {
      const f = await api<Feed>("/money/calendar/feed", { method: "POST", body: { amounts } });
      setView((v) => (v ? { ...v, feed: f } : v));
      track("money calendar feed made", { amounts: f.amounts });
      if (fresh) notify("The new link is ready. The old one has stopped working.");
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
  const stopFeed = () => setAsk({
    title: "Turn the link off?", body: "Calendars subscribed to it stop getting updates.", label: "Turn it off",
    run: async () => { await api("/money/calendar/feed", { method: "DELETE" }); setView((v) => (v ? { ...v, feed: null } : v)); notify("The link is off."); },
  });
  const newFeed = () => setAsk({
    title: "Make a new link?", body: "The current one stops working, so calendars subscribed to it stop updating.", label: "Make a new link",
    run: () => makeFeed(true),
  });
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

  const deleteAll = () => setAsk({
    title: "Delete my money calendar?", body: "Your own events, the feed link and the reminder settings are removed. Tax and holdings dates come back on their own.", label: "Delete my money calendar",
    run: async () => { await api("/money/calendar", { method: "DELETE" }); setRem(null); await load(); notify("Your money calendar is deleted."); },
  });
  const confirm = async () => {
    if (!ask) return;
    setBusy(true);
    try { await ask.run(); } catch (e) { fail(e); } finally { setBusy(false); setAsk(null); }
  };

  useEffect(() => { if (view?.feed) setAmounts(view.feed.amounts); }, [view?.feed]);

  const head = (
    <PageHeader eyebrow="Money · Plan" title="Money calendar" asOf={view?.as_of} asOfLabel="Dates up to"
      lede="Tax due dates, results and dividends for your holdings and watchlist, plus your own dates. Subscribe from any calendar app with a private link." />
  );
  if (!view) {
    return (
      <div className="k-page">
        {head}
        {error ? <ErrorState title="The calendar couldn't be read" action={{ label: "Try again", onClick: () => { void load(); } }}>{error}</ErrorState> : <Card><Skeleton label="Opening your money calendar" /></Card>}
      </div>
    );
  }
  const url = view.feed ? feedUrl(view.feed.path) : "";
  const dayEvents = picked ? shown.filter((e) => e.date === picked) : [];
  const upcoming = shown.filter((e) => e.date >= today);
  const editOwn = (o: Own) => setForm({ id: o.id, date: o.date, title: o.title, note: o.note, amount: o.amount == null ? "" : String(o.amount), repeat: o.repeat });

  return (
    <div className="k-page">
      {head}

      <Card>
        <CardHead title={mode === "month" ? monthName(cursor.y, cursor.m) : "The next 90 days"} actions={<>
          {mode === "month" && <>
            <button type="button" className="btn quiet sm" onClick={() => step(-1)} aria-label="Previous month">‹ Prev</button>
            <button type="button" className="btn quiet sm" onClick={() => step(1)} aria-label="Next month">Next ›</button>
          </>}
          <Seg label="View" options={[{ value: "list", label: "List" }, { value: "month", label: "Month" }]} value={mode} onChange={(v) => setMode(v as typeof mode)} />
        </>} />
        <ChipSet label="Show" options={view.cats.map((c) => ({ value: c.id, label: c.label }))} on={cats} onToggle={(v) => toggleCat(v as Cat)} />
        {mode === "month" ? (
          <div className="k-stack">
            <Month y={cursor.y} m={cursor.m} events={shown} today={today} picked={picked} onPick={(d) => setPicked(d === picked ? null : d)} />
            {picked ? <DayList events={dayEvents} today={today} /> : <p className="k-note">Pick a day to see its dates.</p>}
          </div>
        ) : (
          <>
            {upcoming.length === 0
              ? <EmptyState title="Nothing in the next 90 days">Tax due dates, results and dividends for your holdings appear here. Add your own date below.</EmptyState>
              : <DayList events={upcoming} today={today} />}
            <Earlier label="The past week" count={shown.filter((e) => e.date < today).length}>
              <DayList events={shown.filter((e) => e.date < today)} today={today} label="The past week's dates" />
            </Earlier>
          </>
        )}
      </Card>

      <div className="k-two mc-grid">
        <Card label="Your own dates">
          <CardHead title={form.id ? "Change your date" : "Add your own date"} info="A fixed deposit maturing, an insurance premium, an EMI, a rent increase: once, or every month or year." />
          <FormGrid onSubmit={(e) => { e.preventDefault(); void saveEvent(); }} label="Your own date">
            <Field label="Date" type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} />
            <Field label="Name" maxLength={80} placeholder="e.g. FD matures" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
            <Field label="Amount" optional unit="₹" inputMode="decimal" placeholder="e.g. 250000" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            <Field label="Repeats">{(id) => <Select id={id} value={form.repeat} onChange={(v) => setForm({ ...form, repeat: v as Repeat })} options={(Object.keys(REPEAT) as Repeat[]).map((r) => ({ value: r, label: REPEAT[r] }))} />}</Field>
            <Field label="Note" optional wide maxLength={200} value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            <FormActions>
              <button type="submit" className="btn" disabled={busy}>{form.id ? "Save changes" : "Add to calendar"}</button>
              {form.id && <button type="button" className="btn quiet" onClick={() => setForm(blank)}>Cancel</button>}
            </FormActions>
          </FormGrid>
          {ownNow.length > 0 && <OwnDates rows={ownNow} edit={editOwn} remove={removeEvent} />}
          <Earlier label="Past dates" count={ownPast.length}>
            <OwnDates rows={ownPast} edit={editOwn} remove={removeEvent} />
          </Earlier>
        </Card>

        <div className="k-page">
          <Card label="Calendar feed">
            <CardHead title="In your calendar app" info="The link works without signing in, so treat it like a password. Make a new one if it's been shared, or turn it off. Calendar apps check it every few hours." />
            <p className="k-small k-muted">A private link with these dates for the past month and the next year. In Google Calendar: Other calendars, then From URL. On an iPhone or Mac: add a calendar subscription.</p>
            <CheckField label="Include my amounts (left out unless ticked)" checked={amounts} onChange={setFeedAmounts} />
            {view.feed ? (
              <>
                <input className="k-input mc-url" readOnly value={url} aria-label="Your calendar link" onFocus={(e) => e.target.select()} />
                <div className="k-row">
                  <button type="button" className="btn" onClick={() => copy(url)}><Copy size={16} />Copy link</button>
                  <a className="btn quiet" href={url.replace(/^https?:\/\//, "webcal://")}>Open in calendar app</a>
                  <button type="button" className="btn quiet" disabled={busy} onClick={newFeed}>New link</button>
                  <button type="button" className="btn quiet" onClick={stopFeed}>Turn off</button>
                </div>
              </>
            ) : <button type="button" className="btn k-btn-end" disabled={busy} onClick={() => makeFeed(false)}>Make a private link</button>}
          </Card>

          <Card label="Reminders">
            <CardHead title="Reminders" info="Sent through the email and phone notifications set up in Account. Reminders list the dates, not your amounts." />
            {!view.reminders_allowed ? (
              <PlanNote>A reminder by email or phone a few days before each date is on the {view.reminders_plan} plan.</PlanNote>
            ) : rem && (
              <FormGrid label="Reminders" onSubmit={(e) => { e.preventDefault(); void saveReminders(); }}>
                <div className="k-field wide"><CheckField label="Remind me before my dates" checked={rem.on} onChange={(on) => setRem({ ...rem, on })} /></div>
                <Field label="How early">{(id) => <Select id={id} value={rem.days} onChange={(v) => setRem({ ...rem, days: Number(v) })} options={view.remind_days.map((d) => ({ value: d, label: d === 1 ? "The day before" : `${d} days before` }))} />}</Field>
                <Field label="By">{(id) => <Select id={id} value={rem.channel} onChange={(v) => setRem({ ...rem, channel: v as Reminders["channel"] })}
                  options={[{ value: "both", label: "Email and phone" }, { value: "email", label: "Email" }, { value: "push", label: "Phone notification" }]} />}</Field>
                <div className="k-field wide" role="group" aria-label="Remind me about">
                  <div className="k-label-row"><span className="k-lbl">Remind me about</span></div>
                  <div className="k-row">
                    {view.cats.filter((c) => c.id !== "market").map((c) => (
                      <CheckField key={c.id} label={c.label} checked={rem.cats.includes(c.id)}
                        onChange={(on) => setRem({ ...rem, cats: on ? [...rem.cats, c.id] : rem.cats.filter((x) => x !== c.id) })} />
                    ))}
                  </div>
                </div>
                <FormActions><button type="submit" className="btn" disabled={busy}>Save reminders</button></FormActions>
              </FormGrid>
            )}
          </Card>
        </div>
      </div>

      <section className="k-stack">
        {view.notes.length > 0 && <ul className="k-list muted">{view.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>}
        <p className="k-note" data-testid="mc-market">
          {view.market_on ? "Market events (RBI policy, data releases, the Fed, index changes) are in this calendar and its feed. "
            : "RBI policy, data releases, the Fed and index changes can go into this calendar and its feed too. "}
          <Link className="link" to="/trade/events">{view.market_on ? "Change which ones" : "Turn them on from Market events"}</Link>
        </p>
        <p className="k-note">Only you can see your calendar. Your own dates and amounts are kept with your account and deleted with the button below.</p>
        <button type="button" className="btn quiet sm k-btn-end" onClick={deleteAll}><Trash size={16} />Delete my money calendar</button>
      </section>

      {ask && <ConfirmDialog title={ask.title} confirmLabel={ask.label} onConfirm={() => void confirm()} onClose={() => setAsk(null)} busy={busy}>{ask.body}</ConfirmDialog>}
    </div>
  );
}
