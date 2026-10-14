/** The headline change: the live total less the latest complete snapshot. None while the live total is partial or no complete snapshot exists. */
export function netWorthDelta(net: number, livePartial: string[] | null | undefined, hist: { d: string; net: number; partial?: string[] }[]) {
  if (livePartial?.length) return null;
  for (let i = hist.length - 1; i >= 0; i--) if (!hist[i].partial?.length) return { change: net - hist[i].net, since: hist[i].d };
  return null;
}

/** The expected-rate note under a repo-linked loan; says so when there is no repo history to work the spread from. */
export function expectedNote(repoAtReset: string, spread: number | null | undefined) {
  return spread == null ? "Not enough repo history to work this out" : `repo ${repoAtReset} + ${spread.toFixed(2)}`;
}
