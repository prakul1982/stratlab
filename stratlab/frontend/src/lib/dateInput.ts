/** Reading a date typed by hand, day first as India writes it, for the kit's DateInput. Pure functions (tested in
 * unit/review-r1.test.mjs). A date is kept as a calendar day, "YYYY-MM-DD", never moved by a time zone. */
const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];

const pad = (n: number) => String(n).padStart(2, "0");

function valid(y: number, m: number, d: number): string | null {
  if (!(y >= 1900 && y <= 2200 && m >= 1 && m <= 12 && d >= 1 && d <= 31)) return null;
  const t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCMonth() === m - 1 && t.getUTCDate() === d ? `${y}-${pad(m)}-${pad(d)}` : null;
}

const year = (s: string) => { const n = Number(s); return s.length <= 2 ? 2000 + n : n; };

const MONTH_NAMES = "january february march april may june july august september october november december".split(" ");

/** The year, month and day a text spells, in any of the accepted ways, whether or not that day exists. */
function partsOf(text: string): [number, number, number] | null {
  const s = text.trim().toLowerCase().replace(/,/g, " ").replace(/\s+/g, " ");
  if (!s) return null;
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return [+m[1], +m[2], +m[3]];
  m = s.match(/^(\d{1,2})[/.\- ](\d{1,2})[/.\- ](\d{2}|\d{4})$/);
  if (m) return [year(m[3]), +m[2], +m[1]];
  m = s.match(/^(\d{1,2})[ \-]?([a-z]{3,9})\.?[ \-]?(\d{2}|\d{4})$/);
  if (m) {
    const k = MONTHS.indexOf(m[2].slice(0, 3));
    return k >= 0 && (m[2].length === 3 || MONTH_NAMES[k].startsWith(m[2])) ? [year(m[3]), k + 1, +m[1]] : null;
  }
  return null;
}

/** "14 Aug 2025", "14 august 2025", "14/08/2025", "14-08-25", "14.08.2025" or "2025-08-14" → "2025-08-14"; null when
 * it isn't a real day. Numbers are read day first (14/08 is 14 August), never month first. */
export function parseDay(text: string): string | null {
  const p = partsOf(text);
  return p ? valid(p[0], p[1], p[2]) : null;
}

/** What is wrong with a text that isn't a day: a date written the right way round that doesn't exist (31/02/2026) says
 * which day is missing; anything else says how to write one (R13S-016: "Write the date day first" for 31 Feb). */
export function whyNotDay(text: string): string {
  const p = partsOf(text);
  if (p && p[0] >= 1900 && p[0] <= 2200 && p[1] >= 1 && p[1] <= 12 && p[2] >= 1 && p[2] <= 31) {
    return `There is no ${p[2]} ${MONTH_NAMES[p[1] - 1].replace(/^./, (c) => c.toUpperCase())} ${p[0]}.`;
  }
  return "Write the date day first, like 14 Aug 2025 or 14/08/2025.";
}

/** "2025-08-14" → "14 Aug 2025" (what the box shows); "" for nothing. */
export function showDay(iso: string | null | undefined): string {
  const m = (iso ?? "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return "";
  return `${+m[3]} ${MONTHS[+m[2] - 1].replace(/^./, (c) => c.toUpperCase())} ${m[1]}`;
}
