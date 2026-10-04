/* Derivatives positioning (Trade): the shapes the API sends and the few words and number formats the page and its
 * cards share. Facts only: what was open or traded, never what it might mean. */

export type PartStatus = { status: "ok" | "pending" | "none"; as_of: string | null; expected: string | null; today?: "pending";
  error?: string | null; checked?: string | null };

/** One participant's row: contracts long and short, with the change from the day before as `<key>_chg`. */
export type PRow = { id: "client" | "dii" | "fii" | "pro" | "total"; label: string } & Record<string, number | string | null | undefined>;

export type Flow = { buy: number | null; sell: number | null; net: number | null };
export type PcrRow = { name: string; exchange: string; expiry?: string; pcr_oi?: number | null; pcr_vol?: number | null; pcr_near?: number | null;
  spot?: number | null; source: "live" | "recorded" | null; as_of?: string };

export type Summary = {
  participants: PartStatus & { oi: PRow[]; vol?: PRow[]; prev: string | null };
  cash: PartStatus & { fii?: Flow; dii?: Flow };
  pcr: PcrRow[] | null; names: string[]; full: boolean; note: string; today: string; plan_needed: string;
};

export type StrikeRow = { strike: number; call_oi: number | null; put_oi: number | null; call_vol: number | null; put_vol: number | null;
  call_chg: number | null; put_chg: number | null };
export type IvStats = { days: number; need: number; percentile: number | null; rank: number | null; low: number | null; high: number | null };
export type ChainFacts = {
  name: string; exchange: string; choice: string; source: "live" | "recorded" | null; as_of?: string; expiry?: string; expiries?: string[];
  spot?: number | null; rows: StrikeRow[]; change_from?: string | null; strikes_counted?: number;
  pcr?: { oi: number | null; vol: number | null; call_oi: number; put_oi: number; call_vol: number | null; put_vol: number | null };
  pcr_near?: number | null; pcr_near_vol?: number | null; max_pain?: number | null; atm_iv?: number | null; atm?: number | null;
  top?: { call: { strike: number; oi: number } | null; put: { strike: number; oi: number } | null };
  iv: IvStats | null; note: string; plan_needed: string;
};

export type PartPoint = { day: string } & Record<"client" | "dii" | "fii" | "pro", Record<string, number | null>>;
export type CashPoint = { day: string; fii: number | null; dii: number | null };
export type ChainPoint = { day: string; expiry: string | null; pcr_oi: number | null; pcr_vol: number | null; max_pain: number | null;
  atm_iv: number | null; spot: number | null };

export const PARTICIPANTS: [PRow["id"], string][] = [["client", "Client"], ["dii", "DII"], ["fii", "FII"], ["pro", "Pro"]];
export const RANGES: [string, string][] = [["3m", "3M"], ["6m", "6M"], ["1y", "1Y"], ["all", "All"]];

/** A count of contracts, Indian grouping: 1,23,456. */
export const contracts = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toLocaleString("en-IN"));
/** A short count for chart axes: 12.3L, 1.2Cr. */
export function contractsShort(v: number): string {
  const a = Math.abs(v), s = v < 0 ? "−" : "";
  if (a >= 1e7) return `${s}${(a / 1e7).toFixed(1)}Cr`;
  if (a >= 1e5) return `${s}${(a / 1e5).toFixed(1)}L`;
  if (a >= 1e3) return `${s}${(a / 1e3).toFixed(0)}K`;
  return `${s}${Math.round(a)}`;
}
/** A signed change: +1,234 or −1,234. */
export const signed = (v: number | null | undefined) => (v == null ? "–" : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(Math.round(v)).toLocaleString("en-IN")}`);
/** ₹ crore, signed for a net figure. */
export const crore = (v: number | null | undefined, sign = false) =>
  v == null ? "–" : `${sign && v > 0 ? "+" : v < 0 ? "−" : ""}₹${Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })} cr`;
export const ratio = (v: number | null | undefined) => (v == null ? "–" : v.toFixed(2));
/** Why a part's number is missing, in a few words for the card that shows it (never a bare dash). */
export const missingWhy = (p: PartStatus | undefined) => (p?.error ? "Couldn't be read just now" : "Not published yet");
export const strike = (v: number | null | undefined) => (v == null ? "–" : v.toLocaleString("en-IN", { maximumFractionDigits: 2 }));

/** "3 Oct 2026" from an ISO day. */
export function dayName(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso.slice(0, 10) + "T00:00:00");
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}
/** A recording's time in India, whatever the reader's own zone: "1 Oct, 3:25 pm IST". */
export function istTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${d.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST`;
}
export const shortDay = (iso: string) => new Date(iso.slice(0, 10) + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short" });

/** The status line for one of the exchange's daily numbers. */
export function statusLine(s: PartStatus, what: string): string {
  if (s.status === "none") return `No ${what} stored yet. The exchange publishes them each trading evening, usually between 6:30 and 8 pm.`;
  const base = `As of ${dayName(s.as_of)}.`;
  if (s.status === "pending") return `${base} ${dayName(s.expected)}'s ${what} aren't published yet.`;
  if (s.today === "pending") return `${base} Today's ${what} aren't published yet: the exchange usually puts them out between 6:30 and 8 pm.`;
  return base;
}
