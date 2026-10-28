import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { asOf as asOfText, dateOnly, inr, monthLong, pctPlain, signed, signedInrCompact } from "../../lib/format";
import { Info } from "../../components/ui";
import { EmptyState, PlanNote, Signed, Stat } from "../../components/kit";

// Your SIP and fund behaviour: your XIRR beside each fund's own NAV return over the same dates, the gap in points and
// rupees, the SIP record, redemptions after a fall from the high, and holding periods. What happened, never advice. The page says
// each scheme once (MF-1, RC2B-047): the totals are one block (BehaviourStats, BehaviourNotes), and a scheme's own return, SIP record and
// falls are folded under its row (BehaviourDetail), both read from the one load (useFundBehaviour).
export type Sip = { first: string; last: string; months_paid: number; months_missed: number; missed: string[]; instalments: number; longest_run: number;
  longest_from: string; longest_to: string; current_run: number; stopped: boolean; stopped_after: string | null };
export type Fall = { date: string; type: string; units: number; nav: number; high: number; high_date: string; fall_pct: number; received: number | null;
  worth_today: number | null; difference: number | null };
export type Row = {
  key: string; name: string; folio: string; held: boolean; xirr: number | null; fund: number | null; gap_pp: number | null; gap_rupees: number | null;
  from: string | null; to: string | null; start_nav: number | null; end_nav: number | null; idcw: boolean; short_span: boolean; full: boolean;
  sip?: Sip | null; falls?: Fall[]; high_source?: "history" | "statement"; redeemed_units?: number | null; avg_days_held?: number | null;
  value?: number | null; long_value?: number | null; long_share?: number | null;
};
export type Total = { schemes: number; compared: number; gap_rupees?: number | null; sips?: number; sips_running?: number; sips_stopped?: number; months_missed?: number;
  falls?: number; falls_received?: number | null; falls_worth_today?: number | null; avg_days_held?: number | null; held_under_year_pct?: number | null;
  long_share?: number | null; long_value?: number | null };
export type Behaviour = { full: boolean; plan: string; schemes: Row[]; total: Total | null; pending: number; last_txn: string | null; fall_pct: number;
  long_years: number; assumptions: string[]; disclaimer: string; as_of: string };

const rate = (v: number | null | undefined) => (v == null ? "–" : pctPlain(v * 100, 1));
const pts = (v: number | null | undefined) => <Signed value={v}>{v == null ? "–" : `${signed(v, 1)} pts`}</Signed>;
const rupees = (v: number | null | undefined) => <Signed value={v}>{signedInrCompact(v)}</Signed>;
const month = (m: string) => monthLong(m);
const span = (days: number | null | undefined) => (days == null ? "–" : days >= 365 ? `${(days / 365).toFixed(1)} years` : `${days} days`);

export type BehaviourQuery = { b: Behaviour | null; failed: boolean; retry: () => void };

export function useFundBehaviour(version: string, on: boolean): BehaviourQuery {
  const [b, setB] = useState<Behaviour | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!on) return;
    let live = true;
    api<Behaviour>("/money/mutual-funds/behaviour").then((r) => { if (live) { setB(r); setFailed(false); } }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [version, tick, on]);
  // NAV history for funds with redemptions is read in the background: look again every few seconds, for a while
  useEffect(() => {
    if (!b?.pending || tick >= 40) return;
    const t = window.setTimeout(() => setTick((n) => n + 1), 6000);
    return () => window.clearTimeout(t);
  }, [b, tick]);
  return { b, failed, retry: () => setTick((n) => n + 1) };
}

/** What the habits block has to show: its totals, or why not. */
export const behaviourShown = (q: BehaviourQuery) => q.failed || (!!q.b && !!q.b.total && q.b.schemes.length > 0);

/** One scheme's row of the comparison, by its key. */
export const behaviourOf = (q: BehaviourQuery, key: string): Row | undefined => q.b?.schemes.find((s) => s.key === key);

/** The totals over every fund, as stats for the page's one row of them (the gap in rupees, SIPs, redemptions after a fall, how long money was held). */
export function BehaviourStats({ q }: { q: BehaviourQuery }) {
  const { b } = q;
  if (!b || !b.total || !b.schemes.length || !b.full) return null;
  const t = b.total;
  return (
    <>
      <Stat label={<>Gap in rupees, all funds <Info label="How the gap in rupees is worked out">Your value today and what you took out, less what the same purchases and redemptions would come to at each fund's own yearly NAV return. Positive: timing added to the fund's return. Negative: it took away. Your XIRR counts when your money went in and came out; the fund's NAV return is what a rupee kept in it all along earned over the same dates. The gap is what timing did: what happened, not what to do next.</Info></>}
        value={rupees(t.gap_rupees)} note={`${t.compared} of ${t.schemes} fund${t.schemes === 1 ? "" : "s"} compared`} />
      <Stat label="SIPs" value={t.sips ?? 0} note={`${t.sips_running ?? 0} running · ${t.sips_stopped ?? 0} stopped · ${t.months_missed ?? 0} month${t.months_missed === 1 ? "" : "s"} missed`} />
      <Stat label={`Redemptions after a ${b.fall_pct}% fall`} value={b.pending > 0 ? "–" : t.falls ?? 0}
        note={b.pending > 0 ? `Reading the NAV history of ${b.pending} fund${b.pending === 1 ? "" : "s"} to find each high` : (t.falls ?? 0) > 0 ? `${inr(t.falls_received)} received · ${inr(t.falls_worth_today)} today` : `None came ${b.fall_pct}% or more below the fund's high`} />
      {/* DG-025: by the money redeemed, not by units of different schemes */}
      <Stat label="Money redeemed was held, on average" value={span(t.avg_days_held)} note={t.held_under_year_pct != null ? `${t.held_under_year_pct.toFixed(0)}% of it for a year or less` : undefined} />
      <Stat label={`Today's value held over ${b.long_years} years`} value={t.long_share == null ? "–" : `${t.long_share.toFixed(0)}%`} note={t.long_value != null ? inr(t.long_value) : undefined} />
    </>
  );
}

/** What the habits need said under their stats: why there are none, what the plan keeps back, how far the SIPs are counted. */
export function BehaviourNotes({ q }: { q: BehaviourQuery }) {
  const { b, failed, retry } = q;
  if (failed) return <EmptyState title="This couldn't be loaded" action={{ label: "Try again", onClick: retry }}>This couldn't be loaded just now.</EmptyState>;
  if (!b || !b.total || !b.schemes.length) return null;
  return (
    <>
      {!b.full && <PlanNote>The gap in rupees, your SIP record, redemptions after a fall and how long you held are on the {b.plan} plan.</PlanNote>}
      {b.full && b.last_txn && b.schemes.some((s) => s.sip) && <p className="k-note">SIPs are counted up to your statement's latest transaction, {dateOnly(b.last_txn)}. Import a newer statement to bring it up to date.</p>}
    </>
  );
}

/** How your return against the fund's is worked out, for the page's one fold of method. */
export function BehaviourHow({ q }: { q: BehaviourQuery }) {
  const { b } = q;
  if (!b || !b.total || !b.schemes.length) return null;
  return (
    <>
      <ul className="k-list muted">
        {b.full && b.schemes.some((s) => (s.falls ?? []).length > 0) && <li>"Those units today" is hindsight arithmetic: the same units at today's NAV, known only afterwards.</li>}
        {b.assumptions.map((a, i) => <li key={i}>{a}</li>)}
      </ul>
      <p className="k-note">{asOfText(b.as_of) ? `Worked out ${asOfText(b.as_of)}. ` : ""}{b.disclaimer}</p>
    </>
  );
}

/** The gap to the fund's own NAV return in points, with that return under it: the one comparison a row shows. */
/** Whether a scheme has a gap to show (the scheme list leaves out the "Against the fund" column when none has). */
export function hasGap(q: BehaviourQuery, id: string): boolean {
  return behaviourOf(q, id)?.gap_pp != null;
}

export function GapCell({ q, id }: { q: BehaviourQuery; id: string }) {
  const s = behaviourOf(q, id);
  if (!s || s.gap_pp == null) return <span className="k-none">–</span>;
  return <>{pts(s.gap_pp)}<span className="k-sub-line">Fund's NAV return {rate(s.fund)}</span></>;
}

/** The rest of one scheme's story, in its folded detail: the dates compared, the gap in rupees, its SIP record and its redemptions after a fall. */
export function BehaviourDetail({ q, id, name }: { q: BehaviourQuery; id: string; name?: string }) {
  const { b } = q;
  const s = behaviourOf(q, id);
  if (!b || !s) return null;
  const r = s.sip;
  const falls = s.falls ?? [];
  return (
    <section aria-label={name ? `How you invested, ${name}` : "How you invested"}>
      <h3>How you invested</h3>
      <p className="k-small">
        <b>Compared over</b> {s.from ? `${dateOnly(s.from)} to ${s.held ? "today" : dateOnly(s.to)}` : "No dated purchase in the statement"}
        {s.start_nav != null && s.end_nav != null ? ` · NAV ${s.start_nav} to ${s.end_nav}` : ""}
        {b.full && <> · <b>Gap in ₹</b> {rupees(s.gap_rupees)}</>}
      </p>
      {s.idcw && <p className="k-note">IDCW option: the NAV return leaves out payouts; your XIRR counts them.</p>}
      {s.short_span && <p className="k-note">Under a year: both rates annualised from a short span.</p>}
      {b.full && r && (
        <>
          <p className="k-small">
            <b>SIP record.</b> {month(r.first)} to {month(r.last)}: {r.months_paid} month{r.months_paid === 1 ? "" : "s"} paid, {r.months_missed} missed · longest unbroken run {r.longest_run} month{r.longest_run === 1 ? "" : "s"} ({month(r.longest_from)} to {month(r.longest_to)})
            {r.stopped ? ` · no instalment after ${month(r.stopped_after!)}` : ` · running for ${r.current_run} month${r.current_run === 1 ? "" : "s"}`}
          </p>
          {r.missed.length > 0 && <p className="k-note">Missed: {r.missed.map(month).join(", ")}{r.months_missed > r.missed.length ? " and earlier" : ""}</p>}
        </>
      )}
      {b.full && falls.length > 0 && b.pending === 0 && (
        <>
          <p className="k-small"><b>Redemptions after a fall of {b.fall_pct}% or more</b></p>
          <ul className="k-list plain" aria-label="Redemptions after a fall">
            {falls.map((f) => (
              <li key={`${f.date}${f.type}${f.units}`} className="k-small">
                {dateOnly(f.date)}: {f.type === "switch_out" ? "switch out" : "redemption"} of {f.units} units at NAV {f.nav}, {f.fall_pct}% below the high of {f.high} ({dateOnly(f.high_date)}{s.high_source === "statement" ? ", from your statement" : ""}).
                {" "}Received {inr(f.received)}; those units today {inr(f.worth_today)} ({rupees(f.difference)}).
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
