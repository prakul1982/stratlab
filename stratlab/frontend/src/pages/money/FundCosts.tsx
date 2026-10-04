import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { dateOnly, money } from "../../lib/format";
import { AsOf, Info } from "../../components/ui";

// What each fund held costs a year: its expense ratio (TER) and its parts, the rupees on the current value, both plans
// side by side, the TER since the first units still held were bought, and category changes. Facts only.
type Side = { total: number | null; parts: { key: string; label: string; pct: number }[] };
type Cost = {
  key: string; name: string; matched: string; plan: "direct" | "regular" | null; value: number | null; ter_date: string; ter: number | null; full: boolean;
  parts?: Side["parts"]; cost_year?: number | null; regular?: Side | null; direct?: Side | null; other_plan?: "direct" | "regular" | null;
  gap_pp?: number | null; gap_year?: number | null; other_cost_year?: number | null;
  since?: { first_buy: string; from: string; history_starts_late: boolean; then: number; now: number | null; change_pp: number | null; changes: { date: string; ter: number }[]; count: number } | null;
  category?: string; category_changes?: { date: string; from: string; to: string; recat_2026: boolean }[];
};
type Costs = {
  full: boolean; plan: string; schemes: Cost[]; unmatched: { key: string; name: string }[];
  total: { cost_year: number; value: number; weighted_ter: number | null; funds: number; held: number } | null;
  read_at: string | null; assumptions: string[]; disclaimer: string; as_of: string;
};

const inr = (v: number | null | undefined) => money(v, "INR", 0);
const ter = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(2)}%`);
const PLAN: Record<string, string> = { direct: "Direct plan", regular: "Regular plan" };

export function FundCosts({ version }: { version: string }) {
  const [c, setC] = useState<Costs | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let live = true;
    api<Costs>("/money/mutual-funds/costs").then((r) => { if (live) { setC(r); setFailed(false); } }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [version]);

  if (failed) return <section className="card" aria-label="Fund costs"><p className="small muted" style={{ margin: 0 }}>Fund costs couldn't be loaded just now. Reload the page to try again.</p></section>;
  if (!c || !c.total) return null;
  const t = c.total;
  return (
    <section className="card stack" style={{ gap: 12 }} aria-label="Fund costs">
      <div className="stack" style={{ gap: 4 }}>
        <h2 className="h2">What your funds cost</h2>
        <p className="small muted" style={{ margin: 0 }}>Each fund's total expense ratio (TER) as published, and what it comes to in rupees a year on your current value.</p>
      </div>
      <div className="stat-row">
        <div className="stat"><span className="tiny muted">Expense ratios, a year <Info label="How the yearly cost is worked out">Each fund's current value times its plan's TER, added up. The TER is taken out of the fund a little each day, so the NAV and your value are already after it.</Info></span><b className="num">{inr(t.cost_year)}</b><span className="tiny muted">on {inr(t.value)} in {t.funds} fund{t.funds === 1 ? "" : "s"}</span></div>
        <div className="stat"><span className="tiny muted">Average TER, by value</span><b className="num">{ter(t.weighted_ter)}</b></div>
      </div>
      {c.schemes.length > 0 && (
        <div className="table-wrap">
          <table aria-label="Fund costs">
            <thead><tr><th style={{ textAlign: "left" }}>Scheme</th><th>TER</th>{c.full && <><th>A year</th><th>Direct TER</th><th>Regular TER</th><th>Gap a year</th></>}<th style={{ textAlign: "left" }}>{c.full ? "Since you bought" : "As of"}</th></tr></thead>
            <tbody>{c.schemes.map((s) => (
              <tr key={s.key}>
                <td style={{ textAlign: "left", minWidth: 220, whiteSpace: "normal" }}>
                  <b>{s.name}</b>
                  <div className="tiny muted">{s.plan ? PLAN[s.plan] : "Plan not in the name"} · listed as {s.matched}{s.category ? ` · ${s.category}` : ""}</div>
                  {(s.category_changes ?? []).map((g) => (
                    <div key={g.date} className="tiny">Category changed on {dateOnly(g.date)}{g.recat_2026 ? " (2026 recategorisation)" : ""}: was {g.from}.</div>
                  ))}
                  {s.parts && s.parts.length > 0 && (
                    <details className="tiny">
                      <summary style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>Parts of the TER</summary>
                      <ul className="muted" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                        {s.parts.map((p) => <li key={p.key}>{p.label}: {ter(p.pct)}</li>)}
                      </ul>
                    </details>
                  )}
                </td>
                <td className="num">{ter(s.ter)}</td>
                {c.full && <>
                  <td className="num">{inr(s.cost_year)}</td>
                  <td className="num">{ter(s.direct?.total)}{s.plan === "direct" && <div className="tiny muted">yours</div>}</td>
                  <td className="num">{ter(s.regular?.total)}{s.plan === "regular" && <div className="tiny muted">yours</div>}</td>
                  <td className="num">{s.gap_pp == null ? "–" : <>{inr(s.gap_year)}<div className="tiny muted">{Math.abs(s.gap_pp).toFixed(2)} pts</div></>}</td>
                </>}
                <td style={{ textAlign: "left", minWidth: 180, whiteSpace: "normal" }} className="tiny">
                  {!c.full && dateOnly(s.ter_date)}
                  {c.full && (s.since ? (
                    <>
                      {ter(s.since.then)} to {ter(s.since.now)}{s.since.change_pp != null && s.since.change_pp !== 0 ? ` (${s.since.change_pp > 0 ? "+" : "−"}${Math.abs(s.since.change_pp).toFixed(2)} pts)` : ", no change"}
                      <div className="muted">{s.since.history_starts_late ? `History starts ${dateOnly(s.since.from)}; your first units held were bought ${dateOnly(s.since.first_buy)}` : `From ${dateOnly(s.since.first_buy)}`} · {s.since.count} change{s.since.count === 1 ? "" : "s"}</div>
                    </>
                  ) : <span className="muted">No history yet</span>)}
                  {c.full && <div className="muted">TER as of {dateOnly(s.ter_date)}</div>}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
      {c.full && <p className="tiny muted" style={{ margin: 0 }}>Every scheme has a direct and a regular plan with their own TER. The gap is the regular plan's TER less the direct plan's, as a yearly amount on your current value in this scheme.</p>}
      {c.unmatched.length > 0 && <p className="tiny muted" style={{ margin: 0 }}>Not found in the TER disclosure yet: {c.unmatched.map((u) => u.name).join(", ")}.</p>}
      {!c.full && (
        <div className="banner"><span>Each TER's parts, the rupees per fund, both plans side by side, TER changes since you bought and category changes are on the {c.plan} plan.</span><Link to="/plans" className="btn sm">See plans</Link></div>
      )}
      <AsOf parts={[["TERs read", c.read_at]]} />
      <details className="small">
        <summary className="tiny" style={{ minHeight: 32, display: "flex", alignItems: "center", cursor: "pointer" }}>How fund costs are worked out</summary>
        <ul className="tiny muted" style={{ margin: "6px 0 0", paddingLeft: 18 }}>{c.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <p className="tiny muted" style={{ margin: "6px 0 0" }}>{c.disclaimer} As of {dateOnly(c.as_of)}.</p>
      </details>
    </section>
  );
}
