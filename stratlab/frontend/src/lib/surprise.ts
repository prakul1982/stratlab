/** The surprise percentage worked out from the two figures as they are printed (2 decimals), so the page's own numbers
 * give the percentage beside them: 1.85 vs 1.81 is +2.2%, not the +2.4% of the unrounded figures. Null against an
 * estimate of 0. */
export function surpriseShown(actual: number, estimate: number): number | null {
  const a = Math.round(actual * 100) / 100, e = Math.round(estimate * 100) / 100;
  return e ? ((a - e) / Math.abs(e)) * 100 : null;
}
