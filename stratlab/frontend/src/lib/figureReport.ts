/* "Report an error in this figure" (owner, 12 Nov): the words the dialog opens with, kept free of React so the unit tests read them. */

/** A column heading that names a period: "FY26", "Q2 FY27", "2025", "Mar 2026", "TTM". */
export const isPeriod = (h: string): boolean => /^(?:FY\s?\d{2,4}|Q[1-4]\b.*|H[12]\b.*|(?:19|20)\d{2}(?:-\d{2})?|[A-Z][a-z]{2}\s(?:19|20)\d{2}|TTM|LTM)$/i.test(h.trim());

/** Which of a row's figures the dialog starts on, and what it is: in a table of periods the latest (the last column) with its period,
 * else the first figure with its column's name. `at` picks another one. */
export function figureChoice(choices: [string, string][], at?: number): { index: number; column: string | null; value: string | null; period: string | null } {
  if (!choices.length) return { index: 0, column: null, value: null, period: null };
  const periods = choices.every(([h]) => isPeriod(h));
  const i = at != null && at >= 0 && at < choices.length ? at : periods ? choices.length - 1 : 0;
  const [column, value] = choices[i];
  // a lone "Value" or "Now" column names nothing: the row's name is the figure's
  const plain = choices.length === 1 && /^(value|now|figure|latest)$/i.test(column.trim());
  return { index: i, column: plain ? null : column, value, period: periods ? column : null };
}

/** The page's own heading, else the window's title less the site's name: "Tata Consultancy Services". */
export function pageName(doc: { querySelector: (s: string) => { textContent: string | null } | null; title: string }): string {
  const h = doc.querySelector("main h1")?.textContent?.trim();
  return (h || doc.title.replace(/\s*[|·–-]\s*StratLab.*$/i, "").trim()).slice(0, 80);
}
