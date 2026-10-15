/** A stage's length in days; "116+ days" when it began at or before the first candle read, so the true length is longer (R29D-002). */
export function stageDaysText(n: number, capped?: boolean): string {
  return `${n}${capped ? "+" : ""} day${n === 1 && !capped ? "" : "s"}`;
}
