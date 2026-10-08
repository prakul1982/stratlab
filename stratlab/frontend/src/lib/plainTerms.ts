/* Words a person reads in the library and the trend scan, spelled out. */

/** The scan's internal short name, spelled out: "ST S2: Stage 2 + Supertrend · NIFTY 50 stocks" becomes
 * "Stage 2 + Supertrend · NIFTY 50 stocks", and "Fresh ST S2" "Fresh Stage 2 + Supertrend". */
export function plainTerms(text: string | null | undefined): string {
  return (text ?? "").replace(/\bST S2:\s*Stage 2 \+ Supertrend/g, "Stage 2 + Supertrend").replace(/\bST S2\b/g, "Stage 2 + Supertrend");
}

/** What a test group holds, said accurately: a group named "NIFTY 50 stocks" that holds 5 of them is "5 of the NIFTY 50
 * stocks", not "NIFTY 50 stocks (5)". A name with no number in it gets the count after it ("My banks · 3 in the test"). */
export function groupLabel(name: string, members?: number | null): string {
  if (members == null || !Number.isFinite(members) || members < 1) return name;
  const named = name.match(/\b(\d+)\b/);
  if (named) return Number(named[1]) === members ? name : `${members} of the ${name}`;
  return `${name} · ${members} in the test`;
}
