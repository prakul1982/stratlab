/** SORT EVERYWHERE (site88, owner: "sorting on every table header"): reading a table cell's words back as a value to sort by, and sorting rows
 *  by one column. A number column sorts by the number ("₹1,234.5 cr", "−2.3%", "1.2 lakh cr", "$3.4bn", "12x"), a column of days by the day
 *  ("13 Nov 2026", "2026-11-13", "Nov 2026"), any other by its words; a cell with no value (empty, "–") goes last either way. */

export type SortKind = "number" | "date" | "text";
export type SortValue = number | string | null;

const MONTHS: Record<string, number> = { jan: 0, feb: 1, mar: 2, apr: 3, may: 4, jun: 5, jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11 };
// the unit after a figure, as a multiple (crore is 10^7, a lakh crore 10^12): only a column that mixes them needs it, but it never hurts
const UNITS: [RegExp, number][] = [
  [/^lakh\s*(?:cr|crore)s?\b/i, 1e12], [/^(?:tn|trillion|t)\b/i, 1e12], [/^(?:cr|crore)s?\b/i, 1e7], [/^(?:bn|billion|b)\b/i, 1e9],
  [/^(?:lakh|lakhs|lac|l)\b/i, 1e5], [/^(?:mn|million|m)\b/i, 1e6], [/^(?:k|thousand)\b/i, 1e3],
];

/** No value: nothing, or only a dash. */
export const isBlank = (s: string): boolean => /^\s*[–—-]?\s*$/.test(s);

/** The number a cell starts with (signs, ▲/▼, ₹/$ and a unit read), or null when it doesn't start with one ("Rank 3", a name). */
export function parseNumber(text: string): number | null {
  const s = text.replace(/ /g, " ").trim();
  const m = /^([▲▼↑↓+\-−–]?)\s*([₹$€£]?)\s*([+\-−]?)\s*(\d[\d,]*(?:\.\d+)?|\.\d+)\s*(.*)$/s.exec(s);
  if (!m) return null;
  let n = Number(m[4].replace(/,/g, ""));
  if (!Number.isFinite(n)) return null;
  const neg = /[▼↓\-−–]/.test(m[1]) || /[\-−]/.test(m[3]);
  const rest = m[5];
  for (const [re, mult] of UNITS) if (re.test(rest)) { n *= mult; break; }
  return neg ? -n : n;
}

/** The day a cell names (as a time in ms), when one is at or near its start ("13 Nov 2026", "13 Nov", "As of 30 Sep 2026", "2026-11-13",
 *  "Nov 2026"); a day with no year is this year's. */
export function parseDate(text: string, year = new Date().getFullYear()): number | null {
  const s = text.replace(/ /g, " ");
  const iso = /(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(s);
  if (iso && iso.index <= 8) return Date.UTC(+iso[1], +iso[2] - 1, +iso[3], +(iso[4] ?? 0), +(iso[5] ?? 0));
  const dm = /\b(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?,?(?:\s+(\d{4}))?(?:,?\s+(\d{1,2}):(\d{2}))?/.exec(s);
  if (dm && dm.index <= 8 && MONTHS[dm[2].toLowerCase()] != null) return Date.UTC(dm[3] ? +dm[3] : year, MONTHS[dm[2].toLowerCase()], +dm[1], +(dm[4] ?? 0), +(dm[5] ?? 0));
  const my = /\b([A-Za-z]{3})[a-z]*\.?\s+(\d{4})\b/.exec(s);
  if (my && my.index <= 8 && MONTHS[my[1].toLowerCase()] != null) return Date.UTC(+my[2], MONTHS[my[1].toLowerCase()], 1);
  return null;
}

/** What a column holds: numbers (a `numeric` column, or one whose every value starts with a number), days (every value names one), or words. */
export function kindOf(texts: string[], numeric?: boolean): SortKind {
  const vals = texts.filter((t) => !isBlank(t));
  if (vals.length && vals.every((t) => parseDate(t) != null)) return "date";      // a column of days, right-aligned or not
  if (numeric) return "number";
  if (!vals.length) return "text";
  if (vals.every((t) => parseNumber(t) != null && /^[\s▲▼↑↓+\-−–₹$€£\d.,%x×]*(?:lakh\s*cr|lakh|cr|crore|bn|mn|m|k|tn)?[\s%x×]*(?:\s·.*)?$/i.test(t))) return "number";
  return "text";
}

/** A cell's value to sort by, as its column holds it. */
export function valueOf(text: string, kind: SortKind): SortValue {
  if (isBlank(text)) return null;
  if (kind === "number") return parseNumber(text);
  if (kind === "date") return parseDate(text);
  return text.trim().toLowerCase();
}

/** The direction a first click sorts in: high to low for numbers and days (the biggest, the newest first), A to Z for words. */
export const firstDesc = (kind: SortKind): boolean => kind !== "text";

const collator = typeof Intl !== "undefined" ? new Intl.Collator("en-IN", { numeric: true, sensitivity: "base" }) : null;

/** Rows sorted by their values (one per row, in the same order), the blanks last whichever the direction; ties keep their order. */
export function sortByValues<R>(rows: R[], values: SortValue[], desc: boolean): R[] {
  const idx = rows.map((_, i) => i);
  idx.sort((a, b) => {
    const x = values[a], y = values[b];
    if (x == null || y == null) return x == null && y == null ? a - b : x == null ? 1 : -1;
    const c = typeof x === "number" && typeof y === "number" ? x - y : collator ? collator.compare(String(x), String(y)) : String(x).localeCompare(String(y));
    return (desc ? -c : c) || a - b;
  });
  return idx.map((i) => rows[i]);
}
