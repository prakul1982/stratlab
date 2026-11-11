import { CRORE, bigMoney, pctPlain } from "./format";
import type { Region } from "./research";
import type { DiveRow, Layer, Stat } from "./theme";

/** An amount in the dive's unit ("₹ crore" or "$ million") as the app writes money: ₹1.51 lakh cr, $2.4B. The one rule for big money
 * (bigMoney), as the company page, its public page, the screens and Compare write a market value (LIVE3-018: "₹11.4 lakh cr" here
 * beside "₹11.38 lakh cr" there). */
export function amount(v: number | null | undefined, region: Region): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return bigMoney(region === "IN" ? v * CRORE : v * 1e6, region === "IN" ? "INR" : "USD");
}
/** A margin or rate in percent, one decimal, the real minus. */
export const pc = (v: number | null | undefined, dp = 1) => pctPlain(v, dp).replace("-", "−");
/** A multiple: 12.4x. */
export const times = (v: number | null | undefined, dp = 1) => (v == null || !Number.isFinite(v) ? "–" : `${v.toFixed(dp)}x`);
/** A change in percentage points: +2.0 pts, −0.5 pts. */
export const points = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(1)} pts`);
/** "48.0% to 50.0%" for a range; one value when they are the same. */
export const span = (s: Stat | null | undefined, f: (v: number) => string = (v) => pc(v)) => (!s ? "–" : s.min === s.max ? f(s.min) : `${f(s.min)} to ${f(s.max)}`);

/** The table of one layer: its companies, then the layer's median and range as the last two rows. */
export interface LayerLine { kind: "company" | "median" | "range"; key: string; row?: DiveRow; label?: string; stats?: Layer["stats"] }
export function layerLines(l: Layer): LayerLine[] {
  const out: LayerLine[] = l.companies.map((row) => ({ kind: "company", key: row.symbol, row }));
  if (l.companies.length > 0) {
    const n = l.stats.ebitda?.n ?? l.stats.net?.n ?? 0;
    out.push({ kind: "median", key: "~median", stats: l.stats, label: `Median of ${n} compan${n === 1 ? "y" : "ies"}${l.stats_over === "all" ? " (company-wide figures)" : ""}` });
    if (n > 1) out.push({ kind: "range", key: "~range", stats: l.stats, label: "Range" });
  }
  return out;
}

/** The heading of the search box's list of themes StratLab has already mapped (LIVE6-012). It is one shared library, kept once for
 *  everyone, not this person's reading history: it never says "Already read" or "read <date>" (an account that never opened a theme was
 *  shown "Already read: Cybersecurity · US, read 11 Nov"); the date is when the stored map was last updated. */
export const LIBRARY_HEAD = "Ready to open:";
export function libraryLabel(i: { name: string; region: string; at: string | null }, fmtDay: (iso: string) => string): string {
  const where = ({ IN: "India", US: "US" } as Record<string, string>)[i.region] ?? i.region;
  return `${i.name} · ${where}${i.at ? `, updated ${fmtDay(i.at.slice(0, 10))}` : ""}`;
}
