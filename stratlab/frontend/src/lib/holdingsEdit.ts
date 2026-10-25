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

const VIA_NAMES: Record<string, string> = { kite: "Kite", ibkr: "IBKR" };

/** What an edit does to a row a broker or statement syncs (the server's holdings.set_qty and connect.sync). */
export function syncedNote(via: string): string {
  if (via === "cas") return "From your depository statement. The next statement sets the quantity and average it reads, replacing what you type here.";
  const name = VIA_NAMES[via] ?? via;
  return `Synced from ${name}. A quantity you type is kept: the shares above ${name}'s are kept as your own, through its next read. ` +
    `An average price typed alone is replaced by ${name}'s average on its next read.`;
}

/** Whether to say "live prices are offline": prices are missing and at least one stock really has no value to show. */
export function unpricedNote(prices: boolean, rows: { value: number | null }[]): boolean {
  return !prices && rows.some((r) => r.value == null);
}

/** The closes the holdings are valued at while live prices are off (DP2-001, DG-002): how many are at the exchange's close
 * of which day, and how many at the close in the uploaded file. */
export type Closes = { day: string | null; close: number; file: number } | null | undefined;

/** The line under the totals about where the prices are from: null while live prices cover every stock. `fmt` names a day. */
export function priceNote(prices: boolean, closes: Closes, rows: { value: number | null; market?: string }[], fmt: (iso: string) => string): string | null {
  const unpriced = rows.filter((r) => r.value == null && r.market !== "US").length;
  const parts: string[] = [];
  if (closes && (closes.close || closes.file)) {
    const at = [closes.close ? `the exchange's close${closes.day ? ` of ${fmt(closes.day)}` : ""}` : "", closes.file ? `the close in your holdings file for ${closes.file}` : ""].filter(Boolean).join(", and ");
    parts.push(`Live prices are off right now, so these are at their last close: ${at}.`);
  }
  if (unpriced && !prices) parts.push(`${unpriced} ${unpriced === 1 ? "stock has" : "stocks have"} no price, so ${unpriced === 1 ? "it is" : "they are"} shown at cost.`);
  return parts.length ? parts.join(" ") : null;
}

/** The gain-or-loss figure's label: of every line, or of the lines with a price when some are at cost (DG-001, DG-050: one
 * priced US stock's +131.8% stood for nine lines, eight of them with no price). */
export function pnlLabel(base: string, partial: { priced: number; lines: number } | null | undefined): string {
  return partial ? `${base} · ${partial.priced} of ${partial.lines} lines` : base;
}

/** "Today", or the session the day's change is of when that is an earlier day (DG-005: Friday's move labelled "Today" on a
 * Sunday, while Money home said "Last session (Fri 23 Oct)"). */
export function dayLabel(session: string | null | undefined, today: string, fmt: (iso: string) => string): string {
  return session && session < today ? `Last session (${fmt(session)})` : "Today";
}
