/* The home page's watchlist card: the last prices it showed, kept in this browser for this account, so a cold load paints the rows at
 * once (said as the earlier read, with its time) while today's are read (rel1, LIVE9B-010: "Reading your watchlist prices…" was still
 * on screen 17 s after the page opened, and the card's arrival moved the page). Removed at sign-out (localData.clearLocalData). */
const KEY = "stratlab.mine.movers.v1";
const MAX_AGE_MS = 4 * 86400_000;        // older than this is no help: the card reads afresh with its placeholder

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const local = (): Store | null => { try { return localStorage; } catch { return null; } };

/** The rows kept for this account and when they were read, or null (none, another account's, too old, or storage off). */
export function readKeptMovers<T>(uid: string | null | undefined, now = Date.now(), store: Store | null = local()): { at: string; rows: T[] } | null {
  if (!uid || !store) return null;
  try {
    const got = JSON.parse(store.getItem(KEY) ?? "null");
    if (!got || got.uid !== uid || !Array.isArray(got.rows) || !got.rows.length || typeof got.at !== "string") return null;
    if (!(now - Date.parse(got.at) < MAX_AGE_MS)) return null;
    return { at: got.at, rows: got.rows as T[] };
  } catch { return null; }
}

/** Keep the rows just shown, for this account. */
export function keepMovers<T>(uid: string | null | undefined, rows: T[], now = Date.now(), store: Store | null = local()): void {
  if (!uid || !store || !rows.length) return;
  try { store.setItem(KEY, JSON.stringify({ uid, at: new Date(now).toISOString(), rows: rows.slice(0, 6) })); } catch { /* storage full or off */ }
}

export function forgetKeptMovers(store: Store | null = local()): void {
  try { store?.removeItem(KEY); } catch { /* storage off */ }
}
