import { money } from "./format";

/** ui100: an amount a share (a dividend), with the decimals it needs: two at least, up to four for a small one, never trailing zeros past
 *  the second ("₹0.75 a share", not "₹0.7500"; "₹0.0125" stays). Its own file, not format.ts: format rides in the landing page's
 *  download, whose budget (R5V-020, 450 KB) had no room. */
export function perShare(v: number | null | undefined, currency?: string | null): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const dp = [2, 3, 4].find((d) => Math.abs(+v.toFixed(d) - v) < 1e-9) ?? 4;
  return money(v, currency, dp);
}
