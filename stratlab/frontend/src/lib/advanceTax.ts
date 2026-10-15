/* Section 234B on the Tax tools page: what the interest figure runs to, in a few words beside it. */

type B234 = { months: number; until: string; unpaid?: number; fully_paid?: boolean; to_today?: boolean; self_assessment?: number };

/** "for 2 months, to May 2026; paid in full, so it stops there", or that some is still unpaid and it grows each month. */
export function b234Note(b: B234, fmt: (v: number) => string): string {
  const month = new Date(`${b.until}T00:00:00`).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const span = `${b.months} month${b.months === 1 ? "" : "s"}, to ${month}`;
  if (b.fully_paid && (b.self_assessment ?? 0) > 0) return `${span}; paid in full, so it stops there`;
  if (b.to_today) return `${span}; ${fmt(b.unpaid ?? 0)} still unpaid, so it goes up each month until paid`;
  return `${span}, as if the rest is paid by the return's due date`;
}
