/* CSV files of the tables people see (EXPORT, 4 Nov: "check wherever we can give this option of exporting the data and provide
 * it"). One builder for every table's download, so each file reads the same in a spreadsheet: a header row, numbers as numbers
 * (no grouping, no unit, a plain "-" for a minus; the unit goes in the column's name), dates as ISO days (2026-11-04), an empty
 * cell for a figure that isn't there, and text that a spreadsheet would run as a formula written as text. No imports: the unit
 * tests load this file as it is. The file is saved through lib/share.ts download() (downloadCsv there). */

export type CsvValue = string | number | boolean | Date | null | undefined;

/** A cell a spreadsheet would run as a formula when the file is opened (= + - @, or a tab or CR in front). */
const FORMULA = /^[=+\-@\t\r]/;

/** The ISO form of a moment: the day alone when it falls on midnight UTC (a calendar day), else the full time in UTC. */
function isoOf(d: Date): string {
  if (Number.isNaN(d.getTime())) return "";
  const iso = d.toISOString();
  return iso.endsWith("T00:00:00.000Z") ? iso.slice(0, 10) : iso.replace(/\.\d{3}Z$/, "Z");
}

/** One cell as written in the file. A number stays a number (rounded to 12 significant digits, so 0.1 + 0.2 is 0.3); text is quoted
 * when it holds a comma, a quote or a line break; text that starts like a formula gets a leading ' so it is read as text. */
export function csvCell(v: CsvValue): string {
  if (v == null) return "";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "";
    const n = Number(v.toPrecision(12));
    return Object.is(n, -0) ? "0" : String(n);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (v instanceof Date) return isoOf(v);
  let s = String(v).replace(/−/g, "-");
  if (FORMULA.test(s)) s = "'" + s;
  return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

/** The whole file: a byte-order mark first (so a spreadsheet reads ₹ and names in any script as UTF-8), the header, then a row a
 * line, lines ended CRLF as RFC 4180 says. */
export function toCsv(head: string[], rows: CsvValue[][]): string {
  return "﻿" + [head, ...rows].map((r) => r.map(csvCell).join(",")).join("\r\n") + "\r\n";
}

/** What a table shows in a cell, read back as a value: "1,23,456.5", "−3.2" and "+4.1" are numbers, "–" or "" is empty, anything
 * else (a name, "₹1.51 lakh cr", "12.4x") stays the text the table shows. A ▲ or ▼ in front of a change is left off the number. */
export function shownValue(text: string): CsvValue {
  const t = text.replace(/\s+/g, " ").trim();
  if (t === "" || t === "–" || t === "—" || t === "-") return null;
  const n = plainNumber(t);
  return n ?? t;
}

/** A plain number as tables write it, or null: grouping commas (Indian or Western), the real minus, a sign, a ▲ or ▼. */
export function plainNumber(t: string): number | null {
  const m = /^[▲▼]?\s?([+−-]?)(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+(?:\.\d+)?)$/.exec(t.trim());
  if (!m) return null;
  const n = Number(m[2].replace(/,/g, ""));
  return m[1] === "-" || m[1] === "−" ? -n : n;
}

/** How a whole column of shown text is best written: as percent figures (every filled cell is "12.5%"), as rupee or dollar amounts
 * (every filled cell is "₹1,234" or "$12.50", with no word unit after), or as it is. The unit then goes in the column's name. */
export function columnOf(texts: string[]): { suffix: string; values: CsvValue[] } {
  const filled = texts.map((t) => t.replace(/\s+/g, " ").trim()).map((t) => (t === "–" || t === "—" ? "" : t));
  const all = (re: RegExp) => filled.some((t) => t) && filled.every((t) => !t || re.test(t));
  const strip = (re: RegExp) => filled.map((t) => (t ? plainNumber(t.replace(re, "")) : null));
  if (all(/^[▲▼]?\s?[+−-]?[\d,]+(\.\d+)?\s?%$/)) return { suffix: " (%)", values: strip(/\s?%$/) };
  if (all(/^[▲▼]?\s?[+−-]?₹\s?[\d,]+(\.\d+)?$/)) return { suffix: " (₹)", values: strip(/₹\s?/) };
  if (all(/^[▲▼]?\s?[+−-]?\$\s?[\d,]+(\.\d+)?$/)) return { suffix: " ($)", values: strip(/\$\s?/) };
  return { suffix: "", values: texts.map(shownValue) };
}

/** A file name: "stratlab-" and the words of `stem` in lower case with hyphens, then the day, then ".csv". */
export function csvName(stem: string, day: string): string {
  const words = stem.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/&/g, " and ").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80);
  return `stratlab-${words || "table"}${day ? `-${day}` : ""}.csv`;
}
