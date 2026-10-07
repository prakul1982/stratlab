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

/** Size steps of a short figure: [divisor, suffix, decimals], largest first. */
export const SHORT_INR: [number, string, number][] = [[1e7, "Cr", 1], [1e5, "L", 2], [1e3, "k", 1]];
export const SHORT_INTL: [number, string, number][] = [[1e9, "B", 1], [1e6, "M", 1], [1e3, "k", 1]];

/** The step a size is written in. A size that rounds up to the next step's size is written in that step: 99,999 is
 * ₹1.00L, not ₹100.0k; 9,999,999 is ₹1.0Cr, not ₹100.00L; 999,999 dollars is $1.0M, not $1000.0k. */
export function shortStep(a: number, steps: [number, string, number][]): [number, string, number] | null {
  for (let i = 0; i < steps.length; i++) {
    const [div, , dp] = steps[i];
    if (a < div) continue;
    const up = i > 0 ? steps[i - 1] : null;
    return up && Number((a / div).toFixed(dp)) >= up[0] / div ? up : steps[i];
  }
  return null;
}

/** Short money for chart axes: ₹5.2L, $12.4k, $1.2M. */
export function moneyShort(v: number, currency?: string | null): string {
  const a = Math.abs(v), sign = v < 0 ? "−" : "", s = currencySymbol(currency);
  const step = shortStep(a, currency === "INR" ? SHORT_INR : SHORT_INTL);
  if (step) return `${sign}${s}${(a / step[0]).toFixed(step[2])}${step[1]}`;
  return `${sign}${s}${a.toFixed(a < 10 ? 2 : 0)}`;
}

/** Big money in the units people say: $4.31T, $12.4B, ₹1.51 lakh cr, ₹8,500 cr. */
export function bigMoney(v: number | null | undefined, currency: string): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const s = currencySymbol(currency);
  if (currency === "INR") return inrCompact(v);
  const a = Math.abs(v);
  const step = shortStep(a, [[1e12, "T", 2], [1e9, "B", 1], [1e6, "M", 0]]);      // $999.96B reads $1.00T, not $1000.0B
  if (step) return `${v < 0 ? "-" : ""}${s}${(a / step[0]).toFixed(step[2])}${step[1]}`;
  return `${s}${Math.round(v).toLocaleString()}`;
}

export function pct(v: number | null | undefined, dp = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const shown = Math.abs(v).toFixed(dp);
  return (+shown === 0 ? "" : v > 0 ? "+" : "−") + shown + "%";           // a change that rounds to nothing has no sign: "0.0%", not "−0.0%"
}

export const signClass = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

export function qty(v: number): string {
  if (Number.isInteger(v)) return v.toLocaleString("en-IN");
  return String(+v.toFixed(8));
}

/** Instrument time zone: India in IST, everything else in UTC unless it says otherwise. */
export const tzOf = (inst?: Partial<Instrument> | null) =>
  inst?.tz || (inst?.market === "IN" || !inst?.market ? "Asia/Kolkata" : "UTC");

/** The one date format, day first, as My space shows it: "6 Oct" and "6 Oct 2026". Every date a person reads goes through
 * `fmtDate` (or `fmtDateTime` for a moment). A plain "YYYY-MM-DD" is a calendar day and is never moved by a time zone. */
export type DateInput = string | number | Date | null | undefined;
export interface DateOpts { year?: boolean; weekday?: boolean; tz?: string }

const CALENDAR_DAY = /^(\d{4})-(\d{2})-(\d{2})(?:T00:00:00)?$/;

function toDate(v: DateInput): Date | null {
  if (v == null || v === "") return null;
  const m = typeof v === "string" ? CALENDAR_DAY.exec(v) : null;
  if (m) return new Date(+m[1], +m[2] - 1, +m[3], 12);
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "6 Oct 2026", or "6 Oct" with `year: false`; `weekday` gives "Tue, 6 Oct 2026". Missing or invalid gives "–". */
export function fmtDate(v: DateInput, o: DateOpts = {}): string {
  const d = toDate(v);
  if (!d) return "–";
  const calendar = typeof v === "string" && CALENDAR_DAY.test(v);
  return d.toLocaleDateString("en-GB", { ...(!calendar && o.tz ? { timeZone: o.tz } : {}), ...(o.weekday ? { weekday: "short" } : {}),
    day: "numeric", month: "short", ...(o.year === false ? {} : { year: "numeric" }) }).replace(/\bSept\b/, "Sep");
}

/** A moment: "6 Oct 2026, 14:05" (24-hour), or "6 Oct, 14:05" with `year: false`; `seconds` adds ":07". */
export function fmtDateTime(v: DateInput, o: DateOpts & { seconds?: boolean } = {}): string {
  const d = toDate(v);
  if (!d) return "–";
  const t = d.toLocaleTimeString("en-GB", { ...(o.tz ? { timeZone: o.tz } : {}), hour: "2-digit", minute: "2-digit", ...(o.seconds ? { second: "2-digit" } : {}), hour12: false });
  return `${fmtDate(d, o)}, ${t}`;
}

export function when(iso: string | null | undefined, tz: string, intraday: boolean): string {
  if (!iso) return "–";
  return intraday ? fmtDateTime(iso, { tz, year: false }) : fmtDate(iso, { tz });
}

/** A date as written ("2025-03-10") is a calendar day, not an instant: `new Date("2025-03-10")` is midnight UTC, which a
 * reader west of Greenwich (every US reader) sees as the 9th. A date with a time keeps its instant. */
export function asDate(iso: string): Date {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(iso);
}

export function dateOnly(iso: string | null | undefined): string {
  return iso ? fmtDate(iso) : "–";
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
  const d = toDate(iso);
  if (!d) return null;
  return day ? fmtDate(iso) : fmtDateTime(d);
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

/** Up or down for a gain or loss that is the user's own (a holding's profit, a fund's gain): for a Stat's `tone`, or
 * `k-${signTone(v)}` as a class. Nothing for zero or a missing value. Never use it on a market-wide change. */
export function signTone(v: number | null | undefined): "up" | "down" | undefined {
  return ok(v) ? (v > 0 ? "up" : v < 0 ? "down" : undefined) : undefined;
}

/** A plain number with its sign, in Indian grouping: +1,234 / −5. */
export function signed(v: number | null | undefined, dp = 0): string {
  if (!ok(v)) return "–";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${nf(Math.abs(v), dp)}`;
}

/** The first name to greet by, from what the sign-in gave the profile (a first or given name, else the first word of the
 * full name). Nothing when the profile has no name, or what it holds is an email address or has digits in it. A name typed
 * in capitals or all lower case is written with a capital first letter. */
export function firstName(meta: Record<string, unknown> | null | undefined): string {
  const m = meta ?? {};
  for (const k of ["given_name", "first_name", "full_name", "name"]) {
    const v = typeof m[k] === "string" ? (m[k] as string).trim() : "";
    const word = v.split(/\s+/)[0] ?? "";
    if (!word || /[@\d]/.test(word)) continue;
    return word === word.toUpperCase() || word === word.toLowerCase() ? word.charAt(0).toUpperCase() + word.slice(1).toLowerCase() : word;
  }
  return "";
}

/** Where a saved list of holdings came from, in words ("your Groww file", "your statements", "your Zerodha login"). */
export function sourceWords(source: string): string {
  if (source === "Manual") return "your own entries";
  if (source === "CSV") return "a CSV file";
  if (source === "Statement") return "your statements";
  if (source === "Zerodha Kite") return "your Zerodha login";
  if (source === "Interactive Brokers") return "your Interactive Brokers account";
  return `your ${source} file`;
}
