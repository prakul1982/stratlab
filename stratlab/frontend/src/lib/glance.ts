const SIGNAL: Record<string, string> = { fresh: "Fresh Stage 2 + Supertrend", st_s2: "Stage 2 + Supertrend", stage2: "Stage 2" };

/** The badge after "Stage 2 · Supertrend up" on the watchlist glance, or null when it would only say the same again
 * (R29B-018: "Stage 2 · Supertrend down · Stage 2"). Only a fresh signal adds something (that it is new). */
export function trendBadge(stage: number | null | undefined, signal: string | null | undefined): string | null {
  if (!signal || !SIGNAL[signal]) return null;
  if (stage === 2 && (signal === "stage2" || signal === "st_s2")) return null;
  return SIGNAL[signal];
}
