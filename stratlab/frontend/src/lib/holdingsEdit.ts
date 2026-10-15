/* What the Holdings page sends when a holding is added, changed or removed, and how it names the dollar rate. Pure
 * functions, so unit/holdings-edit.test.mjs reads them directly. */

export type Mkt = "IN" | "US";
/** One change to the saved holdings (HoldingChange in models.py): a field left out of "set" keeps the saved value. The
 * server applies the changes to the holdings as saved now, so a sync that landed while the page was open stays. */
export type Change = { op: "set" | "add" | "remove"; symbol: string; market: Mkt; qty?: number; avg?: number | null };

/** The edit form's change: only the fields that differ from the row as shown, so a quantity a sync changed meanwhile, or an
 * average saved with more decimals than the page shows, isn't overwritten by the form's copy of it. */
export function editChange(row: { symbol: string; market?: Mkt; qty: number; avg: number | null }, qty: number, avg: number | null): Change {
  return { op: "set", symbol: row.symbol, market: row.market ?? "IN", ...(qty !== row.qty ? { qty } : {}), ...(avg !== row.avg ? { avg } : {}) };
}

/** "₹88.20 a dollar", with the rate's day when it was read more than a day before `now` (an old rate kept while a
 * day's read failed is never passed off as today's). */
export function dollarRate(rate: number, at: string | null | undefined, now: number = Date.now()): string {
  const t = at ? Date.parse(at) : NaN;
  const old = Number.isFinite(t) && now - t > 86_400_000;
  const day = old ? new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "Asia/Kolkata" }) : "";
  return `₹${rate.toFixed(2)} a dollar${old ? ` (the rate of ${day})` : ""}`;
}
