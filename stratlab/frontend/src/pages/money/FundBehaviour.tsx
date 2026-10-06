import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { asOf as asOfText, dateOnly, inr, pctPlain, signed, signedInrCompact } from "../../lib/format";
import { Info } from "../../components/ui";
import { Earlier } from "../../components/Earlier";
import { Card, CardHead, DataTable, Disclosure, EmptyState, PlanNote, Stat, StatRow, type Column } from "../../components/kit";

// Your SIP and fund behaviour: your XIRR beside each fund's own NAV return over the same dates, the gap in points and
// rupees, the SIP record, redemptions after a fall from the high, and holding periods. What happened, never advice.
type Sip = { first: string; last: string; months_paid: number; months_missed: number; missed: string[]; instalments: number; longest_run: number;
  longest_from: string; longest_to: string; current_run: number; stopped: boolean; stopped_after: string | null };
type Fall = { date: string; type: string; units: number; nav: number; high: number; high_date: string; fall_pct: number; received: number | null;
  worth_today: number | null; difference: number | null };
type Row = {
  key: string; name: string; folio: string; held: boolean; xirr: number | null; fund: number | null; gap_pp: number | null; gap_rupees: number | null;
  from: string | null; to: string | null; start_nav: number | null; end_nav: number | null; idcw: boolean; short_span: boolean; full: boolean;
  sip?: Sip | null; falls?: Fall[]; high_source?: "history" | "statement"; redeemed_units?: number | null; avg_days_held?: number | null;
  value?: number | null; long_value?: number | null; long_share?: number | null;
};
type Total = { schemes: number; compared: number; gap_rupees?: number | null; sips?: number; sips_running?: number; sips_stopped?: number; months_missed?: number;
  falls?: number; falls_received?: number | null; falls_worth_today?: number | null; avg_days_held?: number | null; held_under_year_pct?: number | null;
  long_share?: number | null; long_value?: number | null };
type Behaviour = { full: boolean; plan: string; schemes: Row[]; total: Total | null; pending: number; last_txn: string | null; fall_pct: number;
  long_years: number; assumptions: string[]; disclaimer: string; as_of: string };
type FallRow = Fall & { name: string; source?: "history" | "statement"; i: number };

const rate = (v: number | null | undefined) => (v == null ? "–" : pctPlain(v * 100, 1));
const pts = (v: number | null | undefined) => (v == null ? "–" : `${signed(v, 1)} pts`);
const rupees = (v: number | null | undefined) => signedInrCompact(v);
const month = (m: string) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-GB", { month: "short", year: "numeric" });
const span = (days: number | null | undefined) => (days == null ? "–" : days >= 365 ? `${(days / 365).toFixed(1)} years` : `${days} days`);

export function FundBehaviour({ version }: { version: string }) {
  const [b, setB] = useState<Behaviour | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    api<Behaviour>("/money/mutual-funds/behaviour").then((r) => { if (live) { setB(r); setFailed(false); } }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [version, tick]);
  // NAV history for funds with redemptions is read in the background: look again every few seconds, for a while
  useEffect(() => {
    if (!b?.pending || tick >= 40) return;
    const t = window.setTimeout(() => setTick((n) => n + 1), 6000);
    return () => window.clearTimeout(t);
  }, [b, tick]);

  if (failed) return (
    <Card label="Fund behaviour"><CardHead title="Your return against each fund's" />
      <EmptyState title="This couldn't be loaded" action={{ label: "Try again", onClick: () => setTick((n) => n + 1) }}>This couldn't be loaded just now. Reload the page to try again.</EmptyState></Card>
  );
  if (!b || !b.total || !b.schemes.length) return null;
  const t = b.total;
  const held = b.schemes.filter((s) => s.held), gone = b.schemes.filter((s) => !s.held);
  const sips = b.schemes.filter((s) => s.sip);
  const falls: FallRow[] = b.schemes.flatMap((s) => (s.falls ?? []).map((f) => ({ ...f, name: s.name, source: s.high_source }))).map((f, i) => ({ ...f, i }));

  const cols: Column<Row>[] = [
    { key: "scheme", header: "Scheme", rowHeader: true, wrap: true, cell: (s) => (
      <>
        <b>{s.name}</b>
        <span className="k-sub-line">{s.from ? `${dateOnly(s.from)} to ${s.held ? "today" : dateOnly(s.to)}` : "No dated purchase in the statement"}
          {s.start_nav != null && s.end_nav != null ? ` · NAV ${s.start_nav} to ${s.end_nav}` : ""}</span>
        {s.idcw && <span className="k-sub-line">IDCW option: the NAV return leaves out payouts; your XIRR counts them.</span>}
        {s.short_span && <span className="k-sub-line">Under a year: both rates annualised from a short span.</span>}
      </>) },
    { key: "xirr", header: "Your XIRR", numeric: true, cell: (s) => rate(s.xirr) },
    { key: "fund", header: "Fund's NAV return", numeric: true, cell: (s) => rate(s.fund) },
    { key: "gap", header: "Gap", numeric: true, cell: (s) => pts(s.gap_pp) },
    ...(b.full ? [{ key: "gapr", header: "Gap in ₹", numeric: true, cell: (s: Row) => rupees(s.gap_rupees) }] : []),
  ];
  const table = (rows: Row[], label: string) => <DataTable label={label} columns={cols} rows={rows} rowKey={(s) => s.key} />;
  const fallCols: Column<FallRow>[] = [
    { key: "scheme", header: "Scheme", rowHeader: true, wrap: true, cell: (f) => <>{f.name}<span className="k-sub-line">{f.type === "switch_out" ? "Switch out" : "Redemption"} of {f.units} units</span></> },
    { key: "date", header: "Date", numeric: true, cell: (f) => dateOnly(f.date) },
    { key: "nav", header: "NAV, and the high", numeric: true, cell: (f) => <>{f.nav}<span className="k-sub-line">{f.fall_pct}% below {f.high} ({dateOnly(f.high_date)}){f.source === "statement" ? ", from your statement" : ""}</span></> },
    { key: "recv", header: "Received", numeric: true, cell: (f) => inr(f.received) },
    { key: "today", header: "Those units today", numeric: true, cell: (f) => <>{inr(f.worth_today)}<span className="k-sub-line">{rupees(f.difference)}</span></> },
  ];

  return (
    <Card label="Fund behaviour">
      <CardHead title="Your return against each fund's" info="Your XIRR counts when your money went in and came out. The fund's NAV return is what a rupee kept in it all along earned over the same dates. The gap is what timing did: what happened, not what to do next." />
      {b.full && (
        <StatRow>
          <Stat label={<>Gap in rupees, all funds <Info label="How the gap in rupees is worked out">Your value today and what you took out, less what the same purchases and redemptions would come to at each fund's own yearly NAV return. Positive: timing added to the fund's return. Negative: it took away.</Info></>}
            value={rupees(t.gap_rupees)} note={`${t.compared} of ${t.schemes} fund${t.schemes === 1 ? "" : "s"} compared`} />
          <Stat label="SIPs" value={t.sips ?? 0} note={`${t.sips_running ?? 0} running · ${t.sips_stopped ?? 0} stopped · ${t.months_missed ?? 0} month${t.months_missed === 1 ? "" : "s"} missed`} />
          <Stat label={`Redemptions after a ${b.fall_pct}% fall`} value={t.falls ?? 0} note={(t.falls ?? 0) > 0 ? `${inr(t.falls_received)} received · ${inr(t.falls_worth_today)} today` : undefined} />
          <Stat label="Redeemed units held, on average" value={span(t.avg_days_held)} note={t.held_under_year_pct != null ? `${t.held_under_year_pct.toFixed(0)}% for a year or less` : undefined} />
          <Stat label={`Today's value held over ${b.long_years} years`} value={t.long_share == null ? "–" : `${t.long_share.toFixed(0)}%`} note={t.long_value != null ? inr(t.long_value) : undefined} />
        </StatRow>
      )}
      {held.length > 0 && table(held, "Your return against each fund's")}
      <Earlier label="Funds you no longer hold" count={gone.length} className="in-card">{table(gone, "Funds you no longer hold")}</Earlier>

      {b.full && sips.length > 0 && (
        <div className="k-stack">
          <h3 className="k-sub">Your SIP record</h3>
          <ul className="k-list plain" aria-label="SIP record">
            {sips.map((s) => {
              const r = s.sip!;
              return (
                <li key={s.key} className="k-small">
                  <b>{s.name}</b>
                  <div className="k-note">
                    {month(r.first)} to {month(r.last)}: {r.months_paid} month{r.months_paid === 1 ? "" : "s"} paid, {r.months_missed} missed · longest unbroken run {r.longest_run} month{r.longest_run === 1 ? "" : "s"} ({month(r.longest_from)} to {month(r.longest_to)})
                    {r.stopped ? ` · no instalment after ${month(r.stopped_after!)}` : ` · running for ${r.current_run} month${r.current_run === 1 ? "" : "s"}`}
                  </div>
                  {r.missed.length > 0 && <div className="k-note">Missed: {r.missed.map(month).join(", ")}{r.months_missed > r.missed.length ? " and earlier" : ""}</div>}
                </li>
              );
            })}
          </ul>
          {b.last_txn && <p className="k-note">Counted up to your statement's latest transaction, {dateOnly(b.last_txn)}. Import a newer statement to bring it up to date.</p>}
        </div>
      )}

      {b.full && (
        <div className="k-stack">
          <h3 className="k-sub">Redemptions after a fall of {b.fall_pct}% or more</h3>
          {falls.length === 0
            ? <p className="k-note">None: no redemption or switch out came {b.fall_pct}% or more below the fund's high since your first purchase in it.</p>
            : <DataTable label="Redemptions after a fall" columns={fallCols} rows={falls} rowKey={(f) => String(f.i)} />}
          <p className="k-note">"Those units today" is hindsight arithmetic: the same units at today's NAV, known only afterwards.</p>
          {b.pending > 0 && <p className="k-note" role="status">Reading NAV history for {b.pending} fund{b.pending === 1 ? "" : "s"}; until it arrives, highs come from the NAVs in your statement.</p>}
        </div>
      )}

      {!b.full && <PlanNote>The gap in rupees, your SIP record, redemptions after a fall and how long you held are on the {b.plan} plan.</PlanNote>}
      {asOfText(b.as_of) && <p className="k-note">Worked out {asOfText(b.as_of)}.</p>}
      <Disclosure summary="How this is worked out">
        <ul className="k-list muted">{b.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <p className="k-note">{b.disclaimer}</p>
      </Disclosure>
    </Card>
  );
}
