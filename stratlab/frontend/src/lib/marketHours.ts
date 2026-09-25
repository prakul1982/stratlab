import type { Market } from "./types";

/** When each market is open, and how long until it opens or closes. Holidays aren't known, so a
 * closed-for-a-holiday market reads as opening at its usual time. */

const DAY = 24 * 60;
const WD = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** The wall clock in a time zone: weekday (0 = Sunday), minutes past midnight, and the zone's offset from UTC in minutes. */
function wall(now: Date, tz: string) {
  const parts = new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", weekday: "short",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "0";
  const y = +get("year"), mo = +get("month"), d = +get("day"), h = +get("hour") % 24, mi = +get("minute");
  const offset = Math.round((Date.UTC(y, mo - 1, d, h, mi) - now.getTime()) / 60000);
  return { wd: WD.indexOf(get("weekday")), min: h * 60 + mi, offset };
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
  short: string;            // a few characters for the sidebar
  change: Date | null;      // when it next opens or closes
  hoursLocal: string | null; hoursYours: string | null;
}

export function marketState(m: Market, now = new Date()): MarketState {
  const base = { always: false, offline: false, hoursLocal: null, hoursYours: null } as const;
  if (m.status === "offline") return { ...base, open: false, offline: true, short: "offline", change: null };
  if (m.id === "CRYPTO") return { ...base, open: true, always: true, short: "24/7", change: null };
  const at = (mins: number) => new Date(now.getTime() + mins * 60000);
  const yours = (d: Date) => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (m.id === "FX" || !m.hours?.open || !m.hours?.close) {
    // forex trades from Sunday 17:00 to Friday 17:00 New York time
    const w = wall(now, "America/New_York");
    const weekMin = w.wd * DAY + w.min, openAt = 0 * DAY + 17 * 60, closeAt = 5 * DAY + 17 * 60;
    const open = weekMin >= openAt && weekMin < closeAt;
    const until = open ? closeAt - weekMin : (openAt + 7 * DAY - weekMin) % (7 * DAY);
    return { ...base, open, short: open ? "open" : `opens ${inWords(until)}`, change: at(until), hoursLocal: "Sun 17:00 – Fri 17:00 New York", hoursYours: null };
  }
  const w = wall(now, m.tz), o = hm(m.hours.open), c = hm(m.hours.close);
  const weekday = (d: number) => d >= 1 && d <= 5;
  const open = weekday(w.wd) && w.min >= o && w.min < c;
  let until: number;
  if (open) until = c - w.min;
  else {
    let days = 0;
    if (!(weekday(w.wd) && w.min < o)) {
      days = 1;
      while (!weekday((w.wd + days) % 7)) days++;
    }
    until = days * DAY + o - w.min;
  }
  const change = at(until);
  const todayOpen = new Date(now.getTime() + (o - w.min) * 60000), todayClose = new Date(now.getTime() + (c - w.min) * 60000);
  const short = open ? "open" : until < DAY ? `opens ${inWords(until)}` : `opens ${change.toLocaleDateString([], { weekday: "short" })}`;
  return { ...base, open, short, change, hoursLocal: `${m.hours.open}–${m.hours.close} local, ${m.hours.days}`,
    hoursYours: `${yours(todayOpen)}–${yours(todayClose)} your time` };
}
