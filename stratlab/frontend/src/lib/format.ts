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

/** Prices keep more decimals when they're small (crypto pairs, forex). `dp` fixes the decimals (see `priceDp`). */
export function price(v: number | null | undefined, currency?: string | null, dp?: number): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const a = Math.abs(v);
  return money(v, currency, dp ?? (a >= 1000 ? 2 : a >= 1 ? 2 : a >= 0.01 ? 4 : 8));
}

/** The decimals an instrument's prices are quoted in, where its size alone doesn't say: spot forex in 5 (a pipette;
 *  yen pairs 3), currency futures in 4. Undefined means "by size", as `price` does. */
export function priceDp(inst?: { market?: string; symbol?: string; currency?: string } | null): number | undefined {
  if (inst?.market === "FX") return /JPY/.test(inst.symbol ?? "") || inst.currency === "JPY" ? 3 : 5;
  if (inst?.market === "CDS") return 4;
  return undefined;
}

/** A fall from a peak, as a negative percentage with one decimal; one that rounds to nothing is "0%", never "−0%". */
export function fall(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const shown = Math.abs(v).toFixed(1);
  return +shown === 0 ? "0%" : `−${shown}%`;
}

/** A charge in a cost list: whole units, or cents and paise when it's under one unit, so nothing reads "−₹0". */
export function charge(v: number, currency?: string | null): string {
  const a = Math.abs(v);
  if (a === 0) return money(0, currency);
  return "−" + money(a, currency, a < 1 ? 2 : 0);
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
  return `${s}${Math.round(v).toLocaleString("en-US")}`;            // a dollar figure is grouped the international way, whatever the reader's locale
}

export function pct(v: number | null | undefined, dp = 1): string {
  if (v == null || !Number.isFinite(v)) return "–";
  const shown = Math.abs(v).toFixed(dp);
  return (+shown === 0 ? "" : v > 0 ? "+" : "−") + shown + "%";           // a change that rounds to nothing has no sign: "0.0%", not "−0.0%"
}

export const signClass = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "pos" : v < 0 ? "neg" : "");

/** A quantity. With `step` (the instrument's smallest unit, 0.00000001 BTC) a fractional quantity keeps that many
 *  decimals, so a column lines up (0.05013551, 0.05091380). */
export function qty(v: number, step?: number): string {
  if (step && step < 1) {
    const dp = Math.min(8, Math.max(0, Math.ceil(-Math.log10(step) - 1e-9)));
    return v.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }
  if (Number.isInteger(v)) return v.toLocaleString("en-IN");
  return String(+v.toFixed(8));
}

/** Instrument time zone: India in IST, everything else in UTC unless it says otherwise. */
export const tzOf = (inst?: Partial<Instrument> | null) =>
  inst?.tz || (inst?.market === "IN" || !inst?.market ? "Asia/Kolkata" : "UTC");

/* ---------- Time zones (see DESIGN.md "Dates") ----------
 * A market's times are written in that market's own zone, with the zone's name: "14:05 IST", "09:30 ET". The reader's
 * own events (a trial's end, a page coming back) may be in the reader's zone, and are labelled too. */
export const IST = "Asia/Kolkata";
export const ET = "America/New_York";

/** The zone a market's times are written in: India's exchanges IST, US exchanges ET, crypto UTC. */
export function marketTz(market?: string | null): string {
  if (market === "US") return ET;
  if (market === "CRYPTO" || market === "crypto") return "UTC";
  return IST;
}

/** The reader's own zone, as the browser reports it. */
export function localTz(): string {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"; } catch { return "UTC"; }
}

const ZONE_NAMES: Record<string, string> = {
  "Asia/Kolkata": "IST", "Asia/Calcutta": "IST", "America/New_York": "ET", "US/Eastern": "ET", "America/Chicago": "CT",
  "UTC": "UTC", "Etc/UTC": "UTC", "Etc/GMT": "UTC", "GMT": "UTC", "Europe/London": "UK time", "Asia/Tokyo": "JST",
  "Asia/Singapore": "SGT", "Asia/Hong_Kong": "HKT", "Asia/Dubai": "GST",
};

/** A zone's short name for a reader: "IST", "ET", "UTC"; any other zone gets the browser's short name ("CEST",
 * "GMT+9"). No zone given means the reader's own. */
export function tzLabel(tz?: string | null, at: Date = new Date()): string {
  const z = tz || localTz();
  if (ZONE_NAMES[z]) return ZONE_NAMES[z];
  try {
    const part = new Intl.DateTimeFormat("en-GB", { timeZone: z, timeZoneName: "short" }).formatToParts(at).find((x) => x.type === "timeZoneName");
    return part?.value || z;
  } catch {
    return z;
  }
}

/** The one date format, day first, as My space shows it: "6 Oct" and "6 Oct 2026". Every date a person reads goes through
 * `fmtDate` (or `fmtDateTime` for a moment). A plain "YYYY-MM-DD" is a calendar day and is never moved by a time zone. */
export type DateInput = string | number | Date | null | undefined;
/** `tz` is the zone a moment is read in (the reader's own when left out); `zone` writes the zone's name after a time. */
export interface DateOpts { year?: boolean; weekday?: boolean; tz?: string; zone?: boolean }

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

/** The day after the close whose numbers aren't stored yet, as the server says it ({day, due}). */
export type Pending = { day: string; due: string | null; during?: boolean } | null | undefined;

/** Numbers stored once a day, on the evening of a session they don't hold yet: "Latest: 8 Oct · 9 Oct due about
 * 18:30 IST", never "Today's numbers · 8 Oct" (R8B-008). While that session is still trading (`during`, a group with no
 * live view): "Latest close 8 Oct · today's count comes after 5:45 PM ET" (R9R-007). Null when the stored day is the newest. */
export function latestDue(have: string | null | undefined, pending: Pending): string | null {
  if (!have || !pending?.day || have.slice(0, 10) >= pending.day) return null;
  const d = (iso: string) => fmtDate(iso.slice(0, 10), { year: false });
  if (pending.during) return `Latest close ${d(have)} · today's count comes after ${pending.due ?? "the close"}`;
  return `Latest: ${d(have)} · ${d(pending.day)} due${pending.due ? ` about ${pending.due}` : " this evening"}`;
}

/** A market event's day, "Wed 7 Oct"; a weekend one adds "(exchanges closed)" so it is not read as a trading day. */
export function eventWhen(e: { date: string; weekend?: string }, year = false): string {
  return fmtDate(e.date, { weekday: true, year }) + (e.weekend ? " (exchanges closed)" : "");
}

/** A clock time, 24-hour: "14:05"; `seconds` gives "14:05:07", `zone` "14:05 IST". */
export function fmtTime(v: DateInput, o: { tz?: string; zone?: boolean; seconds?: boolean } = {}): string {
  const d = toDate(v);
  if (!d) return "–";
  const t = d.toLocaleTimeString("en-GB", { ...(o.tz ? { timeZone: o.tz } : {}), hour: "2-digit", minute: "2-digit", ...(o.seconds ? { second: "2-digit" } : {}), hourCycle: "h23" });
  return o.zone ? `${t} ${tzLabel(o.tz, d)}` : t;
}

/** A moment: "6 Oct 2026, 14:05" (24-hour), or "6 Oct, 14:05" with `year: false`; `seconds` adds ":07"; `zone` adds the
 * zone's name: "6 Oct 2026, 14:05 IST". A market's time passes its `tz` and `zone: true`. */
export function fmtDateTime(v: DateInput, o: DateOpts & { seconds?: boolean } = {}): string {
  const d = toDate(v);
  if (!d) return "–";
  return `${fmtDate(d, o)}, ${fmtTime(d, o)}`;
}

/** A market moment in its zone: date and clock time when intraday, else the day; `zone` adds the zone's name. */
export function when(iso: string | null | undefined, tz: string, intraday: boolean, zone = false): string {
  if (!iso) return "–";
  return intraday ? fmtDateTime(iso, { tz, year: false, zone }) : fmtDate(iso, { tz });
}

/** When a quote's price was traded, in its market's zone: "15:01 IST" today, "7 Oct, 15:29 IST" on an earlier day, and
 * "7 Oct" for a daily candle (a plain calendar day). The time beside each price, so a stale one is seen as stale. */
export function quoteAt(iso: string | null | undefined, tz: string = IST, now: Date = new Date()): string {
  if (!iso) return "";
  if (CALENDAR_DAY.test(iso)) return fmtDate(iso, { year: false });
  const d = toDate(iso);
  if (!d) return "";
  return dayIn(d, tz) === dayIn(now, tz) ? fmtTime(d, { tz, zone: true }) : fmtDateTime(d, { tz, year: false, zone: true });
}

/** A typed time of day in the 24-hour form the app writes: "9:30", "0930", "09.30" and "09:30" all give "09:30"; null
 * when it isn't one (so a box keeps its last good time while someone types). */
export function parseClock(s: string): string | null {
  const m = /^\s*(\d{1,2})(?::|\.|\s)?(\d{2})\s*$/.exec(s);
  if (!m) return null;
  const h = +m[1], mi = +m[2];
  return h <= 23 && mi <= 59 ? `${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}` : null;
}

/** The calendar day ("2026-10-07") a moment falls on in a zone (India's by default); null when it isn't a moment. */
export function dayIn(v: DateInput, tz: string = IST): string | null {
  const d = toDate(v);
  return d ? d.toLocaleDateString("en-CA", { timeZone: tz }) : null;
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
  return `${days} day${days === 1 ? "" : "s"}`;
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

/** When numbers are from, in words: "3 Oct 2026, 14:05 IST", or "3 Oct 2026" for a date alone. A time is read in the
 * market's zone (`tz`, India's unless given) and carries the zone's name; `zone: false` leaves the name off where the
 * sentence already says it. `year: false` gives "3 Oct, 14:05 IST". */
export function asOf(iso: string | null | undefined, o: { tz?: string; zone?: boolean; year?: boolean } = {}): string | null {
  if (!iso) return null;
  const day = /^\d{4}-\d{2}-\d{2}$/.test(iso);
  const d = toDate(iso);
  if (!d) return null;
  return day ? fmtDate(iso, { year: o.year }) : fmtDateTime(d, { tz: o.tz ?? IST, zone: o.zone ?? true, year: o.year });
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

/** A rupee axis in one unit for every tick, picked from the largest value it shows (`span`): lakh from ₹1 lakh up
 * (₹0.5L, ₹1L, −₹1.5L), else whole rupees (₹5,000, −₹50,000). Crore and above fall back to `axisInr`. */
export function axisInrFor(span: number): (v: number) => string {
  const big = Math.abs(span);
  if (big >= CRORE) return axisInr;
  if (big < LAKH) return (v) => (ok(v) ? `${v < 0 ? "−" : ""}₹${nf(Math.abs(v), 0)}` : "–");
  return (v) => (ok(v) ? (v === 0 ? "₹0" : `${v < 0 ? "−" : ""}₹${nf(Math.abs(v) / LAKH, 2)}L`) : "–");
}

/** A hyphen used as a minus (before a digit or currency sign, at the start or after a space or bracket) becomes the real
 * minus sign (U+2212): the one minus the app draws (FY ranges and dates, where a digit comes first, are left alone). */
export function minus(s: string): string {
  return s.replace(/(^|[\s(])-(?=\.?\d|[₹$€£])/g, "$1−");
}

/** The same for what a table cell or a figure holds: text is fixed, a number is written with its real minus. */
export function minusNode<T>(n: T): T | string {
  if (typeof n === "string") return minus(n);
  if (typeof n === "number") return minus(String(n));
  return n;
}

/** A plain number with fixed decimals, Indian grouping and the real minus: 1,234.50 / −0.21. */
export function num(v: number | null | undefined, dp = 2): string {
  if (!ok(v)) return "–";
  const s = Math.abs(v).toLocaleString("en-IN", { maximumFractionDigits: dp, minimumFractionDigits: dp });
  return `${v < 0 && /[1-9]/.test(s) ? "−" : ""}${s}`;
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

/** The colour class for a signed figure: `k-up` (green) above zero, `k-down` (red) below it, "" for zero or a missing
 * value. Pass the text the figure is shown as, and one that rounds to nothing ("0.0%", "+0") stays plain, so the colour
 * always agrees with the sign that is printed. The sign or ▲/▼ stays in the text: colour is never the only signal. */
export function signCls(v: number | null | undefined, text?: string): "k-up" | "k-down" | "" {
  const t = signTone(v);
  if (!t || (text !== undefined && /\d/.test(text) && !/[1-9]/.test(text))) return "";
  return `k-${t}`;
}

/** A plain number with its sign, in Indian grouping: +1,234 / −5. `market` "US" (or any market but India) groups
 * the international way, +208,772, as a US company's figures are written (DESIGN.md "Numbers"). */
export function signed(v: number | null | undefined, dp = 0, market?: string | null): string {
  if (!ok(v)) return "–";
  return `${v > 0 ? "+" : v < 0 ? "−" : ""}${grouped(Math.abs(v), dp, market)}`;
}

/** A plain count or amount without a currency sign, grouped as its market writes it: 2,08,772 in India, 208,772 in the
 * US. With no market, India's. */
export function grouped(v: number | null | undefined, dp = 0, market?: string | null): string {
  if (!ok(v)) return "–";
  const s = Math.abs(v).toLocaleString(market && market !== "IN" ? "en-US" : "en-IN", { maximumFractionDigits: dp, minimumFractionDigits: 0 });
  return `${v < 0 && /[1-9]/.test(s) ? "−" : ""}${s}`;
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
