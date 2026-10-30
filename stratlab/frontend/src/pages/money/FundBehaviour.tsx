import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { asOf as asOfText, dateOnly, inr, monthLong, pctPlain, signed, signedInrCompact } from "../../lib/format";
import { Info } from "../../components/ui";
import { DataTable, EmptyState, FactTable, Notes, PlanNote, Signed, type Column, type Fact, type Figure } from "../../components/kit";

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

/** Which of the totals have anything to say (LIVE1B-017: a row of "–", "0" and "0 running · 0 stopped" is a row of nothing): a gap
 * when some fund could be compared, SIPs when there is one, redemptions after a fall when one came or the history is still being
 * read, the holding period when money was redeemed, the long-held share when it is known. */
export function behaviourParts(b: Behaviour | null) {
  if (!b || !b.total || !b.schemes.length || !b.full) return null;
  const t = b.total;
  return { gap: t.compared > 0, sips: (t.sips ?? 0) > 0, falls: b.pending > 0 || (t.falls ?? 0) > 0, held: t.avg_days_held != null, long: t.long_share != null };
}
export const behaviourStatsShown = (q: BehaviourQuery) => { const p = behaviourParts(q.b); return !!p && Object.values(p).some(Boolean); };

/** The totals over every fund, as rows of the page's one table of totals (TABLE-SWEEP): the gap in rupees, SIPs, redemptions after a
 * fall, how long money was held. */
export function behaviourFigures(q: BehaviourQuery): Figure[] {
  const { b } = q;
  const parts = behaviourParts(b);
  if (!b || !b.total || !parts) return [];
  const t = b.total;
  const out: Figure[] = [];
  if (parts.gap) out.push({ key: "gap", label: <>Gap in rupees, all funds <Info label="How the gap in rupees is worked out">Your value today and what you took out, less what the same purchases and redemptions would come to at each fund's own yearly NAV return. Positive: timing added to the fund's return. Negative: it took away. Your XIRR counts when your money went in and came out; the fund's NAV return is what a rupee kept in it all along earned over the same dates. The gap is what timing did: what happened, not what to do next.</Info></>,
    value: rupees(t.gap_rupees), note: `${t.compared} of ${t.schemes} fund${t.schemes === 1 ? "" : "s"} compared` });
  if (parts.sips) out.push({ key: "sips", label: "SIPs", value: t.sips ?? 0, note: `${t.sips_running ?? 0} running · ${t.sips_stopped ?? 0} stopped · ${t.months_missed ?? 0} month${t.months_missed === 1 ? "" : "s"} missed` });
  if (parts.falls) out.push({ key: "falls", label: `Redemptions after a ${b.fall_pct}% fall`, value: b.pending > 0 ? "–" : t.falls ?? 0,
    note: b.pending > 0 ? `Reading the NAV history of ${b.pending} fund${b.pending === 1 ? "" : "s"} to find each high` : `${inr(t.falls_received)} received · ${inr(t.falls_worth_today)} today` });
  // DG-025: by the money redeemed, not by units of different schemes
  if (parts.held) out.push({ key: "held", label: "Money redeemed was held, on average", value: span(t.avg_days_held), note: t.held_under_year_pct != null ? `${t.held_under_year_pct.toFixed(0)}% of it for a year or less` : undefined });
  if (parts.long) out.push({ key: "long", label: `Today's value held over ${b.long_years} years`, value: `${t.long_share!.toFixed(0)}%`, note: t.long_value != null ? inr(t.long_value) : undefined });
  return out;
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
      <Notes label="How this is worked out" items={[
        b.full && b.schemes.some((s) => (s.falls ?? []).length > 0) && "\"Those units today\" is hindsight arithmetic: the same units at today's NAV, known only afterwards.",
        ...b.assumptions,
      ]} />
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
  const facts: Fact[] = [
    { id: "span", k: "Compared over", v: s.from ? `${dateOnly(s.from)} to ${s.held ? "today" : dateOnly(s.to)}` : "No dated purchase in the statement",
      n: s.start_nav != null && s.end_nav != null ? `NAV ${s.start_nav} to ${s.end_nav}` : undefined },
    ...(b.full ? [{ id: "gap", k: "Gap in ₹", v: rupees(s.gap_rupees) }] : []),
    ...(b.full && r ? [{ id: "sip", k: "SIP record", v: `${r.months_paid} month${r.months_paid === 1 ? "" : "s"} paid, ${r.months_missed} missed`,
      n: <>{month(r.first)} to {month(r.last)} · longest unbroken run {r.longest_run} month{r.longest_run === 1 ? "" : "s"} ({month(r.longest_from)} to {month(r.longest_to)})
        {r.stopped ? ` · no instalment after ${month(r.stopped_after!)}` : ` · running for ${r.current_run} month${r.current_run === 1 ? "" : "s"}`}</> }] : []),
    ...(b.full && r && r.missed.length > 0 ? [{ id: "missed", k: "Missed", v: <>{r.missed.map(month).join(", ")}{r.months_missed > r.missed.length ? " and earlier" : ""}</> }] : []),
  ];
  const fallCols: Column<Fall>[] = [
    { key: "d", header: "Date", rowHeader: true, cell: (f) => <span className="nowrap">{dateOnly(f.date)}</span> },
    { key: "t", header: "What", cell: (f) => (f.type === "switch_out" ? "Switch out" : "Redemption") },
    { key: "u", header: "Units", numeric: true, cell: (f) => f.units },
    { key: "n", header: "NAV", numeric: true, cell: (f) => f.nav },
    { key: "h", header: "Below the high", numeric: true, cell: (f) => <>{f.fall_pct}%<span className="k-sub-line">high {f.high} on {dateOnly(f.high_date)}{s.high_source === "statement" ? ", from your statement" : ""}</span></> },
    { key: "r", header: "Received", numeric: true, cell: (f) => inr(f.received) },
    { key: "w", header: "Those units today", numeric: true, cell: (f) => <>{inr(f.worth_today)}<span className="k-sub-line">{rupees(f.difference)}</span></> },
  ];
  // TABLE-SWEEP (owner, 29 Oct): the scheme's story as a table of facts, and each redemption after a fall as a row (they were sentences)
  return (
    <section aria-label={name ? `How you invested, ${name}` : "How you invested"}>
      <h3>How you invested</h3>
      <FactTable label={name ? `How you invested in ${name}` : "How you invested in it"} itemHead="Fact" figureHead="Figure" noteHead="Detail" rows={facts} noteUnder />
      <Notes label="About these figures" items={[
        s.idcw && "IDCW option: the NAV return leaves out payouts; your XIRR counts them.",
        s.short_span && "Under a year: both rates annualised from a short span.",
      ]} />
      {b.full && falls.length > 0 && b.pending === 0 && (
        <>
          <h3>Redemptions after a fall of {b.fall_pct}% or more</h3>
          <DataTable label={name ? `Redemptions after a fall, ${name}` : "Redemptions after a fall, this scheme"} columns={fallCols} rows={falls} rowKey={(f) => `${f.date}${f.type}${f.units}`} />
        </>
      )}
    </section>
  );
}
