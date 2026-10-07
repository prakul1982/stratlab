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

/** "14 Aug 2025", "14 august 2025", "14/08/2025", "14-08-25", "14.08.2025" or "2025-08-14" → "2025-08-14"; null when
 * it isn't a real day. Numbers are read day first (14/08 is 14 August), never month first. */
export function parseDay(text: string): string | null {
  const s = text.trim().toLowerCase().replace(/,/g, " ").replace(/\s+/g, " ");
  if (!s) return null;
  let m = s.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (m) return valid(+m[1], +m[2], +m[3]);
  m = s.match(/^(\d{1,2})[/.\- ](\d{1,2})[/.\- ](\d{2}|\d{4})$/);
  if (m) return valid(year(m[3]), +m[2], +m[1]);
  m = s.match(/^(\d{1,2})[ \-]?([a-z]{3,9})\.?[ \-]?(\d{2}|\d{4})$/);
  if (m) {
    const k = MONTHS.indexOf(m[2].slice(0, 3));
    return k >= 0 && (m[2].length === 3 || "january february march april may june july august september october november december".split(" ")[k].startsWith(m[2]))
      ? valid(year(m[3]), k + 1, +m[1]) : null;
  }
  return null;
}

/** "2025-08-14" → "14 Aug 2025" (what the box shows); "" for nothing. */
export function showDay(iso: string | null | undefined): string {
  const m = (iso ?? "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return "";
  return `${+m[3]} ${MONTHS[+m[2] - 1].replace(/^./, (c) => c.toUpperCase())} ${m[1]}`;
}
