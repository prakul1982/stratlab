/* "Good morning" on My space, in the right zone (R5O-031). StratLab's people follow the Indian market unless they
 * picked the US one: their greeting and date are in India's time, as the market lines beside them are. Someone who
 * follows the US market gets their own zone; a browser that reports no real place (UTC, Etc/…) gets India's. */

export const IST_ZONE = "Asia/Kolkata";

export function greetingZone(region: "IN" | "US", browserZone: string | undefined): string {
  const real = !!browserZone && !/^(UTC|GMT|Etc\/)/i.test(browserZone);
  return region === "US" && real ? browserZone! : IST_ZONE;
}

/** The hour (0-23) at `now` in `zone`. */
export function hourIn(zone: string, now: Date = new Date()): number {
  const h = Number(new Intl.DateTimeFormat("en-GB", { hour: "2-digit", hourCycle: "h23", timeZone: zone }).format(now));
  return Number.isFinite(h) ? h % 24 : now.getHours();
}

/** 05:00 to 11:59 morning, 12:00 to 16:59 afternoon, 17:00 to 21:59 evening; the small hours (22:00 to 04:59) just "Hello",
 * never "Good morning" at 00:20. */
export function greetingAt(hour: number): string {
  return hour >= 5 && hour < 12 ? "Good morning" : hour >= 12 && hour < 17 ? "Good afternoon" : hour >= 17 && hour < 22 ? "Good evening" : "Hello";
}
