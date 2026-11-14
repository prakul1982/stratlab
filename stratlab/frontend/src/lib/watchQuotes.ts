/* The Markets panel's last prices, kept on this device (LIVE6-013: every row said "–" for about five seconds each time the panel
 * opened, until the first read came back). The rows open on the prices last seen, each with its own time, and the reads replace them as
 * they arrive. Only the panel imports this (its own chunk); every storage call is guarded, so a browser that refuses storage just
 * waits for the reads as before. Kept per person (`who`), so a shared device never shows one person's list to another. */
import type { WatchQuote } from "./watch";

export const QUOTES_KEY = "stratlab.mw.quotes";
export const KEEP_QUOTES = 200;                 // instruments kept, the latest seen first
const MAX_AGE_MS = 7 * 24 * 3600 * 1000;        // older than a week: not shown

type Kept = Record<string, WatchQuote & { seen: number }>;

const isQuote = (q: unknown): q is WatchQuote & { seen: number } => {
  const x = q as Record<string, unknown> | null;
  return !!x && typeof x === "object" && (x.price === null || (typeof x.price === "number" && Number.isFinite(x.price))) && typeof x.seen === "number";
};

/** The prices kept, as the panel's quotes ({key: quote}); empty when nothing is kept or storage can't be read. `since`: the day (ISO) a
 * key's market last traded; a price kept from before it is left out, so a row never paints an older session's price under the newer
 * session's date (LIVE8A-007: 12 Nov's prices under "Closed · last close Fri 13 Nov" until the reads came). */
export function keptQuotes(who: string, now = Date.now(), store: Pick<Storage, "getItem"> | null = safeStore(), since?: (key: string) => string | null): Record<string, WatchQuote> {
  try {
    const raw = JSON.parse(store?.getItem(`${QUOTES_KEY}.${who}`) ?? "{}") as Kept;
    const out: Record<string, WatchQuote> = {};
    for (const [k, q] of Object.entries(raw && typeof raw === "object" ? raw : {})) {
      if (!isQuote(q) || q.price == null || now - q.seen > MAX_AGE_MS) continue;
      const day = since?.(k);
      if (day && (!q.at || String(q.at).slice(0, 10) < day)) continue;
      const { seen: _seen, ...quote } = q;
      out[k] = quote;
    }
    return out;
  } catch {
    return {};
  }
}

/** The quotes read now added to those kept (the latest KEEP_QUOTES); a quote without a price never replaces one with a price. */
export function keepQuotes(who: string, got: Record<string, WatchQuote | null>, now = Date.now(), store: Pick<Storage, "getItem" | "setItem"> | null = safeStore()): void {
  try {
    const raw = JSON.parse(store?.getItem(`${QUOTES_KEY}.${who}`) ?? "{}") as Kept;
    const kept: Kept = raw && typeof raw === "object" ? raw : {};
    for (const [k, q] of Object.entries(got)) if (q && q.price != null) kept[k] = { ...q, seen: now };
    const rows = Object.entries(kept).filter(([, q]) => isQuote(q)).sort((a, b) => b[1].seen - a[1].seen).slice(0, KEEP_QUOTES);
    store?.setItem(`${QUOTES_KEY}.${who}`, JSON.stringify(Object.fromEntries(rows)));
  } catch { /* storage full or refused: the next open reads afresh */ }
}

function safeStore(): Storage | null {
  try { return typeof localStorage === "undefined" ? null : localStorage; } catch { return null; }
}
