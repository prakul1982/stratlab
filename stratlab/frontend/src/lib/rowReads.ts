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
