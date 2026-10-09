/* What a paper session says about stopping it (R11C-002). */

/** The stop dialog: an open position stays open, valued at the last price, and the stopped page shows it that way. */
export const STOP_DIALOG = "Open paper positions stay open, valued at the last price before the stop. Nothing more is traded, and the session can't be restarted.";

/** A stopped session's line for the position it still holds: "Stopped with a position open: 29 bought at $335.35, valued at
 * the last price before the stop, $335.88. Equity, return and the chart use that price." */
export function stoppedOpenLine(side: string | null | undefined, qty: number, entry: string, valuedAt: string | null): string {
  const what = `${qty.toLocaleString("en-IN")} ${side === "short" ? "sold short" : "bought"} at ${entry}`;
  return `Stopped with a position open: ${what}, ${valuedAt ? `valued at the last price before the stop, ${valuedAt}` : "valued where the equity curve ends"}. Equity, return and the chart use that price.`;
}
