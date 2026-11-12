/* Admin → Library: how a kept entry's dates and state are said. No React here, so the unit tests read it as it is. */
import { IST, fmtDate } from "../../lib/format";

/** An entry's day in India ("28 Oct"): the store's times are UTC instants, so the day is the India day, never the UTC date's first ten
 * characters (lane upd1: an entry kept at 01:00 IST read as the day before). */
export const keptDay = (iso: string): string => fmtDate(iso, { year: false, tz: IST });

/** "28 Oct" or "2 Oct – 28 Oct": the oldest and newest entry of a store, by the India day. */
export const keptSpan = (a: string | null, b: string | null): string =>
  (!a || !b ? "–" : keptDay(a) === keptDay(b) ? keptDay(a) : `${keptDay(a)} – ${keptDay(b)}`);

/** Why a kept theme deck is not the file people get now (the server's `stale`), in words; null when it is. */
export const deckStaleText = (stale: string | null | undefined): string | null =>
  stale === "older version" ? "Not served: made under older rules or an older deck"
    : stale === "earlier day" ? "Not served: an earlier day's file (a deck is made again each day)"
      : null;
