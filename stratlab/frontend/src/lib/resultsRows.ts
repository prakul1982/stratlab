/* The results calendar's rows: pure helpers the page and the unit tests share (rel1, LIVE9A-014). */
import { resultDay } from "./resultDay";

/** The day after an ISO day, as an ISO day. */
export function nextDay(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

/** The day chips after "Today" and "Tomorrow": one per later day that has companies on it. A day gone by, today and tomorrow again by
 * their dates, and a day with nobody reporting (a weekend, an exchange holiday) are left out (LIVE9A-014: "Today, Tomorrow, Mon 16 Nov,
 * Wed 18 Nov" listed a past day and tomorrow twice; Thu 26 Nov, a US holiday, had a chip). */
export function laterDays(days: { date: string; count: number; session?: boolean }[], today: string | null, region?: string): string[] {
  const after = today ? nextDay(today) : "";
  // LIVE10A-020: a US day that is no session (a Sunday, Thanksgiving) gets no chip: its dates are the source's estimates
  return [...new Set(days.filter((d) => d.count > 0 && d.date > after && !(region === "US" && d.session === false)).map((d) => d.date))].sort();
}

/** The market value at the price shown beside it: the stored value scaled by the live price against the stored close it was worked out
 * at (LIVE9A-014: NVDA "$3.92T · $155.58", the value of the last close beside a live price). Unchanged without both prices, or when the
 * two are too far apart for a day's move (a split, a bad read): then the stored value stands. */
export function capAt(cap: number | null | undefined, last: number | null | undefined, live: number | null | undefined): number | null {
  if (cap == null) return null;
  if (!last || !live || last <= 0 || live <= 0) return cap;
  const k = live / last;
  return k >= 0.5 && k <= 2 ? cap * k : cap;
}

/** When a company reports, short, for its own place on the row's first line: "After the close", "Before the open". */
export const whenShort = (when: string | null | undefined): string | null =>
  when ? when.replace(/^./, (c) => c.toUpperCase()) : null;

/** site89b: a usual move's basis in words, for its hover: the average size of the moves over which earlier results days, measured how. */
export function usualTitle(m: { n: number; dates: string[]; basis?: string }): string {
  const days = m.dates.length ? ` (${m.dates.map((d) => resultDay(d)).join(", ")})` : "";
  return `Average size of the move over ${m.n} earlier results day${m.n === 1 ? "" : "s"}${days}: ${m.basis ?? "close before the results day to the close of the session after it"}`;
}

/** Rows with a usual move the "Usual move" column needs to stay (or half the answered rows, when fewer are answered). */
export const MIN_MOVES = 3;

/** Whether the "Usual move" column has too little to show (LIVE11A-019: "–" on every US row while it stayed): once all rows or at least
 * `enough` of them have been answered (rows past the reads' time limit are never answered, and kept the column up before), fewer than
 * MIN_MOVES rows (or half the answered ones, if that is fewer) carry a usual move. LIVE13A-005: one value in 408 US rows (a $0.05 stock)
 * kept the column on every day's table. */
export function movesEmpty(rows: { symbol: string; moves?: unknown; mv_days?: number }[], moves: Record<string, { moves?: unknown; since?: unknown } | null | undefined>, enough = 24): boolean {
  if (!rows.length) return false;
  // LIVE20A-006: a row whose company has no earlier results day kept (`mv_days` 0, from the server) can have no usual move: it is answered
  // from the first frame. The US column stood for 10 s with "–" on every row and loading bars on three, then went.
  const none = (r: { moves?: unknown; mv_days?: number }) => !r.moves && r.mv_days === 0;
  const back = rows.filter((r) => r.moves || moves[r.symbol] !== undefined || none(r));
  const some = new Set(back.filter((r) => r.moves || moves[r.symbol]?.moves).map((r) => r.symbol)).size;
  // ...and when the rows that could still bring one can't reach the count the column needs, it is decided now
  const could = new Set(rows.filter((r) => !r.moves && moves[r.symbol] === undefined && !none(r)).map((r) => r.symbol)).size;
  if (some + could < Math.min(MIN_MOVES, Math.ceil(rows.length / 2))) return true;
  // ...and while rows the server says have earlier results days (`mv_days` > 0) are still being read and could bring it there, it waits
  const pending = new Set(rows.filter((r) => !r.moves && moves[r.symbol] === undefined && (r.mv_days ?? 0) > 0).map((r) => r.symbol)).size;
  if (pending && some < MIN_MOVES && some + pending >= Math.min(MIN_MOVES, Math.ceil(rows.length / 2))) return false;
  if (back.length < Math.min(rows.length, enough)) return false;
  // LIVE12A-008: a "since the latest results" line alone is no usual move: the column of "–" stayed for it (NVDA "– / since Tue 17 Nov")
  const have = new Set(back.filter((r) => r.moves || moves[r.symbol]?.moves).map((r) => r.symbol)).size;
  return have < Math.min(MIN_MOVES, Math.ceil(back.length / 2));
}

/** LIVE13A-005: a US row's meeting without its quarter in brackets. The two sources name it two ways ("(quarter ended Oct 2026)" beside
 * "(fiscal Q3 2027)", mixed down one column), so the row says "Quarterly results" and the quarter goes in its hover text. */
export const purposeShown = (region: string, purpose: string): string =>
  region === "US" ? purpose.replace(/\s*\((?:fiscal Q\d \d{4}|quarter ended [A-Z][a-z]{2} \d{4})\)$/, "") : purpose;

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** Days after a quarter's end within which the results of that quarter fall (companies file within 45 days, 60 for a year's last; a few
 * late ones to 90): a shown quarter that ended longer before the row's results day is the quarter before the one being reported. */
export const REPORTED_WITHIN_DAYS = 95;

/** LIVE14A-009: the quarter a row's growth figures are of ("Jul 2026"), when it is the one before the quarter this results day reports
 * (PANW's row on 18 Nov, results due after the close, showed "Rev +34.5% Profit −211.2%", its quarter to Jul 2026, with no label); null
 * when the figures are of the quarter being reported, or the quarter can't be read. `of` is the stored "Jul 2026 vs Jul 2025". */
export function priorQuarter(of: string | null | undefined, resultsDay: string): string | null {
  const m = /^([A-Z][a-z]{2}) (\d{4})/.exec(String(of ?? "").trim());
  const mi = m ? MONTHS.indexOf(m[1]) : -1;
  if (!m || mi < 0) return null;
  const end = Date.UTC(Number(m[2]), mi + 1, 0);                    // the quarter's last day
  const day = Date.parse(`${resultsDay}T00:00:00Z`);
  if (!Number.isFinite(day)) return null;
  return (day - end) / 86400000 > REPORTED_WITHIN_DAYS ? `${m[1]} ${m[2]}` : null;
}

/** LIVE20A-006: the quarter a results row reports, from its meeting's own words ("Quarterly results (quarter ended Oct 2026)" -> "Oct 2026");
 * null when they don't say (India's rows, the US "(fiscal Q3 2027)" form). */
export function reportedQuarter(purpose: string | null | undefined): string | null {
  const m = /\(quarter ended ([A-Z][a-z]{2}) (\d{4})\)/.exec(String(purpose ?? ""));
  return m && MONTHS.includes(m[1]) ? `${m[1]} ${m[2]}` : null;
}

const monthNo = (q: string): number => { const m = /^([A-Z][a-z]{2}) (\d{4})/.exec(q.trim()); return m ? Number(m[2]) * 12 + MONTHS.indexOf(m[1]) : NaN; };

/** LIVE20A-006: a filing reports a quarter that ended at most this many days before it (a US 10-Q in 40-45, a 10-K in 60-75; India's results
 * in 45, a year's last in 60): figures of a quarter that ended earlier, on a row already filed, are those of the quarter before. */
export const FILED_WITHIN_DAYS = 75;

/** LIVE19A-011: the quarter every row's growth figures are of, on the row itself: "quarter to Oct 2026", or "previous quarter, to Jul 2026" when
 * the figures are of the quarter before the one this day reports. BJ's "Rev +15.7% Profit +15.4%" stood unlabelled beside rows that said
 * "previous quarter, to Jul 2026". LIVE20A-006: a filed row is not taken to be of its own quarter (the figures kept are read some time after
 * the filing): BJ's and The Buckle, filed on 20 Nov for the quarter ended Oct 2026, said "quarter to Aug 2026", IES "quarter to Jun 2026".
 * The quarter the meeting names (`reported`) decides when there is one; else, for a filed row, how long before the filing the figures'
 * quarter ended (FILED_WITHIN_DAYS); else how long before the results day (priorQuarter). null when the figures name no quarter. */
export function quarterLabel(of: string | null | undefined, resultsDay: string, o: { reported?: string | null; filedAt?: string | null } = {}): { text: string; prior: boolean } | null {
  const m = /^([A-Z][a-z]{2}) (\d{4})/.exec(String(of ?? "").trim());
  const mi = m ? MONTHS.indexOf(m[1]) : -1;
  if (!m || mi < 0) return null;
  const mine = `${m[1]} ${m[2]}`;
  const filed = o.filedAt ? Date.parse(`${o.filedAt.slice(0, 10)}T00:00:00Z`) : NaN;
  const p = o.reported && Number.isFinite(monthNo(o.reported)) ? (monthNo(mine) < monthNo(o.reported) ? mine : null)
    : Number.isFinite(filed) ? ((filed - Date.UTC(Number(m[2]), mi + 1, 0)) / 86400000 > FILED_WITHIN_DAYS ? mine : null)
      : priorQuarter(of, resultsDay);
  return p ? { text: `previous quarter, to ${p}`, prior: true } : { text: `quarter to ${mine}`, prior: false };
}
