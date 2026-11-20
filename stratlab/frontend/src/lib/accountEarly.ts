/* LIVE13B-004: what a signed-in page asks the server for while the app's own code is still downloading (entry.tsx, for a saved sign-in
 * only, never a visitor): the data status (LIVE11B-004) and the account itself. A page opened directly asked /me only once all of its
 * ~90 files had arrived (2.8 s on a throttled link, 5 s live); now it is asked beside the first of them, with the saved sign-in's token,
 * and the app's first /me (lib/api.ts) takes this answer when its token is the same. A token near its end is left to the sign-in library
 * to renew first, and an answer older than EARLY_ME_MS is not used. */
import { CFG, sessionKey } from "./config";
import { prefetchPublic as prefetchNow } from "./http";

/** A public read asked now, unless public/early.js has already asked it (site81: lib/app.tsx takes that one). */
const prefetchPublic = (path: string): void => {
  if (!(window as unknown as { __stratlabEarlyPublic?: Record<string, unknown> }).__stratlabEarlyPublic?.[path]) prefetchNow(path);
};
import { VIEW_AS_HEADER, readViewAs } from "./viewAs";

// kept on the window, not in this module, so the app's own request code (lib/api.ts) reads it without depending on this file
type Early = { token: string; at: number; got: Promise<Response> };
declare global { interface Window { __stratlabEarlyMe?: Early | null } }
const EARLY_ME_MS = 30_000;

/** Ask for the account with the saved sign-in's token, once, if there is one that isn't about to end. */
export function prefetchMe(): void {
  try {
    if (!CFG.API_BASE || window.__stratlabEarlyMe) return;
    const saved = JSON.parse(localStorage.getItem(sessionKey()) || "null") as { access_token?: string; expires_at?: number } | null;
    const token = saved?.access_token, ends = Number(saved?.expires_at || 0) * 1000;
    if (!token || !ends || ends < Date.now() + 60_000) return;
    const as = readViewAs();
    const got = fetch(CFG.API_BASE + "/me", { headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}`, ...(as ? { [VIEW_AS_HEADER]: as } : {}) } });
    got.catch(() => undefined);
    window.__stratlabEarlyMe = { token, at: Date.now(), got };
  } catch { /* no saved sign-in to read */ }
}

/** The early answer for this request, once: only the first GET of /me, and only with the same token (lib/api.ts has its own copy of
 * this check, so the app's request code doesn't download this file). */
export function takeEarlyMe(path: string, method: string, token: string | undefined): Promise<Response> | null {
  const e = window.__stratlabEarlyMe;
  if (!e || path !== "/me" || method !== "GET") return null;
  window.__stratlabEarlyMe = null;
  return e.token === token && Date.now() - e.at < EARLY_ME_MS ? e.got : null;
}

/** Everything a signed-in page start asks for at once (entry.tsx). */
export function startAccountReads(): void {
  prefetchPublic("/public/data-online");
  prefetchMe();
}
