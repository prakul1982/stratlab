/* Reading an extra figure for many rows of a table (the results page's earlier moves and implied moves), so that every row
 * asked for ends in a value or a dash within a fixed time (LIVE4-001: 64 cells sat on "Reading earlier results days" for minutes,
 * because the page read only the first 48 rows in the list's order, not the ones on screen, gave up after four rounds and
 * started again from nothing each time "Show 50 more" added rows). No imports: the unit tests run it as it is. */

/** One call's answer: the figures it got, and the rows the server could not reach in time (asked again after a pause). */
export interface PartAnswer<T> { got: Record<string, T | null>; pending: string[] }

export interface ReadOptions {
  /** rows a call asks for */
  size: number;
  /** calls in flight at once */
  parallel?: number;
  /** a row with no answer by then shows a dash (a later answer still fills it) */
  deadlineMs?: number;
  /** the pause before asking again for what came back pending */
  pauseMs?: number;
  /** false once the page has moved on (another market, the page closed): nothing more is asked or put */
  alive?: () => boolean;
}

export const READ_DEADLINE_MS = 18000;
export const READ_PAUSE_MS = 2000;

const sleep = (ms: number) => new Promise<void>((ok) => setTimeout(ok, ms));

/** Ask for `list` in parts of `size`, a few calls at a time, in the order given (the rows on screen first); what comes back pending
 * is asked again after a pause until `deadlineMs`, when every row still without an answer is put as null (a dash). A call that
 * fails puts its rows as null at once. `put` merges what it is given. Resolves once every row has a value or a dash. */
export async function readRows<T>(list: string[], ask: (part: string[]) => Promise<PartAnswer<T>>,
  put: (got: Record<string, T | null>) => void, o: ReadOptions): Promise<void> {
  const alive = o.alive ?? (() => true);
  const parallel = Math.max(1, o.parallel ?? 3), deadline = Date.now() + (o.deadlineMs ?? READ_DEADLINE_MS), pause = o.pauseMs ?? READ_PAUSE_MS;
  const open = new Set(list);              // rows with neither a value nor a dash yet
  const settle = (got: Record<string, T | null>) => {
    if (!alive()) return;
    const keys = Object.keys(got);
    if (!keys.length) return;
    for (const k of keys) open.delete(k);
    put(got);
  };
  const dashes = (rows: Iterable<string>) => Object.fromEntries([...rows].map((s) => [s, null])) as Record<string, T | null>;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<void>((ok) => { timer = setTimeout(ok, Math.max(0, deadline - Date.now())); });

  const work = (async () => {
    let todo = [...new Set(list)];
    for (let round = 0; todo.length && alive() && Date.now() < deadline; round += 1) {
      if (round) await sleep(Math.min(pause, Math.max(0, deadline - Date.now())));
      const parts: string[][] = [];
      for (let i = 0; i < todo.length; i += o.size) parts.push(todo.slice(i, i + o.size));
      const again: string[] = [];
      let next = 0;
      const lane = async () => {
        while (next < parts.length && alive()) {
          const part = parts[next++];
          try {
            const { got, pending } = await ask(part);
            const wait = new Set(pending.filter((s) => part.includes(s)));
            again.push(...part.filter((s) => wait.has(s)));
            settle(Object.fromEntries(part.filter((s) => !wait.has(s)).map((s) => [s, got[s] ?? null])));
          } catch {
            settle(dashes(part));             // a refused or failed call: its rows show a dash, never "Reading" for good
          }
        }
      };
      await Promise.all(Array.from({ length: Math.min(parallel, parts.length) }, lane));
      todo = again.filter((s) => open.has(s));
    }
  })();
  await Promise.race([work, late]);
  if (timer) clearTimeout(timer);
  if (alive() && open.size) settle(dashes(open));      // out of time: a dash for what is left (a late answer still fills it)
}

/** The rows of a calendar in the order a person sees them: each week's days still to come first, then its days gone by (which fold
 * away under "Earlier this week"), each day's rows as listed. */
export function shownOrder<R extends { date: string }>(weeks: { rows: R[] }[], today: string): R[] {
  const ahead: R[] = [], past: R[] = [];
  for (const w of weeks) {
    for (const d of [...new Set(w.rows.map((r) => r.date))]) (d >= today ? ahead : past).push(...w.rows.filter((r) => r.date === d));
  }
  return [...ahead, ...past];
}

/** A quotes call as readRows asks it (LIVE5-001: a results page's rows past the price source's budget were answered "no price",
 * and a call that failed was never asked again, so 28 rows and every row "Show 50 more" added kept the day before's close): a
 * stock the server says was busy, or every stock of a call that failed, is pending (asked again after a pause); a stock with
 * no price is a dash. */
export function quoteAsk<Q extends { price?: number | null }>(call: (part: string[]) => Promise<{ quotes?: Record<string, Q | null>; pending?: string[] }>) {
  return async (part: string[]): Promise<PartAnswer<Q>> => {
    try {
      const r = await call(part);
      const quotes = r?.quotes ?? {};
      const got: Record<string, Q | null> = {};
      for (const s of part) {
        const q = quotes[s] ?? quotes[s.toUpperCase()] ?? null;
        got[s] = q && q.price != null ? q : null;
      }
      return { got, pending: (r?.pending ?? []).filter((s) => part.includes(s)) };
    } catch {
      return { got: {}, pending: [...part] };
    }
  };
}

/** The market day (YYYY-MM-DD, in the market's zone) of the newest of these read times: the session the prices are of. */
export function sessionDayOf(ats: (string | null | undefined)[], tz: string): string | null {
  let best: number | null = null;
  for (const a of ats) {
    const t = a ? Date.parse(a) : NaN;
    if (!Number.isNaN(t) && (best == null || t > best)) best = t;
  }
  return best == null ? null : new Date(best).toLocaleDateString("en-CA", { timeZone: tz });
}

export interface PricesNote {
  /** whether the newest price was read while the market trades */ live: boolean;
  /** that read's time, formatted */ asOf: string | null;
  /** companies shown, and how many of them get a price */ rows: number; cap: number;
  /** the session the prices are of (YYYY-MM-DD) */ closeDay: string | null;
  /** rows still on an older stored close (their price not read yet), and that close's day */ older: number; olderDay: string | null;
  /** whether prices are still being asked for */ reading?: boolean;
}

/** The line under a calendar's tables that says what its prices are (LIVE5-001: "last close, Thu 5 Nov" was taken from the first
 * row's stored close while the rows above it showed Fri 6 Nov's): the day is the session the prices read are of, and rows still
 * on an older close are counted and their day said. */
export function pricesNote(o: PricesNote, day: (iso: string) => string): string {
  if (o.live && o.asOf) {
    return `Prices as of ${o.asOf}, read for ${o.rows > o.cap ? `the first ${o.cap} of the ${o.rows}` : `the ${o.rows}`} companies shown and again each minute while the market trades.`;
  }
  if (!o.rows) return "";
  const base = `Prices are each company's last close${o.closeDay ? `, ${day(o.closeDay)}` : ""}; the market is not trading now.`;
  if (!o.older || !o.olderDay || (o.closeDay && o.olderDay >= o.closeDay)) return base;
  const one = o.older === 1;
  return `${base} ${o.older} ${one ? "company's price" : "companies' prices"} ${o.reading ? (one ? "is still being read" : "are still being read") : "couldn't be read just now"}; ${one ? "it shows" : "they show"} the close of ${day(o.olderDay)}, in grey.`;
}
