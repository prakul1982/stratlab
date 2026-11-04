import { useEffect, useState } from "react";
import { callsInFlight, onIdle } from "./inflight";

/* Calls a page can make after it has painted (R9R-010: /mine fired about 17 API calls at once on a cold load, so the first
 * figures waited behind the calendar and the results, which sit lower down; a browser holds six connections to one address
 * and the rest queue). The first screen's own calls go out at once; the lower cards' calls wait for the first paint and a
 * short pause, so the figures at the top get the connections first. */

/** How long after mounting the lower cards start their calls. */
export const DEFER_MS = 1200;

/** Run `fn` once the browser has painted the page and `ms` more have passed. Returns a function that cancels it. */
/** Once the page is painted and quiet this long (no call out), the later cards needn't wait the rest of the pause. */
export const QUIET_MS = 100;

/** Run `fn` once the browser has painted the page and either the first screen's calls are all answered (then QUIET_MS more) or `ms`
 * have passed, whichever is first (LIVE1B-085: a fixed 1.2 s pause held My space's Markets strip long after the first screen's calls
 * were back). Returns a function that cancels it. */
export function afterPaint(fn: () => void, ms = DEFER_MS): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined, quiet: ReturnType<typeof setTimeout> | undefined;
  let frame = 0, done = false, off = () => {};
  const stop = () => { if (timer !== undefined) clearTimeout(timer); if (quiet !== undefined) clearTimeout(quiet); off(); };
  const run = () => { if (done) return; done = true; stop(); fn(); };
  const go = () => {
    timer = setTimeout(run, ms);
    const check = () => { if (!callsInFlight() && quiet === undefined) quiet = setTimeout(run, Math.min(QUIET_MS, ms)); };
    off = onIdle(check);
    check();
  };
  if (typeof requestAnimationFrame === "function") frame = requestAnimationFrame(() => go());
  else go();
  return () => {
    done = true;
    if (frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
    stop();
  };
}

/** False on the first render, true once the page has painted and `ms` have passed. A card that reads its data only when
 * this is true leaves the connections to the first screen's calls. */
export function useAfterPaint(ms = DEFER_MS): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => afterPaint(() => setReady(true), ms), [ms]);
  return ready;
}
