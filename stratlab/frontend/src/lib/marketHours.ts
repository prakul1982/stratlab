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
  const yours = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (m.id === "FX" || !m.hours?.open || !m.hours?.close) {
    // forex trades from Sunday 17:00 to Friday 17:00 New York time
    const w = wall(now, "America/New_York");
    const weekMin = w.wd * DAY + w.min, openAt = 0 * DAY + 17 * 60, closeAt = 5 * DAY + 17 * 60;
    const open = weekMin >= openAt && weekMin < closeAt;
    const until = open ? closeAt - weekMin : (openAt + 7 * DAY - weekMin) % (7 * DAY);
    const weekend = !open && (w.wd === 6 || w.wd === 0 || (w.wd === 5 && w.min >= 17 * 60));
    return { ...base, open, closedFor: weekend ? "weekend" : null, short: open ? "open" : weekend ? "weekend" : `opens ${inWords(until)}`,
      change: at(until), hoursLocal: "Sun 17:00 – Fri 17:00 New York", hoursYours: null };
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
  const short = open ? "open" : closedFor ?? (until < DAY ? `opens ${inWords(until)}` : `opens ${change.toLocaleDateString([], { weekday: "short" })}`);
  return { ...base, open, closedFor, short, change, hoursLocal: `${m.hours.open}–${m.hours.close} local, ${m.hours.days}`,
    hoursYours: `${yours(todayOpen)}–${yours(todayClose)} your time` };
}
