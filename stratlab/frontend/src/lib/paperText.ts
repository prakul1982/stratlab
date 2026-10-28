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
  return `Orders fill at the close of the candle your rules act on${slip}, not at the live price${fees ? `, and pay ${fees}` : ""}. Unrealised P&L already counts the entry's costs. The notebook's test fills at the next candle's open instead, so a paper run can differ a little from it.`;
}

/** The session's rules in a line each, for the session page (DB-022: it had no rules summary). `cond` writes one rule. */
export function rulesLines<C>(s: { entry: C[]; exit: C[]; entryJoin?: string; side?: string }, cond: (c: C) => string): string[] {
  const join = s.entryJoin === "any" ? " or " : " and ";
  const out = [`${s.side === "short" ? "Sells short" : s.side === "both" ? "Goes long" : "Buys"} when ${s.entry.length ? s.entry.map(cond).join(join) : "no rule is set"}.`];
  if (s.exit.length) out.push(`Exits when ${s.exit.map(cond).join(" or ")}.`);
  return out;
}

/** The last day of Free's paper trading trial, in India's calendar: the trial ends at midnight India time after its fifth
 * Indian market day, so "until the end of Thu 29 Oct", not "until 30 Oct, 18:30 UTC" (DP1-013). */
export function trialLastDay(endsAt: string): string {
  const d = new Date(new Date(endsAt).getTime() - 60_000);
  return d.toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", weekday: "short", day: "numeric", month: "short" }).replace(",", "").replace(/\bSept\b/, "Sep");
}

/** What Free's trial is, said in the start dialog before a first session starts it, and how long is left once it runs
 * (DP1-013: the dialog said "It runs until you stop it" while the trial ends after 5 market days). `days`: the trial's
 * length in Indian market days. */
export function trialStartLine(trial: { started: boolean; active: boolean; ends_at: string | null; days?: number } | null | undefined): string | null {
  if (!trial) return null;
  const days = trial.days ?? 5;
  if (!trial.started) return `On Free, paper trading is a trial of ${days} Indian market days from this first start (a start after the 3:30 PM close counts from the next market day; weekends and market holidays don't count, even for crypto). It ends at midnight India time after the ${days === 5 ? "fifth" : `${days}th`}, and the session stops then unless you upgrade.`;
  if (trial.active && trial.ends_at) return `Your Free trial runs until the end of ${trialLastDay(trial.ends_at)} (India time); the session stops then unless you upgrade.`;
  return "Your Free paper trading trial has ended, so a new session needs Basic or Pro.";
}

/** Said in the start dialog, before the click (DP1-015): stopping ends a session for good. */
export const STOP_IS_FINAL = "You can stop it any time from its page; a stopped session can't be restarted or paused, so a new one starts from fresh.";

/** What starting one more session would meet, said before Start rather than after it (DP1-014): the plan's count of sessions
 * running at once. Null while there is room. `next`: the next plan's count, when there is one. */
export function liveLimitLine(running: number, limit: number, next: { name: string; limit: number } | null): string | null {
  if (running < limit) return null;
  return `Your plan runs ${limit} live ${limit === 1 ? "strategy" : "strategies"} at a time and ${running === 1 ? "one is" : `${running} are`} running. Stop one first${next ? `, or ${next.name} runs ${next.limit}` : ""}.`;
}
