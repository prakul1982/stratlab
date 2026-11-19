/* Trade home's next F&O expiry, on its own so the landing page's download (which holds lib/tradeUi) carries none of it. */
/** The next F&O expiry of either exchange, from the market events (expiry kind): the nearest day on or after `today`, NSE's or BSE's
 * (LIVE12B-013: Trade home's tile skipped BSE's SENSEX expiry of Thu 19 Nov and showed NSE's of Mon 23 Nov as the next one). On a day
 * both expire, NSE's comes first. null when none is listed. */
/* LIVE16B-003: and one of today whose time has passed by India's clock is over (`nowHm`, "19:53": Thursday's 15:30 SENSEX expiry was still
 * "Next F&O expiry" four hours after it ended), as every "Coming up" counts it (lib/eventTime happened). */
export function nextExpiry<E extends { kind: string; date: string; title: string; time?: string | null }>(events: E[] | null | undefined, today: string, nowHm = ""): E | null {
  const ahead = (events ?? []).filter((e) => e.kind === "expiry" && (e.date > today || (e.date === today && !(nowHm && e.time && e.time <= nowHm))));
  ahead.sort((a, b) => a.date.localeCompare(b.date) || Number(a.title.startsWith("SENSEX")) - Number(b.title.startsWith("SENSEX")));
  return ahead[0] ?? null;
}
