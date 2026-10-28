import { useApp } from "./app";
import { useMinute } from "./clock";
import { marketsLive, useLiveRefresh } from "./liveRefresh";

/** Whether any of these markets is trading now (see marketsLive), judged again each minute. */
export function useMarketsLive(ids: readonly string[]): boolean {
  const { markets } = useApp();
  const now = useMinute();
  return marketsLive(markets, ids, now);
}

/** Calls `tick` each minute while one of these markets trades and the tab is in view (LIVE-1: every page with live market
 * numbers reads them again by itself). `also` narrows it further (a page that has nothing live to show yet); returns whether
 * the markets are live, for a page that says so. */
export function useMarketRefresh(ids: readonly string[], tick: () => void, also = true, ms?: number): boolean {
  const live = useMarketsLive(ids);
  useLiveRefresh(live && also, tick, ms);
  return live;
}
