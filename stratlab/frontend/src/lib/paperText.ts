/* What a paper session says about stopping it (R11C-002). */

/** The stop dialog: an open position stays open, valued at the last price, and the stopped page shows it that way. */
export const STOP_DIALOG = "Open paper positions stay open, valued at the last price before the stop. Nothing more is traded, and the session can't be restarted.";

/** A stopped session's line for the position it still holds: "Stopped with a position open: 29 bought at $335.35, valued at
 * the last price before the stop, $335.88. Equity, return and the chart use that price." */
export function stoppedOpenLine(side: string | null | undefined, qty: number, entry: string, valuedAt: string | null): string {
  const what = `${qty.toLocaleString("en-IN")} ${side === "short" ? "sold short" : "bought"} at ${entry}`;
  return `Stopped with a position open: ${what}, ${valuedAt ? `valued at the last price before the stop, ${valuedAt}` : "valued where the equity curve ends"}. Equity, return and the chart use that price.`;
}

/** How a paper session's orders fill and what they pay, as the engine does it (DB-021: the start dialog said "Orders fill
 * at live prices"; they fill at the close of the candle the rules act on, slippage worse, with the market's fees, and the
 * unrealised P&L counts the entry's). `costs` is the market's own line ("0.1% exchange fee each way"); `brokerage` the
 * flat amount per order, already written in the market's money. */
export function fillsLine(r: { slippage: number; brokerage: number }, costs: string | null | undefined, brokerage: string): string {
  const slip = r.slippage > 0 ? `, ${+r.slippage.toFixed(3)}% worse for slippage (your setting)` : "";
  const fees = [costs ? (/^[A-Z][a-z]/.test(costs) ? costs.charAt(0).toLowerCase() + costs.slice(1) : costs) : "", r.brokerage > 0 ? `brokerage of ${brokerage} an order` : ""].filter(Boolean).join(", plus ");
  return `Orders fill at the close of the candle your rules act on${slip}, not at the live price${fees ? `, and pay ${fees}` : ""}. Unrealised P&L already counts the entry's costs.`;
}

/** The session's rules in a line each, for the session page (DB-022: it had no rules summary). `cond` writes one rule. */
export function rulesLines<C>(s: { entry: C[]; exit: C[]; entryJoin?: string; side?: string }, cond: (c: C) => string): string[] {
  const join = s.entryJoin === "any" ? " or " : " and ";
  const out = [`${s.side === "short" ? "Sells short" : s.side === "both" ? "Goes long" : "Buys"} when ${s.entry.length ? s.entry.map(cond).join(join) : "no rule is set"}.`];
  if (s.exit.length) out.push(`Exits when ${s.exit.map(cond).join(" or ")}.`);
  return out;
}
