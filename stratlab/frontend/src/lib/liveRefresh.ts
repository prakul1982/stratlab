import { useEffect, useRef } from "react";

/* Prices on a page left open while the market trades (R63-002: TCS stayed at ₹2,480.00 on its page from 09:36 to 09:38
 * while NIFTY moved 90 points): the page reads them again once a minute, only while its tab is in view, and once on
 * coming back to it. */

export const LIVE_REFRESH_MS = 60_000;
/** A quote read within this long is a live one: older, the market has stopped trading and nothing is read again. */
export const LIVE_QUOTE_MS = 15 * 60_000;

export const liveQuote = (at: string | null | undefined, now = Date.now()) => {
  const t = at ? Date.parse(at) : NaN;
  return Number.isFinite(t) && now - t < LIVE_QUOTE_MS;
};

/** Calls `tick` every `ms` while `on` and the tab is visible, and when the tab comes back into view after `ms` or more. */
export function useLiveRefresh(on: boolean, tick: () => void, ms = LIVE_REFRESH_MS) {
  const fn = useRef(tick);
  useEffect(() => { fn.current = tick; });
  useEffect(() => {
    if (!on) return;
    let last = Date.now();
    const run = (force: boolean) => {
      if (document.visibilityState !== "visible" || (!force && Date.now() - last < ms)) return;
      last = Date.now();
      fn.current();
    };
    const id = window.setInterval(() => run(true), ms);
    const back = () => run(false);
    document.addEventListener("visibilitychange", back);
    return () => { window.clearInterval(id); document.removeEventListener("visibilitychange", back); };
  }, [on, ms]);
}
