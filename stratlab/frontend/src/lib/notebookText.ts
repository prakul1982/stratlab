/* Words on the notebook page that depend on what is being run. */

/** "45 s" or "1 min 05 s": how long a run has taken so far. */
export const runTime = (s: number) => (s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${String(s % 60).padStart(2, "0")} s`);

/** What a run will take, said honestly (R11C-018): one instrument takes seconds; a group's first run reads every member's
 * prices first, so it can take a minute or two, and the runs after it take seconds. While a long run goes, it says so. */
export function runCopy(members: number, running: boolean, elapsed: number): string {
  if (!members) return running && elapsed >= 20 ? "Still running: longer periods and intraday candles take longer." : "Takes a few seconds.";
  if (running && elapsed >= 20) return `Still running: reading the prices of ${members} instruments. A group's first run can take a minute or two.`;
  return `A group of ${members}: the first run reads every one's prices and can take a minute or two; runs after that take a few seconds.`;
}

/** An experiment's trade count in its row: closed trades, and the one still open at the end beside it, so "0 trades" never
 * sits next to a +5.4% that the open trade made (DP1-010). */
export function tradesCount(n: number, open: number): string {
  const closed = `${n} ${open ? "closed " : ""}trade${n === 1 ? "" : "s"}`;
  return open ? `${closed}, ${open} still open` : closed;
}
