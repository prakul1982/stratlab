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
export function periodName(days: number): string {
  if (days >= 365 && days % 365 < 5) return `${Math.round(days / 365)} year${days >= 730 ? "s" : ""}`;
  if (days >= 28) { const m = Math.round(days / 30.4); return `${m} month${m === 1 ? "" : "s"}`; }
  return `${days} days`;
}

/** An outside link that's safe to put in href: only http(s), never javascript: or data: from a feed. */
export function safeHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:" ? u.href : undefined;
  } catch {
    return undefined;
  }
}

/** When numbers are from, in words: "3 Oct 2026, 14:05" (in the reader's time), or "3 Oct 2026" for a date alone. */
export function asOf(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const day = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const d = day ? new Date(`${iso}T12:00:00`) : new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return day ? d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })
    : d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false });
}

/* ---------- Indian rupee formatting (the one place; see DESIGN.md "Numbers") ----------
 * Everything here takes rupees. For a figure already in crore, multiply by CRORE first. Missing or non-finite values
 * give "–". The minus is always the real minus sign (U+2212). */
export const CRORE = 1e7;
const LAKH = 1e5;
const LAKH_CRORE = 1e12;
const nf = (v: number, dp: number) => v.toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: 0 });
const ok = (v: number | null | undefined): v is number => v != null && Number.isFinite(v);

/** Full rupees in Indian grouping: ₹1,00,000. Whole rupees unless you ask for paise: inr(1849.3, 2) is ₹1,849.30. */
export function inr(v: number | null | undefined, dp = 0): string {
  if (!ok(v)) return "–";
  const s = Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp });
  return `${v < 0 && /[1-9]/.test(s) ? "−" : ""}₹${s}`;
}

/** A scaled figure with the digits it needs: 1.51, 12.4, 925, 3,472. Returns the number's text and its rounded value. */
function scaled(x: number): { text: string; n: number } {
  const dp = x >= 100 ? 0 : x >= 10 ? 1 : 2;
  const n = Number(x.toFixed(dp));
  return { text: nf(n, dp), n };
}

/** Compact rupees in Indian units: ₹925, ₹5.2 lakh, ₹3,472 cr, ₹1.51 lakh cr. */
export function inrCompact(v: number | null | undefined): string {
  if (!ok(v)) return "–";
  const a = Math.abs(v), sign = v < 0 ? "−" : "";
  const cr = a >= CRORE ? scaled(a / CRORE) : null;
  if (a >= LAKH_CRORE || (cr && cr.n >= LAKH)) return `${sign}₹${scaled(a / LAKH_CRORE).text} lakh cr`;
  if (cr) return `${sign}₹${cr.text} cr`;
  if (a >= LAKH) return `${sign}₹${scaled(a / LAKH).text} lakh`;
  return `${sign}₹${nf(Math.round(a), 0)}`;
}

/** The same, with a leading + for gains: +₹296 cr, −₹18 cr. */
export function signedInrCompact(v: number | null | undefined): string {
  if (!ok(v)) return "–";
  return `${v > 0 ? "+" : ""}${inrCompact(v)}`;
}

/** A rupee chart axis: ₹1.45L cr, ₹3,472 cr, ₹5.2L, ₹925. Up to three decimals, so close ticks stay different. */
export function axisInr(v: number | null | undefined): string {
  if (!ok(v)) return "–";
  const a = Math.abs(v), sign = v < 0 ? "−" : "";
  if (a >= LAKH_CRORE) return `${sign}₹${nf(a / LAKH_CRORE, 3)}L cr`;
  if (a >= CRORE) return `${sign}₹${nf(a / CRORE, 2)} cr`;
  if (a >= LAKH) return `${sign}₹${nf(a / LAKH, 2)}L`;
  return `${sign}₹${nf(a, 0)}`;
}

/** A percentage with no sign: 0.21%. (`pct` above is the signed one.) */
export function pctPlain(v: number | null | undefined, dp = 1): string {
  return ok(v) ? `${v.toFixed(dp)}%` : "–";
}

/** A plain number with its sign, in Indian grouping: +1,234 / −5. */
export function signed(v: number | null | undefined, dp = 0): string {
  if (!ok(v)) return "–";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), dp)}`;
}
