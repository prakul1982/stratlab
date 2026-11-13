/** A page's code that failed to download is asked for again, a little later each time, before anything is shown (R16-001:
 * one 502 on a chunk showed "Couldn't load StratLab"). Vite's preload error is cancelled in public/boot.js so the import
 * arrives empty instead of throwing; an empty module counts as a failed download here. After the last try the start-up
 * script's guarded reload runs (once per minute at most), else the error goes on to the page's error screen. */
export const RETRY_WAITS = [300, 900, 2000];
/** One try that never answers (a request held open by a proxy) counts as failed after this long, so the page ends on its
 * "Couldn't load… Reload" screen and not on "Opening…" for ever (R29B-003). */
export const TRY_TIMEOUT_MS = 20_000;

const within = <T,>(p: Promise<T>, ms: number): Promise<T> => new Promise<T>((ok, no) => {
  const t = setTimeout(() => no(new Error("Failed to fetch dynamically imported module (timed out)")), ms);
  p.then((v) => { clearTimeout(t); ok(v); }, (e) => { clearTimeout(t); no(e); });
});

/** The app's own code file a failed import names ("Failed to fetch dynamically imported module: https://…/assets/x-1a2b.js"), or null. */
export function failedAsset(e: unknown): string | null {
  const m = String((e as { message?: string })?.message ?? e ?? "").match(/(?:https?:\/\/[^\s"')]+)?\/assets\/[\w.-]+\.(?:js|css)/);
  return m ? m[0] : null;
}

/** A code file that once answered 404 (a deploy switching over) can stay a 404 in the browser's cache: the host marks every
 * /assets/ answer to be kept for a year, its 404 too, so every retry got the kept 404 and "Couldn't load StratLab. Reload"
 * never went away (R43.1 smoke). Before the next try the file is asked for past the cache, which replaces the kept answer. */
export async function refetchPastCache(url: string | null, tryMs: number = TRY_TIMEOUT_MS): Promise<void> {
  if (!url || typeof fetch !== "function") return;
  try { await within(fetch(url, { cache: "reload", credentials: "same-origin" }), tryMs); } catch { /* the next try says how it went */ }
}

export async function importWithRetry<T>(load: () => Promise<T>, waits: number[] = RETRY_WAITS, tryMs: number = TRY_TIMEOUT_MS): Promise<T> {
  let last: unknown;
  for (let i = 0; i <= waits.length; i++) {
    if (i) await new Promise((ok) => setTimeout(ok, waits[i - 1]));
    if (i) await refetchPastCache(failedAsset(last), tryMs);
    try {
      const m = await within(Promise.resolve().then(load), tryMs);
      if (m == null) throw new Error("Failed to fetch dynamically imported module");
      if (typeof window !== "undefined") window.__stratlabLoadFailed = false;      // it came: a later error is the page's own
      return m;
    } catch (e) { last = e; }
  }
  if (typeof window !== "undefined") { window.__stratlabLoadFailed = true; window.__stratlabRecover?.(); }
  throw last;
}
