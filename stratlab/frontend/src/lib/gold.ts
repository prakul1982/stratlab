/* One gold price across the pages (DG-060), as words: a pure function (unit/review-dg1.test.mjs reads it). */

/** The gold price in India the Money pages use (/money/gold: Net worth's gold and gold bonds), and the import duty between it
 * and the world price. */
export type IndiaGold = { per_10g: number | null; as_of: string | null; duty_pct: number; duty_note: string };

/** The gold tile's line in rupees (DG-060, DP2-040: My space said ₹1,22,042 per 10 g, the world price at the dollar rate,
 * while Net worth valued gold at ₹1,42,150, about 14% apart with nothing saying why): India's price first, the one Net worth
 * uses, then the world price at the dollar rate with the duty that is most of the gap. */
export function goldLine(india: IndiaGold | null | undefined, world10g: number | null, inr: (v: number) => string): string | null {
  if (india?.per_10g) {
    const gap = world10g ? ` The world price at the dollar rate is ${inr(world10g)}; ${india.duty_note}.` : "";
    return `${inr(india.per_10g)} per 10 g in India, the price Net worth uses.${gap}`;
  }
  return world10g ? `${inr(world10g)} per 10 g at the world price and dollar rate, before India's import duty and GST` : null;
}

/** goldLine in two parts: India's price (one short line) and the world price with the duty (for behind an (i)), so a home card can
 * show the first and keep the rest one tap away (VR1-002). `short + " " + more` is goldLine. */
export function goldLineParts(india: IndiaGold | null | undefined, world10g: number | null, inr: (v: number) => string): { short: string; more: string | null } | null {
  const line = goldLine(india, world10g, inr);
  if (!line) return null;
  if (!india?.per_10g || !world10g) return { short: line, more: null };
  const i = line.indexOf(". ");
  return i < 0 ? { short: line, more: null } : { short: line.slice(0, i + 1), more: line.slice(i + 2) };
}
