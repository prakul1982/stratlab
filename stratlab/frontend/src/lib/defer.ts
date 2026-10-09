import { useEffect, useState } from "react";

/* Calls a page can make after it has painted (R9R-010: /mine fired about 17 API calls at once on a cold load, so the first
 * figures waited behind the calendar and the results, which sit lower down; a browser holds six connections to one address
 * and the rest queue). The first screen's own calls go out at once; the lower cards' calls wait for the first paint and a
 * short pause, so the figures at the top get the connections first. */

/** How long after mounting the lower cards start their calls. */
export const DEFER_MS = 1200;

/** Run `fn` once the browser has painted the page and `ms` more have passed. Returns a function that cancels it. */
export function afterPaint(fn: () => void, ms = DEFER_MS): () => void {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let frame = 0;
  const go = () => { timer = setTimeout(fn, ms); };
  if (typeof requestAnimationFrame === "function") frame = requestAnimationFrame(() => go());
  else go();
  return () => {
    if (frame && typeof cancelAnimationFrame === "function") cancelAnimationFrame(frame);
    if (timer !== undefined) clearTimeout(timer);
  };
}

/** False on the first render, true once the page has painted and `ms` have passed. A card that reads its data only when
 * this is true leaves the connections to the first screen's calls. */
export function useAfterPaint(ms = DEFER_MS): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => afterPaint(() => setReady(true), ms), [ms]);
  return ready;
}
