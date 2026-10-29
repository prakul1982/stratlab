/* The one Calendar's "All dates" rows (IA-1 item 3), worked out here, apart from the page, so the unit tests can read them:
 * each source's dated things as one kind of row, and the order they are listed in. */
import { price } from "./format";
import type { IpoRow } from "./ipo";

export type CalType = "results" | "action" | "ipo" | "event" | "money";
export const TYPE_NAME: Record<CalType, string> = { results: "Results", action: "Corporate action", ipo: "IPO", event: "Market event", money: "My money date" };
export const TYPE_CHIP: Record<CalType, string> = { results: "Results", action: "Corporate actions", ipo: "IPOs", event: "Market events", money: "My money dates" };
export const TYPES = Object.keys(TYPE_NAME) as CalType[];

export interface CalRow { id: string; date: string; type: CalType; name: string; to: string; detail: string; mine?: boolean }

/** The dates an IPO has in the window, each its own row: "Opens", "Closes", "Allotment", "Lists". */
export function ipoRows(rows: IpoRow[], from: string, to: string): CalRow[] {
  const steps: [keyof IpoRow, string][] = [["open", "Opens"], ["close", "Closes"], ["allotment", "Allotment"], ["listing", "Lists"]];
  const out: CalRow[] = [];
  for (const r of rows) {
    const band = r.low != null && r.high != null ? `${price(r.low, r.currency, 0)}–${price(r.high, r.currency, 0)}` : r.price != null ? price(r.price, r.currency, 0) : null;
    for (const [k, word] of steps) {
      const d = typeof r[k] === "string" ? (r[k] as string).slice(0, 10) : null;
      if (!d || d < from || d > to) continue;
      out.push({ id: `ipo:${r.id}:${k}`, date: d, type: "ipo", name: r.name, to: `/invest/ipos/${encodeURIComponent(r.id)}`,
        detail: [word, r.segment === "sme" ? "SME" : null, band ? `price band ${band}` : null, r.lot ? `lot ${r.lot.toLocaleString("en-IN")}` : null].filter(Boolean).join(" · ") });
    }
  }
  return out;
}

/** Results and corporate actions with the market events, IPO dates and money dates, in date order (a day's own order: results,
 * actions, IPOs, events, your dates). */
export function mergeRows(parts: CalRow[][]): CalRow[] {
  return parts.flat().sort((a, b) => a.date.localeCompare(b.date) || TYPES.indexOf(a.type) - TYPES.indexOf(b.type) || a.name.localeCompare(b.name));
}

