/* How the Market pulse's index levels load (R24-001: at India's open the request took 13 to 40 s, and on an iPhone the
 * skeleton never went away, with no word of why). Pure, so the unit tests can read it. */

/** After this long without an answer the page says it is still loading and offers Retry, instead of a skeleton for ever. */
export const PULSE_SLOW_MS = 15_000;
/** While the server's first read of the levels since it started is still going it answers `pending`: asked again this often… */
export const PULSE_PENDING_EVERY_MS = 2_000;
/** …this many times before the page says it is still loading. */
export const PULSE_PENDING_TRIES = 6;

export type PulseLoad = "loading" | "slow" | "error" | "ready";

/** What the levels card shows: the levels once they are in; an error when the request failed; "slow" once PULSE_SLOW_MS has
 * passed (or the server's first read is still pending after every retry); a skeleton before that. */
export function pulseLoad(s: { data: unknown | null; error: string | null; slow: boolean }): PulseLoad {
  if (s.data) return "ready";
  if (s.error) return "error";
  return s.slow ? "slow" : "loading";
}

/** Whether a `pending` answer is asked again (true) or the page gives up waiting and says it is still loading (false). */
export const askAgain = (pending: boolean | undefined, tries: number) => !!pending && tries < PULSE_PENDING_TRIES;
