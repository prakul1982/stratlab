import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { dateOnly, money } from "../../lib/format";
import { AsOf, Info } from "../../components/ui";
import { Earlier } from "../../components/Earlier";

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

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const rate = (v: number | null | undefined) => (v == null ? "–" : `${(v * 100).toFixed(1)}%`);
const pts = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts`);
const signed = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : ""}${inr(v)}`);
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
    <section className="card stack" style={{ gap: 6 }} aria-label="Fund behaviour"><h2 className="h2">Your return against each fund's</h2>
      <p className="small muted" style={{ margin: 0 }} role="status">This couldn't be loaded just now. Reload the page to try again.</p></section>
  );
  if (!b || !b.total || !b.schemes.length) return null;
  const t = b.total;
  const held = b.schemes.filter((s) => s.held), gone = b.schemes.filter((s) => !s.held);
  const sips = b.schemes.filter((s) => s.sip);
  const falls = b.schemes.flatMap((s) => (s.falls ?? []).map((f) => ({ ...f, name: s.name, source: s.high_source })));

  const table = (rows: Row[], label: string) => (
    <div className="table-wrap">
      <table aria-label={label}>
        <thead><tr><th style={{ textAlign: "left" }}>Scheme</th><th>Your XIRR</th><th>Fund's NAV return</th><th>Gap</th>{b.full && <th>Gap in ₹</th>}</tr></thead>
        <tbody>{rows.map((s) => (
          <tr key={s.key}>
            <td style={{ textAlign: "left", minWidth: 200, whiteSpace: "normal" }}>
              <b>{s.name}</b>
              <div className="tiny muted">{s.from ? `${dateOnly(s.from)} to ${s.held ? "today" : dateOnly(s.to)}` : "No dated purchase in the statement"}
                {s.start_nav != null && s.end_nav != null ? ` · NAV ${s.start_nav} to ${s.end_nav}` : ""}</div>
              {s.idcw && <div className="tiny muted">IDCW option: the NAV return leaves out payouts; your XIRR counts them.</div>}
              {s.short_span && <div className="tiny muted">Under a year: both rates annualised from a short span.</div>}
            </td>
            <td className="num">{rate(s.xirr)}</td>
            <td className="num">{rate(s.fund)}</td>
            <td className="num">{pts(s.gap_pp)}</td>
            {b.full && <td className="num">{signed(s.gap_rupees)}</td>}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );

  return (
    <section className="card stack" style={{ gap: 12 }} aria-label="Fund behaviour">
      <div className="stack" style={{ gap: 4 }}>
        <h2 className="h2">Your return against each fund's</h2>
        <p className="small muted" style={{ margin: 0 }}>Your XIRR counts when your money went in and came out. The fund's NAV return is what a rupee kept in it all along earned over the same dates. The gap is what timing did: what happened, not what to do next.</p>
      </div>
      {b.full && (
        <div className="stat-row">
          <div className="stat"><span className="tiny muted">Gap in rupees, all funds <Info label="How the gap in rupees is worked out">Your value today and what you took out, less what the same purchases and redemptions would come to at each fund's own yearly NAV return. Positive: timing added to the fund's return. Negative: it took away.</Info></span><b className="num">{signed(t.gap_rupees)}</b><span className="tiny muted">{t.compared} of {t.schemes} fund{t.schemes === 1 ? "" : "s"} compared</span></div>
          <div className="stat"><span className="tiny muted">SIPs</span><b className="num">{t.sips ?? 0}</b><span className="tiny muted">{t.sips_running ?? 0} running · {t.sips_stopped ?? 0} stopped · {t.months_missed ?? 0} month{t.months_missed === 1 ? "" : "s"} missed</span></div>
          <div className="stat"><span className="tiny muted">Redemptions after a {b.fall_pct}% fall</span><b className="num">{t.falls ?? 0}</b>{(t.falls ?? 0) > 0 && <span className="tiny muted">{inr(t.falls_received)} received · {inr(t.falls_worth_today)} today</span>}</div>
          <div className="stat"><span className="tiny muted">Redeemed units held, on average</span><b className="num">{span(t.avg_days_held)}</b>{t.held_under_year_pct != null && <span className="tiny muted">{t.held_under_year_pct.toFixed(0)}% for a year or less</span>}</div>
          <div className="stat"><span className="tiny muted">Today's value held over {b.long_years} years</span><b className="num">{t.long_share == null ? "–" : `${t.long_share.toFixed(0)}%`}</b>{t.long_value != null && <span className="tiny muted">{inr(t.long_value)}</span>}</div>
        </div>
      )}
      {held.length > 0 && table(held, "Your return against each fund's")}
      <Earlier label="Funds you no longer hold" count={gone.length} className="in-card">{table(gone, "Funds you no longer hold")}</Earlier>

      {b.full && sips.length > 0 && (
        <div className="stack" style={{ gap: 6 }}>
          <h3 className="h3" style={{ margin: 0 }}>Your SIP record</h3>
          <ul className="stack" style={{ gap: 6, margin: 0, paddingLeft: 0, listStyle: "none" }} aria-label="SIP record">
            {sips.map((s) => {
              const r = s.sip!;
              return (
                <li key={s.key} className="small">
                  <b>{s.name}</b>
                  <div className="tiny muted">
                    {month(r.first)} to {month(r.last)}: {r.months_paid} month{r.months_paid === 1 ? "" : "s"} paid, {r.months_missed} missed · longest unbroken run {r.longest_run} month{r.longest_run === 1 ? "" : "s"} ({month(r.longest_from)} to {month(r.longest_to)})
                    {r.stopped ? ` · no instalment after ${month(r.stopped_after!)}` : ` · running for ${r.current_run} month${r.current_run === 1 ? "" : "s"}`}
                  </div>
                  {r.missed.length > 0 && <div className="tiny muted">Missed: {r.missed.map(month).join(", ")}{r.months_missed > r.missed.length ? " and earlier" : ""}</div>}
                </li>
              );
            })}
          </ul>
          {b.last_txn && <p className="tiny muted" style={{ margin: 0 }}>Counted up to your statement's latest transaction, {dateOnly(b.last_txn)}. Import a newer statement to bring it up to date.</p>}
        </div>
      )}

      {b.full && (
        <div className="stack" style={{ gap: 6 }}>
          <h3 className="h3" style={{ margin: 0 }}>Redemptions after a fall of {b.fall_pct}% or more</h3>
          {falls.length === 0
            ? <p className="tiny muted" style={{ margin: 0 }}>None: no redemption or switch out came {b.fall_pct}% or more below the fund's high since your first purchase in it.</p>
            : (
              <div className="table-wrap">
                <table aria-label="Redemptions after a fall">
                  <thead><tr><th style={{ textAlign: "left" }}>Scheme</th><th>Date</th><th>NAV, and the high</th><th>Received</th><th>Those units today</th></tr></thead>
                  <tbody>{falls.map((f, i) => (
                    <tr key={`${f.date}-${i}`}>
                      <td style={{ textAlign: "left", minWidth: 180, whiteSpace: "normal" }}>{f.name}<div className="tiny muted">{f.type === "switch_out" ? "Switch out" : "Redemption"} of {f.units} units</div></td>
                      <td className="num">{dateOnly(f.date)}</td>
                      <td className="num">{f.nav}<div className="tiny muted">{f.fall_pct}% below {f.high} ({dateOnly(f.high_date)}){f.source === "statement" ? ", from your statement" : ""}</div></td>
                      <td className="num">{inr(f.received)}</td>
                      <td className="num">{inr(f.worth_today)}<div className="tiny muted">{signed(f.difference)}</div></td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          <p className="tiny muted" style={{ margin: 0 }}>"Those units today" is hindsight arithmetic: the same units at today's NAV, known only afterwards.</p>
          {b.pending > 0 && <p className="tiny muted" style={{ margin: 0 }} role="status">Reading NAV history for {b.pending} fund{b.pending === 1 ? "" : "s"}; until it arrives, highs come from the NAVs in your statement.</p>}
        </div>
      )}

      {!b.full && (
        <div className="banner"><span>The gap in rupees, your SIP record, redemptions after a fall and how long you held are on the {b.plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>
      )}
      <AsOf parts={[["Worked out", b.as_of]]} />
      <details className="small">
        <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>How this is worked out</summary>
        <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{b.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <p className="tiny muted" style={{ margin: "6px 0 0" }}>{b.disclaimer}</p>
      </details>
    </section>
  );
}
