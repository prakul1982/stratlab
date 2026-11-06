/* The last mood read shown at once while a fresh one is read (LIVE4-024: switching to the US showed "Reading the tape… Still
 * loading" for over 10 s, and India's first read of a session took 29 s). Kept in memory for the session and on this device; the
 * loading bar shows only when there has never been a read. No imports beyond types: the unit tests run it as it is. */
import type { PulseMood, Region } from "./research";

const mem = new Map<Region, PulseMood>();
const KEY = (r: Region) => `stratlab.mood.v1.${r}`;
/** A copy older than this (seconds) is shown while the page asks again for the fresh read: market open / shut. */
export const MOOD_STALE_OPEN = 120, MOOD_STALE_SHUT = 1800;
/** A copy kept on the device older than this is not shown (seconds). */
export const MOOD_KEEP = 3 * 86400;

export function keptMood(region: Region, now = Date.now()): PulseMood | null {
  const hit = mem.get(region);
  if (hit) return hit;
  try {
    const raw = localStorage.getItem(KEY(region));
    const got = raw ? (JSON.parse(raw) as PulseMood) : null;
    if (got && got.region === region && got.read_at && now - Date.parse(got.read_at) < MOOD_KEEP * 1000) { mem.set(region, got); return got; }
  } catch { /* no storage here (a private window): nothing kept */ }
  return null;
}

export function keepMood(region: Region, m: PulseMood): void {
  if (m.pending) return;
  mem.set(region, m);
  try { localStorage.setItem(KEY(region), JSON.stringify(m)); } catch { /* full or blocked: memory only */ }
}

/** Whether a read is old enough that a fresher one is being read behind it (the server says so, or its read time is past the limit). */
export function moodStale(m: PulseMood | null, now = Date.now()): boolean {
  if (!m) return false;
  if (m.refreshing) return true;
  if (!m.read_at) return false;
  return now - Date.parse(m.read_at) > (m.is_open ? MOOD_STALE_OPEN : MOOD_STALE_SHUT) * 1000;
}
