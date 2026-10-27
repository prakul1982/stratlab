import { Card, CardHead } from "./kit/Card";
import { DataTable, type Column } from "./kit/DataTable";
import { Disclosure } from "./kit/Disclosure";
import type { ReactNode } from "react";
import { Info } from "./ui";
import { EVERYONE, FLAG_GROUP, FLAG_GROUPS, FLAGS, LIMITS, NUMBERS, unlimitedLabel, type Limits, type PlanId } from "../lib/plans";

/** Every limit and feature side by side, from the server's plans when signed in; signed out, the
 * same tables from the app's own copy of the limits (R60-012: a visitor comparing plans saw less than a signed-in user). */
export function PlanCompare({ plans }: { plans?: Record<string, Partial<Limits>> }) {
  const lim = (p: PlanId): Limits => ({ ...LIMITS[p], ...(plans?.[p] ?? {}) });
  const num = (p: PlanId, k: keyof Limits) => {
    const v = lim(p)[k] as number | null;
    // Free's one session is a trial of 5 market days: said as a trial in the cell (DK-005)
    return v == null ? unlimitedLabel(p, k) : p === "free" && k === "live_limit" ? `${v} (5-market-day trial)` : v.toLocaleString("en-IN");
  };
  const ids: PlanId[] = ["free", "basic", "pro"];
  const names = { free: "Free", basic: "Basic", pro: "Pro" };
  type Row = { id: string; label: string; cell: (p: PlanId) => string };
  // VR1-163: a value's own note ("Unlimited (up to 200 a day)", "1 (5-market-day trial)") is a line under it, not four lines in a 55px column; a long note on a row's name sits behind an (i)
  const valueOf = (v: string): ReactNode => { const m = /^(.+?) (\(.+\))$/.exec(v); return m ? <>{m[1]} <span className="k-sub-line">{m[2]}</span></> : v; };
  const nameOf = (v: string): ReactNode => { const m = /^(.+?) \((.{20,})\)$/.exec(v); return m ? <>{m[1]}<Info label={`About ${m[1].toLowerCase()}`}>{m[2].charAt(0).toUpperCase() + m[2].slice(1)}.</Info></> : v; };
  // "What each plan adds" in three parts under subheadings (DI-032: 40-odd rows mixing trading, research and money)
  const flagRows = (g: string) => FLAGS.filter(([f]) => (FLAG_GROUP[f] ?? "research") === g)
    .map(([f, label]) => ({ id: String(f), label, cell: (p: PlanId) => (lim(p).features.includes(f) ? "✓" : "–") }));
  const groups: { id: string; title: string; sub?: string; rows: Row[] }[] = [
    { id: "limits", title: "How much", rows: NUMBERS.map(([k, label]) => ({ id: String(k), label, cell: (p: PlanId) => num(p, k) })) },
    ...FLAG_GROUPS.map((g) => ({ id: `paid-${g.id}`, title: g.title, sub: "What each plan adds", rows: flagRows(g.id) })),
  ];
  const everyone: Row[] = EVERYONE.map((label) => ({ id: label, label, cell: () => "✓" }));
  const columns = (first: string): Column<Row>[] => [
    // the group's name is the heading just above the table: said again as the first column's header it was the same word twice, so it is named for assistive tools only (VR3-016)
    { key: "label", header: <span className="sr-only">{first}</span>, wrap: true, cell: (r) => nameOf(r.label) },
    ...ids.map((p) => ({ key: p, header: names[p], numeric: true, cell: (r: Row) => valueOf(r.cell(p)) })),
  ];
  // one table per group, each with the plan names on top; the header stays in view as the page scrolls past it
  return (
    <Card id="compare" className="k-compare">
      <CardHead title="Side by side" />
      {groups.map((g, i) => (
        <div key={g.id} className="k-stack" data-plans-group={g.id}>
          {g.sub && groups[i - 1]?.sub !== g.sub && <h3 className="k-sub">{g.sub}</h3>}
          {g.sub ? <h4 className="k-sub k-small">{g.title}</h4> : <h3 className="k-sub">{g.title}</h3>}
          <DataTable label={`Plans side by side: ${g.sub ? `${g.sub.toLowerCase()}, ` : ""}${g.title.toLowerCase()}`} columns={columns(g.title)} rows={g.rows} rowKey={(r) => r.id} pinHead />
        </div>
      ))}
      {/* the same on every plan: one line each, folded so the page stays short (DP1-022: three lists said the same facts) */}
      <div className="k-stack" data-plans-group="all">
        <Disclosure summary={`On every plan (${everyone.length} tools)`}>
          <ul className="k-list">{everyone.map((r) => <li key={r.id}>{r.label}</li>)}</ul>
        </Disclosure>
      </div>
    </Card>
  );
}
