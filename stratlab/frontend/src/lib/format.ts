import type { Instrument } from "./types";

const SYMBOLS: Record<string, string> = { INR: "₹", USD: "$", USDT: "$", USDC: "$", EUR: "€", GBP: "£", JPY: "¥" };

export const currencySymbol = (c?: string | null) => (c ? SYMBOLS[c] ?? c + " " : "");
const locale = (c?: string | null) => (c === "INR" ? "en-IN" : "en-US");

/** Money in the instrument's currency: ₹5,00,000 or $12,400. */
export function money(v: number | null | undefined, currency?: string | null, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = Math.abs(v).toLocaleString(locale(currency), { maximumFractionDigits: dp, minimumFractionDigits: dp });
  return (v < 0 ? "−" : "") + currencySymbol(currency) + s;
}

/** Prices keep more decimals when they're small (crypto pairs, forex). */
export function price(v: number | null | undefined, currency?: string | null): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  const dp = a >= 1000 ? 2 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8;
  return money(v, currency, dp);
}

/** Prices on a chart axis: whole numbers once they're big, more decimals when small. */
export function priceAxis(v: number, currency?: string | null): string {
  const a = Math.abs(v);
  return money(v, currency, a >= 100 ? 0 : a >= 1 ? 2 : 4);
}

/** Short money for chart axes: ₹5.2L, $12.4k, $1.2M. */
export function moneyShort(v: number, currency?: string | null): string {
  const a = Math.abs(v), sign = v < 0 ? "−" : "", s = currencySymbol(currency);
  if (currency === "INR") {
    if (a >= 1e7) return `${sign}${s}${(a / 1e7).toFixed(1)}Cr`;
    if (a >= 1e5) return `${sign}${s}${(a / 1e5).toFixed(2)}L`;
  } else {
    if (a >= 1e9) return `${sign}${s}${(a / 1e9).toFixed(1)}B`;
    if (a >= 1e6) return `${sign}${s}${(a / 1e6).toFixed(1)}M`;
  }
  if (a >= 1e3) return `${sign}${s}${(a / 1e3).toFixed(1)}k`;
  return `${sign}${s}${a.toFixed(a < 10 ? 2 : 0)}`;
}

export function pct(v: number | null | undefined, dp = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(dp) + "%";
}

export const signClass = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

export function qty(v: number): string {
  if (Number.isInteger(v)) return v.toLocaleString("en-IN");
  return String(+v.toFixed(8));
}

/** Instrument time zone: India in IST, everything else in UTC unless it says otherwise. */
export const tzOf = (inst?: Partial<Instrument> | null) =>
  inst?.tz || (inst?.market === "IN" || !inst?.market ? "Asia/Kolkata" : "UTC");

export function when(iso: string | null | undefined, tz: string, intraday: boolean): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return intraday
    ? d.toLocaleString("en-GB", { timeZone: tz, day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false })
    : d.toLocaleDateString("en-GB", { timeZone: tz, day: "2-digit", month: "short", year: "2-digit" });
}

export function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} d ago`;
  return dateOnly(iso);
}

export const TF_NAME: Record<string, string> = { "1d": "Daily", "1h": "1-hour", "15m": "15-minute", "5m": "5-minute" };
export const TF_UNIT: Record<string, string> = { "1d": "day", "1h": "hour", "15m": "15-min", "5m": "5-min" };

export function periodName(days: number): string {
  if (days >= 365 && days % 365 < 5) return `${Math.round(days / 365)} year${days >= 730 ? "s" : ""}`;
  if (days >= 28) return `${Math.round(days / 30.4)} months`;
  return `${days} days`;
}
