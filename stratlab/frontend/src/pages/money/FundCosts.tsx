import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { asOf as asOfText, dateOnly, inr, pctPlain } from "../../lib/format";
import { Info } from "../../components/ui";
import { Disclosure, EmptyState, FigureTable, Notes, PlanNote, type Figure } from "../../components/kit";

// What each fund held costs a year: its expense ratio (TER) and its parts, the rupees on the current value, both plans
// side by side, the TER since the first units still held were bought, and category changes. Facts only. The page says each
// scheme once (MF-1, RC2B-047): the totals are one block (CostStats, CostNotes), and a scheme's own costs are folded under its row
// (CostDetail), both read from the one load (useFundCosts).
export type Side = { total: number | null; parts: { key: string; label: string; pct: number }[] };
export type Cost = {
  key: string; name: string; matched: string; plan: "direct" | "regular" | null; value: number | null; ter_date: string; ter: number | null; full: boolean;
  parts?: Side["parts"]; cost_year?: number | null; regular?: Side | null; direct?: Side | null; other_plan?: "direct" | "regular" | null;
  gap_pp?: number | null; gap_year?: number | null; other_cost_year?: number | null;
  since?: { first_buy: string; from: string; history_starts_late: boolean; then: number; now: number | null; change_pp: number | null; changes: { date: string; ter: number }[]; count: number } | null;
  category?: string; category_changes?: { date: string; from: string; to: string; recat_2026: boolean }[];
};
export type Costs = {
  state: "ok" | "reading" | "unavailable"; full: boolean; plan: string; schemes: Cost[]; unmatched: { key: string; name: string }[];
  total: { cost_year: number; value: number; weighted_ter: number | null; funds: number; held: number } | null;
  read_at: string | null; assumptions: string[]; disclaimer: string; as_of: string;
};

export const ter = (v: number | null | undefined) => pctPlain(v, 2);
const PLAN: Record<string, string> = { direct: "Direct plan", regular: "Regular plan" };

export type CostsQuery = { c: Costs | null; failed: boolean; retry: () => void };

export function useFundCosts(version: string, on: boolean): CostsQuery {
  const [c, setC] = useState<Costs | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!on) return;
    let live = true;
    api<Costs>("/money/mutual-funds/costs").then((r) => { if (live) { setC(r); setFailed(false); } }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [version, tick, on]);
  // the very first read of the TER disclosure runs in the background: look again every few seconds, for a while
  useEffect(() => {
    if (c?.state !== "reading" || tick >= 40) return;
    const t = window.setTimeout(() => setTick((n) => n + 1), 5000);
    return () => window.clearTimeout(t);
  }, [c, tick]);
  return { c, failed, retry: () => setTick((n) => n + 1) };
}

/** What the cost block has to show: its totals, or why not. */
export const costsShown = (q: CostsQuery) => q.failed || (!!q.c && (q.c.state !== "ok" || !!q.c.total));

/** One scheme's cost, by its key (none when the disclosure has no TER for it). */
export const costOf = (q: CostsQuery, key: string): Cost | undefined => q.c?.schemes.find((s) => s.key === key);

/** Whether the yearly cost totals have anything to say: a total over no fund ("₹0 on ₹0 in 0 funds", an average of "–") is left out (LIVE1B-017). */
export const costStatsShown = (q: CostsQuery) => q.c?.state === "ok" && !!q.c.total && q.c.total.funds > 0;

/** The yearly totals over every fund, as rows of the page's one table of totals (TABLE-SWEEP; none until the costs are read). */
export function costFigures(q: CostsQuery): Figure[] {
  const t = costStatsShown(q) && q.c?.state === "ok" ? q.c.total : null;
  if (!t) return [];
  return [
    { key: "ter-year", label: <>Expense ratios, a year <Info label="How the yearly cost is worked out">Each fund's current value times its plan's TER, added up. The TER is taken out of the fund a little each day, so the NAV and your value are already after it.</Info></>,
      value: inr(t.cost_year), note: `On ${inr(t.value)} in ${t.funds} fund${t.funds === 1 ? "" : "s"}` },
    { key: "ter-avg", label: "Average TER, by value", value: ter(t.weighted_ter) },
  ];
}

/** What the costs need said under their stats: why there are none yet, the funds left out, what the plan keeps back. */
export function CostNotes({ q }: { q: CostsQuery }) {
  const { c, failed, retry } = q;
  if (failed) return <EmptyState title="Fund costs couldn't be loaded" action={{ label: "Try again", onClick: retry }}>Fund costs couldn't be read just now.</EmptyState>;
  if (c?.state === "reading") return <EmptyState title="Reading each fund's costs">Costs are being read; check back shortly.</EmptyState>;
  if (c?.state === "unavailable") return <EmptyState title="Fund costs aren't available">Fund costs aren't available right now. They are read again every few hours.</EmptyState>;
  if (!c || !c.total) return null;
  return (
    <>
      {c.unmatched.length > 0 && <p className="k-note">{c.unmatched.length} fund{c.unmatched.length === 1 ? " is" : "s are"} not in the TER disclosure yet, so {c.unmatched.length === 1 ? "it is" : "they are"} left out of the costs.</p>}
      {!c.full && <PlanNote>Each TER's parts, the rupees per fund, both plans side by side, TER changes since you bought and category changes are on the {c.plan} plan.</PlanNote>}
    </>
  );
}

/** How the costs are worked out, for the page's one fold of method. */
export function CostHow({ q }: { q: CostsQuery }) {
  const { c } = q;
  if (!c || !c.total) return null;
  return (
    <>
      <Notes label="How the costs are worked out" items={[
        c.full && "Every scheme has a direct and a regular plan with their own TER. The gap is the regular plan's TER less the direct plan's, as a yearly amount on your current value in the scheme.",
        ...c.assumptions,
      ]} />
      <p className="k-note">{c.read_at ? `TERs read ${asOfText(c.read_at)}. ` : ""}{c.disclaimer} As of {dateOnly(c.as_of)}.</p>
    </>
  );
}

/** A scheme's TER and, on the plans that have it, what that is in rupees a year (the two figures its row shows). */
export function CostCell({ q, id }: { q: CostsQuery; id: string }) {
  const s = costOf(q, id);
  if (!q.c || !s) return <span className="k-none">–</span>;
  return <>{ter(s.ter)}{q.c.full && s.cost_year != null && <span className="k-sub-line">{inr(s.cost_year)} a year</span>}</>;
}

/** The rest of one scheme's costs, in its folded detail: the plan, both plans side by side, the TER since it was bought, category changes. */
export function CostDetail({ q, id, name }: { q: CostsQuery; id: string; name?: string }) {
  const { c } = q;
  const s = costOf(q, id);
  if (!c || c.state !== "ok") return null;
  if (!s) return c.unmatched.some((u) => u.key === id) ? <section><h3>What it costs</h3><p className="k-note">Not in the TER disclosure yet.</p></section> : null;
  const sinceLine = s.since ? (
    <>
      {s.since.change_pp != null && s.since.change_pp !== 0 ? `${s.since.change_pp > 0 ? "+" : "−"}${Math.abs(s.since.change_pp).toFixed(2)} pts` : "No change"} · {s.since.count} change{s.since.count === 1 ? "" : "s"}
      <span className="k-sub-line">{s.since.history_starts_late ? `History starts ${dateOnly(s.since.from)}; your first units held were bought ${dateOnly(s.since.first_buy)}` : `From ${dateOnly(s.since.first_buy)}`}</span>
    </>
  ) : "No history yet";
  return (
    <section aria-label={name ? `What it costs, ${name}` : "What it costs"}>
      <h3>What it costs</h3>
      {/* TABLE-SWEEP (owner, 29 Oct): the plan in words, then its TERs and the gap as a table (they were five tiles and a sentence) */}
      <p className="k-small">{s.plan ? PLAN[s.plan] : "Plan not in the name"}, listed as {s.matched}.</p>
      <FigureTable label={name ? `What ${name} costs` : "What it costs"} header="Cost" valueHeader="Figure" noteHeader="Detail" rows={[
        { key: "ter", label: `TER as of ${dateOnly(s.ter_date)}`, value: ter(s.ter) },
        ...(c.full ? [
          { key: "direct", label: "Direct plan TER", value: ter(s.direct?.total), note: s.plan === "direct" ? "Yours" : undefined },
          { key: "regular", label: "Regular plan TER", value: ter(s.regular?.total), note: s.plan === "regular" ? "Yours" : undefined },
          { key: "gap", label: "Gap a year", value: s.gap_pp == null ? "–" : inr(s.gap_year), note: s.gap_pp == null ? undefined : `${Math.abs(s.gap_pp).toFixed(2)} pts` },
          { key: "since", label: "TER since you bought", value: s.since ? <span className="nowrap">{ter(s.since.then)} → {ter(s.since.now)}</span> : "–", note: sinceLine },
        ] : []),
      ]} />
      {(s.category_changes ?? []).map((g) => (
        <p key={g.date} className="k-note">Category changed on {dateOnly(g.date)}{g.recat_2026 ? " (2026 recategorisation)" : ""}: was {g.from}.</p>
      ))}
      {s.parts && s.parts.length > 0 && (
        <Disclosure summary="Parts of the TER"><FigureTable label="Parts of the TER" header="Part" valueHeader="TER" noteHeader={null} rows={s.parts.map((p) => ({ key: p.key, label: p.label, value: ter(p.pct) }))} /></Disclosure>
      )}
    </section>
  );
}
