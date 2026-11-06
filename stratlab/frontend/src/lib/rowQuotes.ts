import { useEffect, useRef, useState } from "react";
import { quotesInBatches } from "./investUi";
import { liveQuote } from "./liveRefresh";
import { useMarketRefresh } from "./marketLive";
import { researchApi, type Quote, type Region } from "./research";

/** At most this many rows get a live price, the first in the order shown: every row a calendar page shows (LIVE4-001: with 48, the rows
 * after the 48th, "Show 50 more" included, showed yesterday's close as "Price now" in market hours). 24 a call. */
export const LIVE_ROWS = 240;

/** The prices of the rows in view: read once when the rows change, then each minute while the market trades and for a quarter
 * hour after (never otherwise), 24 companies a call, through the company pages' own quote read. `quoteAt` is the latest time any
 * of them was read, `live` whether that was a live one; a company with no price is left out. */
export function useRowQuotes(region: Region, symbols: string[]) {
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>({});
  const stamp = useRef(0);
  const have = useRef(quotes);
  have.current = quotes;
  const read = () => {
    const ticket = stamp.current;
    // the rows with no price yet first (the ones "Show more" just added), then the rest again
    const order = [...symbols.filter((s) => have.current[s] == null), ...symbols.filter((s) => have.current[s] != null)];
    void quotesInBatches((syms) => researchApi.quotes(region, syms), order,
      (soFar) => ticket === stamp.current && setQuotes((cur) => ({ ...cur, ...Object.fromEntries(Object.entries(soFar).filter(([, v]) => v?.price != null)) })),
      () => ticket === stamp.current);
  };
  useMarketRefresh([region], read, symbols.length > 0);
  const key = `${region}|${symbols.join(",")}`;
  // another market starts from nothing; more rows of the same market keep the prices read so far while the list is read again
  const [quotesFor, setQuotesFor] = useState(region);
  if (quotesFor !== region) { setQuotesFor(region); setQuotes({}); }
  useEffect(() => {
    stamp.current += 1;
    if (symbols.length) read();
    return () => { stamp.current += 1; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  const quoteAt = Object.values(quotes).map((x) => x?.at).filter((x): x is string => !!x).sort().pop() ?? null;
  return { quotes, quoteAt, live: !!quoteAt && liveQuote(quoteAt) };
}
