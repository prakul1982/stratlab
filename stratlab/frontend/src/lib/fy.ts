/** The financial year on the Money pages (tax report, tax tools, mutual funds, ITR export, US stocks, the Money home's tax
 * tile). Each page opens on its own year, from its own data: a year picked on one page is not carried to another, which
 * had opened the tax report on FY 2024-25 while the tax sat in FY 2025-26 (RC2B-002, DG-051). A financial year is named
 * by the calendar year it starts in (2025 = FY 2025-26). */

/** The year a page opens on, from the years it has: the year whose return is being filed now (the most recent completed
 * one, the year before the current one) when the page lists it, else its latest year with data (`hasData` says which of
 * its years have anything), else the current year. `saved` is a year the caller already holds (a year picked on this
 * very page), which wins when the page has it. */
export function pickFy(years: number[], current: number, hasData: (fy: number) => boolean = () => true, saved: number | null = null): number {
  if (saved != null && years.includes(saved)) return saved;
  const filing = current - 1;
  if (years.includes(filing)) return filing;
  const busy = [...years].sort((a, b) => b - a).find(hasData);
  return busy ?? (years.includes(current) ? current : years[0] ?? current);
}

/** The year a tax page opens on, the one rule for every Money and tax page (tax report, Money home's tax card, tax tools,
 * ITR export, US stocks, funds): the year a link asked for (`?fy=2025`: "as in tax tools" lands on that very year), else
 * the year being filed (pickFy), unless that year has nothing in it and another year has:
 * then the latest year that has something, and `from` the year it was moved from, so the page can say why in one line
 * (movedYearNote). A page never opens on a year of zeros when there is a year with data. */
export function openFy(years: number[], current: number, hasData: (fy: number) => boolean, saved: number | null = null, asked: number | null = null): { fy: number; from: number | null } {
  if (asked != null && years.includes(asked)) return { fy: asked, from: null };
  const fy = pickFy(years, current, hasData, saved);
  if (hasData(fy)) return { fy, from: null };
  const busy = [...years].sort((a, b) => b - a).find(hasData);
  return busy == null ? { fy, from: null } : { fy: busy, from: fy };
}

/** Why a page opened on another year than the shared one: "No trades in FY 2025-26, the year being filed, so this is
 * FY 2024-25, the latest year with trades." */
export function movedYearNote(from: number, to: number, current: number, what: string): string {
  const which = from === current - 1 ? "the year being filed" : from === current ? "this year" : "the year last opened";
  return `No ${what} in ${fyLabel(from)}, ${which}, so this is ${fyLabel(to)}, the latest year with ${what}.`;
}

/** "FY 2025-26". */
export const fyLabel = (fy: number) => `FY ${fy}-${String(fy + 1).slice(2)}`;

/** The year a link carries, from a query string's `fy` ("2025" for FY 2025-26), or null. */
export function askedFy(v: string | null | undefined): number | null {
  const n = Number(v);
  return v && Number.isInteger(n) && n > 1990 && n < 2200 ? n : null;
}

/** A link to a Money page that opens on a given year: `fyLink("/money/tax-tools", 2025)` is "/money/tax-tools?fy=2025". */
export function fyLink(path: string, fy: number): string {
  return `${path}${path.includes("?") ? "&" : "?"}fy=${fy}`;
}

/** A year with anything in the tax report: sales, intraday, F&O business lines or units (the Money home's card and
 * the tax report must call the same years empty). */
export function yearHasTrades(y: { count: number; intraday?: { count: number }; business?: { segments: unknown[] }; units?: unknown }): boolean {
  return y.count > 0 || (y.intraday?.count ?? 0) > 0 || (y.business?.segments.length ?? 0) > 0 || !!y.units;
}

/** Whether the tax report has anything to work from: sales in tradebooks, F&O lines, mutual fund sales or US stock trades
 * (the Money home's card and the tax report must agree on when to ask for tradebooks). */
export function taxHasData(t: { trades: number; business_lines?: number; mf?: { count: number } | null; us_trades?: number }): boolean {
  return t.trades > 0 || (t.business_lines ?? 0) > 0 || (t.mf?.count ?? 0) > 0 || (t.us_trades ?? 0) > 0;
}
