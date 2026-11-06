import { useEffect, useRef, useState } from "react";
import { liveQuote } from "./liveRefresh";
import { useMarketRefresh } from "./marketLive";
import { quoteAsk, readRows } from "./rowReads";
import { researchApi, type Quote, type Region } from "./research";

/** At most this many rows get a price, the first in the order shown: every row a calendar page can show, a day opened in full
 * with "Show 50 more" included (LIVE4-001 with 48, LIVE5-001 with 240: a 200-company day opened in full ran past it). */
export const LIVE_ROWS = 1000;
/** Rows a quotes call asks for (the server's cap), and calls at once. */
export const QUOTE_PART = 24;
const QUOTE_PARALLEL = 2;
/** A row the price source was too busy for is asked again until this long after the read started (prices kept after the close
 * cost the server nothing, so the late rows come in on the second or third round). */
export const QUOTE_DEADLINE_MS = 45000;

/** The prices of the rows in view: read when the rows change (the rows with no price yet first: the ones "Show more" just added),
 * then each minute while the market trades and for a quarter hour after. Each call asks for 24 companies through the company
 * pages' own quote read, the one Invest home's watchlist uses; a company the server's price source was busy for, or a call that
 * failed, is asked again after a pause until QUOTE_DEADLINE_MS (LIVE5-001: such rows kept the day before's close for good).
 * `quoteAt` is the latest time any of them was read, `live` whether that was a live one, `reading` whether prices are still being
 * asked for; a company with no price is left out. */
export function useRowQuotes(region: Region, symbols: string[]) {
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>({});
  const [reading, setReading] = useState(false);
  const stamp = useRef(0);
  const have = useRef(quotes);
  have.current = quotes;
  const read = () => {
    const ticket = stamp.current;
    const order = [...symbols.filter((s) => have.current[s] == null), ...symbols.filter((s) => have.current[s] != null)];
    setReading(true);
    void readRows<Quote>(order, quoteAsk((part) => researchApi.quotesPending(region, part)),
      (got) => {
        const priced = Object.entries(got).filter(([, v]) => v?.price != null);
        if (priced.length && ticket === stamp.current) setQuotes((cur) => ({ ...cur, ...Object.fromEntries(priced) }));
      },
      { size: QUOTE_PART, parallel: QUOTE_PARALLEL, deadlineMs: QUOTE_DEADLINE_MS, alive: () => ticket === stamp.current })
      .finally(() => { if (ticket === stamp.current) setReading(false); });
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
  return { quotes, quoteAt, live: !!quoteAt && liveQuote(quoteAt), reading };
}
