/* The one Calendar's "All dates" rows (IA-1 item 3), worked out here, apart from the page, so the unit tests can read them:
 * each source's dated things as one kind of row, and the order they are listed in. */
import { fmtDate, perShare, price } from "./format";
import type { IpoRow } from "./ipo";

export type CalType = "results" | "action" | "ipo" | "event" | "money";
export const TYPE_NAME: Record<CalType, string> = { results: "Results", action: "Corporate action", ipo: "IPO", event: "Market event", money: "My money date" };
export const TYPE_CHIP: Record<CalType, string> = { results: "Results", action: "Corporate actions", ipo: "IPOs", event: "Market events", money: "My money dates" };
export const TYPES = Object.keys(TYPE_NAME) as CalType[];

export interface CalRow { id: string; date: string; type: CalType; name: string; to: string; detail: string; mine?: boolean; symbol?: string }

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


/** What the Calendar reads of a results day and of a corporate action (the research tables' own rows). */
export interface ResultIn { region: string; symbol: string; name: string | null; date: string; purpose?: string; when?: string | null; mine?: boolean }
export interface ActionIn { id: string; region: string; symbol: string; name: string | null; ex_date: string; kind: string; label: string; amount: number | null; currency: string; record_date: string | null; mine?: boolean }

const companyTo = (region: string, symbol: string) => `/research/${region}/${encodeURIComponent(symbol)}`;

/** Results days from `today` on, each its own row: the company, its page, and what the exchange filing says it is for. */
export function resultRows(rows: ResultIn[], today: string): CalRow[] {
  return rows.filter((r) => r.date >= today).map((r) => ({
    id: `res:${r.region}:${r.symbol}:${r.date}`, date: r.date.slice(0, 10), type: "results" as const, name: r.name ?? r.symbol, symbol: r.symbol, mine: r.mine,
    to: companyTo(r.region, r.symbol), detail: [r.purpose, r.when].filter(Boolean).join(" · ") }));
}

/** Corporate actions by ex-date up to `until`: the action, a dividend's amount a share, and the record date. */
export function actionRows(rows: ActionIn[], until: string): CalRow[] {
  return rows.filter((a) => a.ex_date <= until).map((a) => ({
    id: `act:${a.id}`, date: a.ex_date.slice(0, 10), type: "action" as const, name: a.name ?? a.symbol, symbol: a.symbol, mine: a.mine, to: companyTo(a.region, a.symbol),
    detail: [`Ex-date: ${a.label}`, a.kind === "dividend" && a.amount ? `${perShare(a.amount, a.currency)} a share` : null,
      a.record_date ? `record date ${fmtDate(a.record_date.slice(0, 10), { year: false })}` : null].filter(Boolean).join(" · ") }));
}

/** The Calendar's "My stocks" dates (inv96: also the Invest home's Coming up): the person's stocks' results days and corporate actions
 * (dividends, bonuses, splits, buybacks, rights, demergers, with their record dates) from `today` to `until`, in the Calendar's order. */
export function myStockRows(results: ResultIn[], actions: ActionIn[], today: string, until: string): CalRow[] {
  return mergeRows([resultRows(results, today), actionRows(actions, until)]);
}
