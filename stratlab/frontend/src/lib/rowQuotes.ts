import { useEffect, useRef, useState } from "react";
import { quotesInBatches } from "./investUi";
import { liveQuote } from "./liveRefresh";
import { useMarketRefresh } from "./marketLive";
import { researchApi, type Quote, type Region } from "./research";

/** At most this many rows in view get a live price (and, on the results page, their earlier moves and an implied move): the first of
 * each list, never a whole 134-company day at once. */
export const LIVE_ROWS = 48;

/** The prices of the rows in view: read once when the rows change, then each minute while the market trades and for a quarter
 * hour after (never otherwise), 24 companies a call, through the company pages' own quote read. `quoteAt` is the latest time any
 * of them was read, `live` whether that was a live one; a company with no price is left out. */
export function useRowQuotes(region: Region, symbols: string[]) {
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>({});
  const stamp = useRef(0);
  const read = () => {
    const ticket = stamp.current;
    void quotesInBatches((syms) => researchApi.quotes(region, syms), symbols,
      (soFar) => ticket === stamp.current && setQuotes((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(soFar).filter(([, v]) => v?.price != null)) })),
      () => ticket === stamp.current);
  };
  useMarketRefresh([region], read, symbols.length > 0);
  const key = `${region}|${symbols.join(",")}`;
  useEffect(() => {
    stamp.current += 1;
    setQuotes({});
    if (symbols.length) read();
    return () => { stamp.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const quoteAt = Object.values(quotes).map((x) => x?.at).filter((x): x is string => !!x).sort().pop() ?? null;
  return { quotes, quoteAt, live: !!quoteAt && liveQuote(quoteAt) };
}
