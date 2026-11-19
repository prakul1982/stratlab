/** A page whose source said it is busy (the server's 503, "source_busy") asks again on its own, a little later each time,
 * instead of showing an error at once (rel1, CX1 problem 3: a Pro user's deep dive showed "the fundamentals source is busy").
 * The waits, in milliseconds; after the last one the page shows the error with "Try again". */
export const BUSY_RETRY_MS = [4000, 10000, 20000];

/** How long to wait before asking again after `e` on the `attempt`-th automatic try (0 first), or null: not a busy answer, or
 * the tries are used up. */
export function busyRetryIn(e: unknown, attempt: number): number | null {
  const status = (e as { status?: number } | null)?.status;
  return status === 503 && attempt >= 0 && attempt < BUSY_RETRY_MS.length ? BUSY_RETRY_MS[attempt] : null;
}

/** The line shown while waiting: the server's own words, then when it asks again. */
export const busyLine = (message: string, ms: number): string =>
  `${message.replace(/\s*Try again[^.]*\.?$/i, "").trim()} Asking again in ${Math.round(ms / 1000)} s.`;
