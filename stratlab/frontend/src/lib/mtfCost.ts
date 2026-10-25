/* The margin funding page's pure parts: the calculator's limits and the chart's ranges and axis (what the unit tests read). */
import { num } from "./format";
import { numberProblem, problems, type Limits } from "./validate";

type CostField = "buy" | "qty" | "margin_pct" | "rate_pct" | "days" | "charges" | "price" | "maint_pct";

/** The server's own limits (mtf.CostReq), checked as each box is typed in: a problem is said under its box, and the
 * answer goes rather than stand under figures it isn't for (DF-020: "Check the margin pct" in a toast, and "Holding for
 * 100000 days costs ₹0.00" from the last good answer). */
export const COST_LIMITS: Record<CostField, Limits> = {
  buy: { min: 0, above: true, max: 1e7, unit: "₹" }, qty: { min: 0, above: true, max: 1e8 },
  margin_pct: { min: 0, above: true, max: 100, below: true, unit: "%" }, rate_pct: { min: 0, max: 60, unit: "% / yr" },
  days: { min: 0, max: 3650, whole: true }, charges: { min: 0, max: 1e8, optional: true, unit: "₹" },
  price: { min: 0, above: true, max: 1e7, optional: true, unit: "₹" }, maint_pct: { min: 0, max: 100, below: true, optional: true, unit: "%" },
};

/** Each box's problem, only for the boxes with one. */
export const costProblems = (f: Record<CostField, string>): Partial<Record<CostField, string>> =>
  problems(Object.fromEntries((Object.keys(COST_LIMITS) as CostField[]).map((k) => [k, numberProblem(f[k], COST_LIMITS[k])])) as Record<CostField, string | null>);

export const RANGE_DAYS: [string, string, number][] = [["1m", "1M", 31], ["3m", "3M", 93], ["1y", "1Y", 366]];

/** The range switch for a daily history: 1M / 3M / 1Y only where the stored days are well past them (one and a half
 * times), always "All" beside them. 44 days offered "1M" and "All", two charts that looked alike (DF-021). */
export function rangesFor(spanDays: number): [string, string][] {
  return RANGE_DAYS.filter(([, , d]) => spanDays >= d * 1.5).map(([value, label]) => [value, label]);
}

/** A chart's axis in crore, as the figures are: "₹1,42,500 cr", never "₹1.425L cr" (DF-021). */
export const axisCrore = (v: number): string => `₹${num(v, 0)} cr`;
