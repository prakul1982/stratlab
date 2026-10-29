/* How business-update figures are written: the filed unit with Indian digit grouping, plain signed changes (a change, not a
 * verdict), and the period and filing day. */

/** "Sep 2026", or "Q2 FY27" for a quarter (Indian financial year). */
export function periodName(p: string, span: "month" | "quarter" = "month") {
  const [y, m] = p.split("-").map(Number);
  if (!y || !m) return p;
  if (span === "quarter") {
    const q = ({ 6: 1, 9: 2, 12: 3, 3: 4 } as Record<number, number>)[m];
    if (q) return `Q${q} FY${String((m >= 4 ? y + 1 : y) % 100).padStart(2, "0")}`;
  }
  return `${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]} ${y}`;
}

/** The month rows of a side-by-side table (newest first) with each run of two or more months that no company has a figure
 * for folded into one row, "gap:<newest>:<oldest>:<months>", so a table never runs down a screen of dashes. A single empty
 * month stays a row of its own (a missing month between two filed ones is worth seeing). */
export function foldEmptyMonths(periods: string[], hasFigure: (period: string) => boolean): string[] {
  const out: string[] = [];
  for (let i = 0; i < periods.length;) {
    if (hasFigure(periods[i])) { out.push(periods[i++]); continue; }
    let j = i;
    while (j < periods.length && !hasFigure(periods[j])) j++;
    out.push(j - i >= 2 ? `gap:${periods[i]}:${periods[j - 1]}:${j - i}` : periods[i]);
    i = j;
  }
  return out;
}

/** 2,36,013 units, ₹33,275 billion, 34.2%: the unit as filed, Indian digit grouping. */
export function bizValue(v: number | null | undefined, unit: string | null) {
  if (v == null || !Number.isFinite(v)) return "–";
  const n = v.toLocaleString("en-IN", { maximumFractionDigits: 2 }).replace(/^-/, "−");   // the real minus
  const u = (unit ?? "").trim();
  if (u === "%") return `${n}%`;
  if (u.startsWith("₹")) return `₹${n} ${u.slice(1).trim()}`.trim();
  return `${n} ${u}`.trim();
}

/** "+24.4%", or "+1.2 pts" for a figure that is itself a percent. Plain text, no colour: a change, not a verdict. */
export function bizChange(c: number | null | undefined, unit: string | null) {
  if (c == null) return "–";
  const s = c > 0 ? "+" : c < 0 ? "−" : "";
  return (unit ?? "").includes("%") ? `${s}${Math.abs(c).toFixed(2)} pts` : `${s}${Math.abs(c).toFixed(1)}%`;
}


/** A filing's subject as a line: all-capitals subjects ("RELIANCE'S JIO STUDIOS BETS ON...") in sentence case, and an unmatched quote mark left at the
 *  end ("...The Hundred.\"") dropped (LIVE1A-064). Mixed-case subjects are only trimmed. */
export function tidyTitle(title: string): string {
  let t: string = title.replace(/\s+/g, " ").trim();
  const last = t.charAt(t.length - 1);
  if (last === '"' && (t.match(/"/g) ?? []).length % 2 === 1) t = t.slice(0, -1).trimEnd();
  const letters = t.replace(/[^A-Za-z]/g, "");
  if (letters.length > 12 && letters.replace(/[^A-Z]/g, "").length / letters.length > 0.7) {
    t = t.toLowerCase().replace(/(^|[.!?]\s+)([a-z])/g, (_m: string, a: string, b: string) => a + b.toUpperCase());
  }
  return t;
}
