import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import { asOf as asOfText, dateOnly, inr, pctPlain } from "../../lib/format";
import { Info } from "../../components/ui";
import { Card, CardHead, DataTable, Disclosure, EmptyState, PlanNote, Stat, StatRow, type Column } from "../../components/kit";

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
  state: "ok" | "reading" | "unavailable"; full: boolean; plan: string; schemes: Cost[]; unmatched: { key: string; name: string }[];
  total: { cost_year: number; value: number; weighted_ter: number | null; funds: number; held: number } | null;
  read_at: string | null; assumptions: string[]; disclaimer: string; as_of: string;
};

const ter = (v: number | null | undefined) => pctPlain(v, 2);
const PLAN: Record<string, string> = { direct: "Direct plan", regular: "Regular plan" };

export function FundCosts({ version }: { version: string }) {
  const [c, setC] = useState<Costs | null>(null);
  const [failed, setFailed] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    let live = true;
    api<Costs>("/money/mutual-funds/costs").then((r) => { if (live) { setC(r); setFailed(false); } }).catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [version, tick]);
  // the very first read of the TER disclosure runs in the background: look again every few seconds, for a while
  useEffect(() => {
    if (c?.state !== "reading" || tick >= 40) return;
    const t = window.setTimeout(() => setTick((n) => n + 1), 5000);
    return () => window.clearTimeout(t);
  }, [c, tick]);

  const note = (title: string, text: string, retry?: boolean) => (
    <Card label="Fund costs"><CardHead title="What your funds cost" />
      <EmptyState title={title} action={retry ? { label: "Try again", onClick: () => setTick((n) => n + 1) } : undefined}>{text}</EmptyState></Card>
  );
  if (failed) return note("Fund costs couldn't be loaded", "Fund costs couldn't be loaded just now. Reload the page to try again.", true);
  if (c?.state === "reading") return note("Reading each fund's costs", "Costs are being read; check back shortly.");
  if (c?.state === "unavailable") return note("Fund costs aren't available", "Fund costs aren't available right now. They are read again every few hours.");
  if (!c || !c.total) return null;
  const t = c.total;
  const cols: Column<Cost>[] = [
    { key: "scheme", header: "Scheme", rowHeader: true, wrap: true, cell: (s) => (
      <>
        <b>{s.name}</b>
        <span className="k-sub-line">{s.plan ? PLAN[s.plan] : "Plan not in the name"} · listed as {s.matched}{s.category ? ` · ${s.category}` : ""}</span>
        {(s.category_changes ?? []).map((g) => (
          <span key={g.date} className="k-sub-line">Category changed on {dateOnly(g.date)}{g.recat_2026 ? " (2026 recategorisation)" : ""}: was {g.from}.</span>
        ))}
        {s.parts && s.parts.length > 0 && (
          <Disclosure summary="Parts of the TER"><ul className="k-list muted">{s.parts.map((p) => <li key={p.key}>{p.label}: {ter(p.pct)}</li>)}</ul></Disclosure>
        )}
      </>) },
    { key: "ter", header: "TER", numeric: true, cell: (s) => ter(s.ter) },
    ...(c.full ? [
      { key: "year", header: "A year", numeric: true, cell: (s: Cost) => inr(s.cost_year) },
      { key: "direct", header: "Direct TER", numeric: true, cell: (s: Cost) => <>{ter(s.direct?.total)}{s.plan === "direct" && <span className="k-sub-line">yours</span>}</> },
      { key: "regular", header: "Regular TER", numeric: true, cell: (s: Cost) => <>{ter(s.regular?.total)}{s.plan === "regular" && <span className="k-sub-line">yours</span>}</> },
      { key: "gap", header: "Gap a year", numeric: true, cell: (s: Cost) => (s.gap_pp == null ? "–" : <>{inr(s.gap_year)}<span className="k-sub-line">{Math.abs(s.gap_pp).toFixed(2)} pts</span></>) },
    ] : []),
    { key: "since", header: c.full ? "Since you bought" : "As of", wrap: true, cell: (s) => (
      <>
        {!c.full && dateOnly(s.ter_date)}
        {c.full && (s.since ? (
          <>
            {ter(s.since.then)} to {ter(s.since.now)}{s.since.change_pp != null && s.since.change_pp !== 0 ? ` (${s.since.change_pp > 0 ? "+" : "−"}${Math.abs(s.since.change_pp).toFixed(2)} pts)` : ", no change"}
            <span className="k-sub-line">{s.since.history_starts_late ? `History starts ${dateOnly(s.since.from)}; your first units held were bought ${dateOnly(s.since.first_buy)}` : `From ${dateOnly(s.since.first_buy)}`} · {s.since.count} change{s.since.count === 1 ? "" : "s"}</span>
          </>
        ) : <span className="k-muted">No history yet</span>)}
        {c.full && <span className="k-sub-line">TER as of {dateOnly(s.ter_date)}</span>}
      </>) },
  ];
  return (
    <Card label="Fund costs">
      <CardHead title="What your funds cost" info="Each fund's total expense ratio (TER) as published, and what it comes to in rupees a year on your current value." />
      <StatRow>
        <Stat label={<>Expense ratios, a year <Info label="How the yearly cost is worked out">Each fund's current value times its plan's TER, added up. The TER is taken out of the fund a little each day, so the NAV and your value are already after it.</Info></>}
          value={inr(t.cost_year)} note={`on ${inr(t.value)} in ${t.funds} fund${t.funds === 1 ? "" : "s"}`} />
        <Stat label="Average TER, by value" value={ter(t.weighted_ter)} />
      </StatRow>
      {c.schemes.length > 0 && <DataTable label="Fund costs" columns={cols} rows={c.schemes} rowKey={(s) => s.key} />}
      {c.full && <p className="k-note">Every scheme has a direct and a regular plan with their own TER. The gap is the regular plan's TER less the direct plan's, as a yearly amount on your current value in this scheme.</p>}
      {c.unmatched.length > 0 && <p className="k-note">Not found in the TER disclosure yet: {c.unmatched.map((u) => u.name).join(", ")}.</p>}
      {!c.full && <PlanNote>Each TER's parts, the rupees per fund, both plans side by side, TER changes since you bought and category changes are on the {c.plan} plan.</PlanNote>}
      {c.read_at && <p className="k-note">TERs read {asOfText(c.read_at)}.</p>}
      <Disclosure summary="How fund costs are worked out">
        <ul className="k-list muted">{c.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
        <p className="k-note">{c.disclaimer} As of {dateOnly(c.as_of)}.</p>
      </Disclosure>
    </Card>
  );
}
