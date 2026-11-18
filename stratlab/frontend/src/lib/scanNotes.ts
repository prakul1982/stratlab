/* LIVE14B-009: the bracket a scan match's numbers carry when its averages count the exchange's special sessions ("(the averages count the
 * exchange's special sessions of 1 Feb 2026 and 8 Nov 2026, which some price histories leave out)", 25 words) was repeated on every row.
 * It is said once, as a numbered note under the table, and each row it applies to carries the note's mark. Pure: the unit tests read it. */
const BRACKET = /\s*\((the averages count the exchange's special sessions? of [^)]+, which some price histories leave out)\)/;

/** The rows' numbers without the bracket (with the note's mark, "¹", where it stood), and the notes, each once, in order. */
export function scanNotes(details: (string | null | undefined)[]): { details: (string | null | undefined)[]; notes: string[] } {
  const notes: string[] = [];
  const out = details.map((d) => {
    const m = d ? BRACKET.exec(d) : null;
    if (!d || !m) return d;
    const text = m[1][0].toUpperCase() + m[1].slice(1) + ".";
    if (!notes.includes(text)) notes.push(text);
    return d.replace(BRACKET, MARKS[notes.indexOf(text)] ?? "*");
  });
  return { details: out, notes };
}

export const MARKS = ["¹", "²", "³", "⁴", "⁵"];
