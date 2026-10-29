/* The chart for one list item (MW-1): the shared price chart with every timeframe from 1 minute to 1 month, drawings,
 * indicators and the chosen timeframe kept on the account per symbol, and live prices moving the forming candle. The panel,
 * the full page and the full-screen view all show this one component. Facts only: prices as the market printed them. */
import { useMemo } from "react";
import { PriceChart, companyLoader, instrumentLoader, type LiveFeed, type RangeKey, type Tf } from "../../charts/price/lazy";
import { WORKSPACE_TFS } from "../../charts/price/ticks";
import { useApp } from "../../lib/app";
import { marketState } from "../../lib/marketHours";
import { priceDp } from "../../lib/format";
import { readLocal } from "../../charts/price/drawSync";
import { live } from "../../lib/watchApi";
import { chartSource, currencyOf, labelOf, type WatchItem } from "../../lib/watch";

export function ChartWorkspace({ item, height = 420 }: { item: WatchItem; height?: number }) {
  const { markets } = useApp();
  const src = chartSource(item);
  const load = useMemo(() => (src.kind === "company" ? companyLoader(src.region, src.symbol, null, true) : instrumentLoader(src.id)),
    [src.kind, src.kind === "company" ? src.region : src.id, src.kind === "company" ? src.symbol : ""]);   // eslint-disable-line react-hooks/exhaustive-deps
  // the chart's own subscription: the shared live client joins it with the panel's, so one stream and one read serve both
  const feed = useMemo<LiveFeed>(() => ({
    market: item.market,
    subscribe: (on, state) => {
      const sub = live().subscribe({
        tick: (k, t) => { if (k === item.id) on(t); },
        state: (s) => state(s.streamed.includes(item.id)),
      });
      sub.set([item.id]);
      return () => sub.close();
    },
  }), [item.id, item.market]);
  const market = markets.find((m) => m.id === item.market);
  const open = market ? marketState(market).open : null;
  const currency = currencyOf(item);
  // the timeframe and range this symbol was last charted on (kept with its drawings), the chart's first view
  const saved = useMemo(() => {
    const l = readLocal(src.storageKey)?.layout;
    const tf = (WORKSPACE_TFS as readonly string[]).includes(l?.tf ?? "") ? (l!.tf as Tf) : undefined;
    const ranges = ["1D", "5D", "1M", "6M", "YTD", "1Y", "5Y", "All"];
    return { tf, range: tf ? (ranges.includes(l?.range ?? "") ? (l!.range as RangeKey) : null) : undefined };
  }, [src.storageKey]);
  return (
    <PriceChart key={src.storageKey} symbol={labelOf(item)} storageKey={src.storageKey} currency={currency} load={load}
      timeframes={WORKSPACE_TFS as unknown as Tf[]} tf={saved.tf} range={saved.range} feed={feed} rememberView marketOpen={open} height={height}
      decimals={priceDp({ market: item.market, symbol: item.symbol, currency })} noVolume={item.market === "FX"} />
  );
}
