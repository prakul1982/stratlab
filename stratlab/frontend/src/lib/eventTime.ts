/* When a dated event has happened, by India's clock. Pure, so the unit tests can read it. */

/** The time of day in India, "18:02": what a dated event's "15:30" is compared with. */
export const istHm = (at: Date = new Date()): string =>
  at.toLocaleTimeString("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false });

/** An event of today whose time has passed by India's clock (a release out already counts too): no longer "coming up"
 * (R70-001: Monday's 15:30 NIFTY expiry was "Next up" at 18:00). One without a time (a holiday) lasts the day. */
export function happened(e: { date: string; time: string | null; status?: string }, today: string, nowHm: string): boolean {
  if (e.date !== today) return e.date < today;
  return e.status === "released" || (!!e.time && e.time <= nowHm);
}
