import { Card, CardHead } from "./kit/Card";
import { DataTable, type Column } from "./kit/DataTable";
import { EVERYONE, FLAGS, LIMITS, NUMBERS, unlimitedLabel, type Limits, type PlanId } from "../lib/plans";

/** Every limit and feature side by side, from the server's plans when signed in; signed out, the
 * same tables from the app's own copy of the limits (R60-012: a visitor comparing plans saw less than a signed-in user). */
export function PlanCompare({ plans }: { plans?: Record<string, Partial<Limits>> }) {
  const lim = (p: PlanId): Limits => ({ ...LIMITS[p], ...(plans?.[p] ?? {}) });
  const num = (p: PlanId, k: keyof Limits) => {
    const v = lim(p)[k] as number | null;
    return v == null ? unlimitedLabel(p, k) : p === "free" && k === "live_limit" ? `${v}, for 5 market days` : v.toLocaleString("en-IN");
  };
  const ids: PlanId[] = ["free", "basic", "pro"];
  const names = { free: "Free", basic: "Basic", pro: "Pro" };
  type Row = { id: string; label: string; cell: (p: PlanId) => string };
  const groups: { id: string; title: string; rows: Row[] }[] = [
    { id: "limits", title: "How much", rows: NUMBERS.map(([k, label]) => ({ id: String(k), label, cell: (p: PlanId) => num(p, k) })) },
    { id: "paid", title: "What each plan adds", rows: FLAGS.map(([f, label]) => ({ id: String(f), label, cell: (p: PlanId) => (lim(p).features.includes(f) ? "✓" : "–") })) },
    { id: "all", title: "On every plan", rows: EVERYONE.map((label) => ({ id: label, label, cell: () => "✓" })) },
  ];
  const columns = (first: string): Column<Row>[] => [
    { key: "label", header: first, wrap: true, cell: (r) => r.label },
    ...ids.map((p) => ({ key: p, header: names[p], numeric: true, cell: (r: Row) => r.cell(p) })),
  ];
  // one table per group, each with the plan names on top; the header stays in view as the page scrolls past it
  return (
    <Card id="compare">
      <CardHead title="Side by side" />
      {groups.map((g) => (
        <div key={g.id} className="k-stack" data-plans-group={g.id}>
          <h3 className="k-sub">{g.title}</h3>
          <DataTable label={`Plans side by side: ${g.title.toLowerCase()}`} columns={columns(g.title)} rows={g.rows} rowKey={(r) => r.id} pinHead />
        </div>
      ))}
    </Card>
  );
}
