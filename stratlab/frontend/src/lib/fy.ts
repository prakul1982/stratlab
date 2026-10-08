/** One financial year across the Money pages (tax report, tax tools, mutual funds, ITR export, the Money home's tax
 * tile): the year picked on one opens on the others, and with nothing picked they all open on the same year. A
 * financial year is named by the calendar year it starts in (2025 = FY 2025-26). */
const KEY = "stratlab.fy";

/** The year last picked on this device, if any. */
export function savedFy(): number | null {
  try {
    const v = Number(localStorage.getItem(KEY));
    return Number.isInteger(v) && v > 1990 && v < 2200 ? v : null;
  } catch { return null; }
}

/** Remember a year picked by hand. */
export function rememberFy(fy: number) {
  try { localStorage.setItem(KEY, String(fy)); } catch { /* storage off */ }
}

/** The year a page opens on, from the years it has: the year last picked, when the page has it; else the year whose
 * return is being filed now (the most recent completed one, the year before the current one), whether or not it has
 * anything in it, so every page opens on the same year (what each page holds is no part of the choice: the tax report
 * has sales, tax tools dividends, and they must not pull to different years). Only a page that doesn't list that year
 * (`hasData` says which of its years have anything) falls back to its latest year with data, else the current year. */
export function pickFy(years: number[], current: number, hasData: (fy: number) => boolean = () => true, saved = savedFy()): number {
  if (saved != null && years.includes(saved)) return saved;
  const filing = current - 1;
  if (years.includes(filing)) return filing;
  const busy = [...years].sort((a, b) => b - a).find(hasData);
  return busy ?? (years.includes(current) ? current : years[0] ?? current);
}

/** "FY 2025-26". */
export const fyLabel = (fy: number) => `FY ${fy}-${String(fy + 1).slice(2)}`;
