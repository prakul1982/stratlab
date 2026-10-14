/** The headline change: the live total less the latest complete snapshot from before today (a change to an entry
 * snapshots today, which would always read as no change). None while the live total is partial or there's no such snapshot. */
export function netWorthDelta(net: number, livePartial: string[] | null | undefined, hist: { d: string; net: number; partial?: string[] }[],
  today: string = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })) {
  if (livePartial?.length) return null;
  for (let i = hist.length - 1; i >= 0; i--) if (hist[i].d < today && !hist[i].partial?.length) return { change: net - hist[i].net, since: hist[i].d };
  return null;
}

/** The expected-rate note under a repo-linked loan; says so when there is no repo history to work the spread from. */
export function expectedNote(repoAtReset: string, spread: number | null | undefined) {
  return spread == null ? "Not enough repo history to work this out" : `repo ${repoAtReset} + ${spread.toFixed(2)}`;
}
