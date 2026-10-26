/* US share sales beside the Indian short-term and long-term totals: the tax report and the long-term exemption tracker show
 * the Indian figures on their own (US shares follow their own rules, and the ₹1.25 lakh exemption isn't for them), with the
 * US figures in a line of their own. */

/** The labels of the short-term and long-term totals: "of Indian shares and funds" when US sales are kept apart. */
export function gainLabel(term: "st" | "lt", hasUs: boolean, net = true): string {
  const base = term === "st" ? "Short-term gains" : "Long-term gains";
  return `${base}${hasUs ? ", Indian shares and funds" : ""}${net ? " (net)" : ""}`;
}

/** The line under them with the US shares' own figures, or null without US sales. */
export function usSharesNote(st: number | null | undefined, lt: number | null | undefined, fmt: (v: number) => string): string | null {
  if (st == null && lt == null) return null;
  return `US shares, kept apart from these totals: short-term ${fmt(st ?? 0)}, long-term ${fmt(lt ?? 0)} (net).`;
}
