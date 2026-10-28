import { useEffect, useRef } from "react";
import { SETTLE_US_MIN, marketState, minutesSinceClose } from "./marketHours";
import type { Market } from "./types";

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

/** How long after a market's close its pages still read prices again, to pick up the closing prints (the US's settle for
 * longer: SETTLE_US_MIN, as its pages call them provisional until then). */
export const LIVE_GRACE_MIN = 15;

/** Whether any of these markets (by id: IN, US, FX, CMDTY, MCX, CRYPTO...) is trading now, or closed only minutes ago: the
 * pages that show its prices read them again each minute then, and stop when it is shut (LIVE-1). Crypto never closes and
 * FX and global commodities trade from Sunday evening to Friday evening New York time. Judged by the hours alone, not the
 * market's `status` from the one list read at sign-in: a feed that was off then may be on now, and a page left open across
 * the open must start reading when it opens. */
export function marketsLive(markets: readonly Market[], ids: readonly string[], now: number = Date.now()): boolean {
  const at = new Date(now);
  return ids.some((id) => {
    const m = markets.find((x) => x.id === id);
    if (!m || m.status === "soon") return false;
    const st = marketState({ ...m, status: "live" }, at);
    if (st.open) return true;
    const since = minutesSinceClose(m, at);
    return since != null && since < (id === "US" ? SETTLE_US_MIN : LIVE_GRACE_MIN);
  });
}
