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

/** 2,36,013 units, ₹33,275 billion, 34.2%: the unit as filed, Indian digit grouping. */
export function bizValue(v: number | null | undefined, unit: string | null) {
  if (v == null || !Number.isFinite(v)) return "–";
  const n = v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
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

