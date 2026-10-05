import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { dateOnly, money } from "../../lib/format";
import { AsOf, Info } from "../../components/ui";
import { Earlier } from "../../components/Earlier";

/* Floating-rate loan check, under the loans in Net worth: is each floating loan's rate following its benchmark? For a
 * repo-linked loan, the rate expected after the last reset beside the rate on the user's statement, with any gap; for
 * every floating loan, what each rate change did to the EMI or the tenure. Arithmetic on the user's own loan. */

type Change = { date: string; from: number; to: number; repo: number | null; balance: number; emi_before: number; new_emi: number; emi_change: number;
  months_before: number; months_if_same_emi: number | null; months_change: number | null; interest_before: number | null;
  interest_if_same_emi: number | null; interest_if_new_emi: number };
type Check = {
  id: string; name: string; benchmark: string; benchmark_label: string; rate: number; current_rate: number | null; reset_months: number | null; ready: boolean;
  why?: string; spread?: number | null; spread_inferred?: boolean; expected?: number | null; last_reset?: string | null; next_reset?: string;
  repo_at_reset?: number | null; changes: Change[]; outstanding?: number; emis_paid?: number; left?: number;
  gap: { pts: number; rupees_year: number; matches: boolean; after: string | null } | null;
};
type Reply = {
  full: boolean; plan: string; loans: number; floating: number; checks: Check[];
  repo: { now: number | null; history: { date: string; rate: number }[]; read_at: string | null };
  draft: { title: string; status: string; points: string[] }; raise: string[]; notes: string[]; disclaimer: string; as_of: string;
};

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const pct = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(2)}%`);
const signedInr = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${inr(Math.abs(v))}`;
const months = (n: number | null) => (n == null ? "never repaid at this EMI" : `${n > 0 ? n : -n} month${Math.abs(n) === 1 ? "" : "s"} ${n > 0 ? "more" : "fewer"}`);

function ChangeRow({ c }: { c: Change }) {
  return (
    <li className="small">
      <b>{dateOnly(c.date)}: {pct(c.from)} to {pct(c.to)}</b>{c.repo != null && <span className="tiny muted"> · repo {pct(c.repo)}</span>}
      <div className="tiny muted">On {inr(c.balance)} owed: a new EMI of {inr(c.new_emi)} ({signedInr(c.emi_change)} a month) for the same months, interest left {inr(c.interest_if_new_emi)};
        {" "}or the same EMI of {inr(c.emi_before)} for {c.months_change === 0 ? "the same months" : months(c.months_change)}
        {c.interest_if_same_emi != null ? `, interest left ${inr(c.interest_if_same_emi)}` : ""}. Before the change: {inr(c.interest_before)} of interest left.</div>
    </li>
  );
}

export function LoanCheck({ version }: { version: string }) {
  const [d, setD] = useState<Reply | null>(null);
  useEffect(() => {
    let live = true;
    api<Reply>("/money/loans/check").then((r) => { if (live) setD(r); }).catch(() => undefined);
    return () => { live = false; };
  }, [version]);
  if (!d) return null;

  return (
    <section className="card stack" style={{ gap: 12 }} aria-label="Floating-rate loan check">
      <div className="stack" style={{ gap: 4 }}>
        <h2 className="h2">Is your rate following its benchmark?</h2>
        <p className="small muted" style={{ margin: 0 }}>For floating-rate loans: the rate expected after each reset, beside the rate on your statement, and what each change did. The repo rate is {pct(d.repo.now)}.</p>
      </div>
      {d.floating === 0 && <p className="small" style={{ margin: 0 }}>None of your loans is marked floating. Edit a loan and pick its rate type (repo-linked, T-bill-linked, MCLR or another rate) to check it.</p>}
      {!d.full && d.floating > 0 && <div className="banner"><span>The check of your floating-rate loans against their benchmark is on the {d.plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>}
      {d.checks.map((c) => (
        <article key={c.id} className="stack" style={{ gap: 6, borderTop: "1px solid var(--line)", paddingTop: 10 }} aria-label={c.name}>
          <div className="spread" style={{ flexWrap: "wrap", gap: 6 }}><b>{c.name}</b><span className="tiny muted">{c.benchmark_label}{c.reset_months ? `, resets every ${c.reset_months === 1 ? "month" : `${c.reset_months} months`}` : ""}</span></div>
          {!c.ready ? <p className="small muted" style={{ margin: 0 }}>{c.why}</p> : <>
            {c.benchmark === "repo" && (
              <div className="stat-row">
                <div className="stat"><span className="tiny muted">Expected now <Info label="How the expected rate is worked out">The repo rate in force on the last reset ({c.last_reset ? dateOnly(c.last_reset) : "the start"}: {pct(c.repo_at_reset)}) plus your spread of {c.spread?.toFixed(2)} points{c.spread_inferred ? ", worked out as the sanctioned rate less the repo rate when the loan started" : ""}.</Info></span><b className="num">{pct(c.expected)}</b><span className="tiny muted">repo {pct(c.repo_at_reset)} + {c.spread?.toFixed(2)}</span></div>
                <div className="stat"><span className="tiny muted">On your statement</span><b className="num">{pct(c.current_rate)}</b>{c.current_rate == null && <span className="tiny muted">Edit the loan to enter it</span>}</div>
                {c.gap && <div className="stat"><span className="tiny muted">Difference</span><b className="num">{c.gap.matches ? "None" : `${c.gap.pts > 0 ? "+" : "−"}${Math.abs(c.gap.pts).toFixed(2)} pts`}</b>{!c.gap.matches && <span className="tiny muted">{inr(Math.abs(c.gap.rupees_year))} a year on {inr(c.outstanding)}</span>}</div>}
              </div>
            )}
            {c.gap && !c.gap.matches && (
              <p className="small" style={{ margin: 0 }} role="status">Your entered rate is {Math.abs(c.gap.pts).toFixed(2)}% {c.gap.pts > 0 ? "above" : "below"} repo + spread{c.gap.after ? ` after the ${dateOnly(c.gap.after)} reset` : ""}.</p>
            )}
            {c.benchmark !== "repo" && <p className="small muted" style={{ margin: 0 }}>The lender sets this benchmark itself, so it isn't checked here; the change from the sanctioned {pct(c.rate)} to your statement's {pct(c.current_rate)} is worked out below.</p>}
            {c.changes.length > 0 ? (() => {
              const recent = c.changes.slice(-2), older = c.changes.slice(0, -2);
              return <>
                <ul className="stack" style={{ gap: 6, margin: 0, paddingLeft: 18 }} aria-label={`Rate changes on ${c.name}`}>{recent.map((x) => <ChangeRow key={x.date} c={x} />)}</ul>
                <Earlier label="Earlier rate changes" count={older.length} className="in-card"><ul className="stack" style={{ gap: 6, margin: 0, paddingLeft: 18 }}>{older.map((x) => <ChangeRow key={x.date} c={x} />)}</ul></Earlier>
              </>;
            })() : <p className="tiny muted" style={{ margin: 0 }}>No rate change since the loan started.</p>}
            {c.next_reset && <p className="tiny muted" style={{ margin: 0 }}>Next reset: {dateOnly(c.next_reset)} (in your money calendar).</p>}
          </>}
        </article>
      ))}
      <details className="small">
        <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>Draft: what the Reserve Bank's 2026 loan pricing rules propose</summary>
        <p className="tiny" style={{ margin: "6px 0 0" }}><b>{d.draft.title}.</b> {d.draft.status}</p>
        <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{d.draft.points.map((p, i) => <li key={i}>{p}</li>)}</ul>
      </details>
      <details className="small">
        <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>Where a difference can be raised, and how this is worked out</summary>
        <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{d.raise.map((p, i) => <li key={`r${i}`}>{p}</li>)}{d.notes.map((p, i) => <li key={`n${i}`}>{p}</li>)}</ul>
        <p className="tiny muted" style={{ margin: "6px 0 0" }}>{d.disclaimer}</p>
      </details>
      <AsOf parts={[["Repo rate read", d.repo.read_at]]} />
    </section>
  );
}
