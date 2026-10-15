/** The headline change: the live total less the latest snapshot from before today that counts the same things (a change
 * to an entry snapshots today, which would always read as no change). A complete total reads against the latest complete
 * snapshot; a partial one (a stock with nothing to value it by) only against a snapshot that left out exactly the same,
 * so the change is like for like. None when there's no such snapshot. */
export function netWorthDelta(net: number, livePartial: string[] | null | undefined, hist: { d: string; net: number; partial?: string[] }[],
  today: string = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })) {
  const left = (p: string[] | null | undefined) => (p ?? []).join("\n");
  for (let i = hist.length - 1; i >= 0; i--) if (hist[i].d < today && left(hist[i].partial) === left(livePartial)) return { change: net - hist[i].net, since: hist[i].d };
  return null;
}

/** The expected-rate note under a repo-linked loan; says so when there is no repo history to work the spread from, and
 * before the first reset the expected rate is the sanctioned rate. */
export function expectedNote(repoAtReset: string, spread: number | null | undefined, lastReset?: string | null) {
  if (spread == null) return "Not enough repo history to work this out";
  return lastReset ? `repo ${repoAtReset} + ${spread.toFixed(2)}` : "the sanctioned rate (no reset yet)";
}
