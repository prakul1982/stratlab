import { CRORE, bigMoney, inrCompact, pctPlain } from "./format";
import type { Region } from "./research";
import type { DiveRow, Layer, Stat } from "./theme";

/** An amount in the dive's unit ("₹ crore" or "$ million") as the app writes money: ₹1.51 lakh cr, $2.4B. */
export function amount(v: number | null | undefined, region: Region): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return region === "IN" ? inrCompact(v * CRORE) : bigMoney(v * 1e6, "USD");
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
    out.push({ kind: "median", key: "~median", stats: l.stats, label: l.stats_over === "all" ? "Median (all company-wide)" : "Median" });
    out.push({ kind: "range", key: "~range", stats: l.stats, label: "Range" });
  }
  return out;
}
