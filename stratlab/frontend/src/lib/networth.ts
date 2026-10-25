/** The headline change: the live total less the latest snapshot from before today that counts the same things (a change
 * to an entry snapshots today, which would always read as no change). A complete total reads against the latest complete
 * snapshot; a partial one (a stock with nothing to value it by) only against a snapshot that left out exactly the same,
 * so the change is like for like. None when there's no such snapshot. */
export function netWorthDelta(net: number, livePartial: string[] | null | undefined, hist: { d: string; net: number; partial?: string[]; added?: number }[],
  today: string = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })): { change: number; since: string; added?: number } | null {
  const left = (p: string[] | null | undefined) => (p ?? []).join("\n");
  for (let i = hist.length - 1; i >= 0; i--) {
    if (hist[i].d < today && left(hist[i].partial) === left(livePartial)) {
      // DP2-006: what entries added, changed or removed since then put in (a new FD) isn't a change in value: it is left
      // out of the change and said beside it
      const added = hist.slice(i + 1).reduce((a, h) => a + (h.added ?? 0), 0);
      return { change: net - hist[i].net - added, since: hist[i].d, ...(added ? { added } : {}) };
    }
  }
  return null;
}

/** The expected-rate note under a repo-linked loan; says so when there is no repo history to work the spread from, and
 * before the first reset the expected rate is the sanctioned rate. */
export function expectedNote(repoAtReset: string, spread: number | null | undefined, lastReset?: string | null) {
  if (spread == null) return "Not enough repo history to work this out";
  return lastReset ? `repo ${repoAtReset} + ${spread.toFixed(2)}` : "the sanctioned rate (no reset yet)";
}

/** The line under the headline change: its day, and the money entries put in or took out since, left out of it (DP2-006). */
export function sinceNote(move: { since: string; added?: number }, day: (iso: string) => string, money: (v: number) => string): string {
  const a = move.added ?? 0;
  return `since ${day(move.since)}${Math.abs(a) >= 1 ? `, leaving out ${money(Math.abs(a))} ${a > 0 ? "added in" : "taken out in"} new or changed entries` : ""}`;
}

const pct2 = (v: number) => `${v.toFixed(2)}%`;

/** DG-013: what the next reset brings when the repo rate has moved since the last one (the 7 Oct 2026 hike to 5.50%). */
export function nextResetNote(c: { benchmark: string; repo_now?: number | null; repo_at_reset?: number | null; next_expected?: number | null; expected?: number | null }): string {
  if (c.benchmark !== "repo" || c.repo_now == null || c.next_expected == null || c.repo_at_reset == null || Math.abs(c.repo_now - c.repo_at_reset) < 1e-9) return "";
  return ` The repo rate is ${pct2(c.repo_now)} now (${pct2(c.repo_at_reset)} at the last reset), so if it stays there the reset takes the expected rate to ${pct2(c.next_expected)}.`;
}
