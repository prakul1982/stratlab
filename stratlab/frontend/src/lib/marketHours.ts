import { fmtTime } from "./format";
import type { Market } from "./types";

/** When each market is open, and how long until it opens or closes, skipping weekends and the exchange
 * holidays the server sends with each market. Half-days aren't known. */

const DAY = 24 * 60;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The wall clock in a time zone: weekday (0 = Sunday), minutes past midnight, and the zone's offset from UTC in minutes. */
function wall(now: Date, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", weekday: "short",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "0";
  const y = +get("year"), mo = +get("month"), d = +get("day"), h = +get("hour") % 24, mi = +get("minute");
  const offset = Math.round((Date.UTC(y, mo - 1, d, h, mi) - now.getTime()) / 60000);
  const iso = (n: number) => new Date(Date.UTC(y, mo - 1, d + n)).toISOString().slice(0, 10);
  return { wd: WD.indexOf(get("weekday")), min: h * 60 + mi, offset, iso };
}

const hm = (s: string) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };

export function inWords(mins: number): string {
  if (mins < 60) return `${Math.max(1, Math.round(mins))}m`;
  if (mins < DAY) { const h = Math.floor(mins / 60), m = Math.round(mins % 60); return m ? `${h}h ${m}m` : `${h}h`; }
  const d = Math.floor(mins / DAY), h = Math.round((mins % DAY) / 60);
  return h ? `${d}d ${h}h` : `${d}d`;
}

export interface MarketState {
  open: boolean; always: boolean; offline: boolean;
  closedFor: "weekend" | "holiday" | null;   // closed all day today, and why
  short: string;            // a few characters for the sidebar
  change: Date | null;      // when it next opens or closes
  hoursLocal: string | null; hoursYours: string | null;
}

export function marketState(m: Market, now = new Date()): MarketState {
  const base = { always: false, offline: false, closedFor: null, hoursLocal: null, hoursYours: null } as const;
  if (m.status === "offline") {
    // no data feed, but on a weekend or holiday that's not the news: the market is shut anyway
    const shut = m.hours?.open ? marketState({ ...m, status: "live" }, now) : null;
    if (shut?.closedFor) return shut;
    return { ...base, open: false, offline: true, short: "offline", change: null };
  }
  if (m.id === "CRYPTO") return { ...base, open: true, always: true, short: "24/7", change: null };
  const at = (mins: number) => new Date(now.getTime() + mins * 60000);
  const yours = (d: Date) => d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  if (m.id === "FX" || !m.hours?.open || !m.hours?.close) {
    // forex trades from Sunday 17:00 to Friday 17:00 New York time; global commodity futures (CME) from Sunday 18:00
    const w = wall(now, "America/New_York");
    const sunOpen = m.id === "CMDTY" ? 18 : 17;
    const weekMin = w.wd * DAY + w.min, openAt = 0 * DAY + sunOpen * 60, closeAt = 5 * DAY + 17 * 60;
    const open = weekMin >= openAt && weekMin < closeAt;
    const until = open ? closeAt - weekMin : (openAt + 7 * DAY - weekMin) % (7 * DAY);
    const weekend = !open && (w.wd === 6 || w.wd === 0 || (w.wd === 5 && w.min >= 17 * 60));
    return { ...base, open, closedFor: weekend ? "weekend" : null, short: open ? "open" : weekend ? "weekend" : `opens ${inWords(until)}`,
      change: at(until), hoursLocal: `Sun ${sunOpen}:00 – Fri 17:00 New York${m.id === "CMDTY" ? ", with a daily break 17:00–18:00" : ""}`, hoursYours: null };
  }
  const w = wall(now, m.tz), o = hm(m.hours.open), c = hm(m.hours.close);
  const weekday = (d: number) => d >= 1 && d <= 5;
  const shut = new Set(m.holidays ?? []);
  const trades = (n: number) => weekday((w.wd + n) % 7) && !shut.has(w.iso(n));
  const open = trades(0) && w.min >= o && w.min < c;
  let until: number, days = 0;
  if (open) until = c - w.min;
  else {
    if (!(trades(0) && w.min < o)) {
      days = 1;
      while (!trades(days) && days < 30) days++;
    }
    until = days * DAY + o - w.min;
  }
  // shut until a later day: say why, the same way for every exchange (Friday evening counts as the weekend)
  const skipped = Array.from({ length: days }, (_, n) => n).filter((n) => n > 0 || !trades(0));
  const first = skipped[0];       // the first closed day decides: a holiday, or the weekend
  const closedFor = open || first === undefined ? null : weekday((w.wd + first) % 7) ? "holiday" : "weekend";
  const change = at(until);
  const todayOpen = new Date(now.getTime() + (o - w.min) * 60000), todayClose = new Date(now.getTime() + (c - w.min) * 60000);
  const short = open ? "open" : closedFor ?? (until < DAY ? `opens ${inWords(until)}` : `opens ${change.toLocaleDateString("en-GB", { weekday: "short" })}`);
  return { ...base, open, closedFor, short, change, hoursLocal: `${m.hours.open}–${m.hours.close} local, ${m.hours.days}`,
    hoursYours: `${yours(todayOpen)}–${yours(todayClose)} your time` };
}

/** "Thu 8 Oct, 09:15 IST": a moment in an exchange's own zone, with the zone's short name. */
export function exchangeTime(d: Date, tz: string): string {
  const day = d.toLocaleDateString("en-GB", { timeZone: tz, weekday: "short", day: "numeric", month: "short" }).replace(/,/g, "").replace(/\bSept\b/, "Sep");
  // the time and the zone's name the one way every market time is written (lib/format: "09:15 IST", "09:30 ET")
  return `${day}, ${fmtTime(d, { tz, zone: true })}`;
}

export type FeedLine = { text: string; tone: "live" | "plain" | "warn" };

/** What a running paper session's price line says. Outside market hours that's the market being closed and when it
 * opens, not a lost connection; "Reconnecting" only when the market is open and the feed is down, and a warning once
 * no price has come for a while. `market` is the session's market (from the app's list); crypto never closes. */
export function sessionFeed(o: { feedConnected: boolean | undefined; lastTickAt: string | null | undefined; market?: Market | null; alwaysOpen?: boolean; now?: Date }): FeedLine {
  const now = o.now ?? new Date();
  const st = o.market && !o.alwaysOpen ? marketState(o.market, now) : null;
  if (st && !st.open && !st.always && !st.offline) {
    const next = st.change ? ` · opens ${exchangeTime(st.change, o.market!.tz)}` : "";
    return { text: `Market closed${next}`, tone: "plain" };
  }
  if (o.feedConnected) {
    if (o.lastTickAt) return { text: "Live prices", tone: "live" };
    return { text: o.alwaysOpen ? "Fetching the latest prices" : "Waiting for the first price", tone: "plain" };
  }
  const quiet = o.lastTickAt ? (now.getTime() - Date.parse(o.lastTickAt)) / 60000 : null;
  if (quiet != null && quiet > 10) return { text: `No prices for ${inWords(quiet)}: the price feed is down, orders wait for it`, tone: "warn" };
  return { text: "Reconnecting to prices", tone: "plain" };
}

/** The line under "Today" when it adds a US session to India's (R6O-015: Today ₹192 = an India day that had closed plus
 *  AAPL moving live, so it changed by the minute under one word): the US part named, live or at its close, in dollars
 *  and at the rupee rate used. null when there's no US part in Today. */
export function usTodayNote(markets: Market[], us: { day: number | null; in_total?: boolean } | null | undefined, usdInr: number | null | undefined,
  now = new Date()): string | null {
  if (!us || us.day == null || !us.in_total) return null;
  const m = markets.find((x) => x.id === "US");
  const live = !!m && marketState(m, now).open;
  const usd = `${us.day < 0 ? "−" : "+"}$${Math.abs(us.day).toFixed(2)}`;
  const inr = usdInr ? ` (₹${Math.round(Math.abs(us.day) * usdInr).toLocaleString("en-IN")} at ₹${usdInr.toFixed(2)} a dollar)` : "";
  return `Today includes US stocks, ${live ? "US, live: it moves until the US close" : "US, at their last close"}: ${usd}${inr}.`;
}
