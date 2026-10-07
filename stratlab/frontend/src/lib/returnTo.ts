/* The page to open once someone has signed in: the address they arrived at (a company, a notebook, Holdings), kept
 * through Google sign-in and opened afterwards. Only StratLab's own pages: anything that could leave the site (another
 * host, "//evil.com", "/\evil.com", a "javascript:" address, a control character) is dropped, so a crafted link can't
 * turn sign-in into a jump to another site. Pure functions plus storage; unit/returnTo.test.mjs checks them. */

/** Where the address to return to is kept between leaving for Google and coming back. */
export const NEXT_PAGE = "stratlab.next";
const MAX_AGE = 60 * 60 * 1000;          // a sign-in that takes longer than an hour starts from home
const MAX_LEN = 512;

/** Pages that are the landing page itself (or its sections): nothing to come back to. */
const LANDING = new Set(["/", "/pricing", "/upgrade", "/help", "/features"]);

/** `next` as a same-site path ("/research/IN/RELIANCE?tab=x#y"), or null when it isn't one of ours. */
export function safeNext(next: unknown, origin = "https://stratlab.invalid"): string | null {
  if (typeof next !== "string" || !next || next.length > MAX_LEN) return null;
  if (!next.startsWith("/") || next.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(next)) return null;
  let url: URL;
  try { url = new URL(next, origin); } catch { return null; }
  if (url.origin !== new URL(origin).origin) return null;
  const path = url.pathname + url.search + url.hash;
  return path.startsWith("/") && !path.startsWith("//") ? path : null;
}

/** The address worth returning to after sign-in, from where the visitor is now; null on the landing page. */
export function returnPathFor(pathname: string, search = "", hash = ""): string | null {
  if (LANDING.has(pathname.replace(/\/+$/, "") || "/")) return null;
  return safeNext(pathname + search + hash);
}

type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const stores = (): Store[] => {
  const out: Store[] = [];
  try { out.push(window.sessionStorage); } catch { /* storage off */ }
  try { out.push(window.localStorage); } catch { /* storage off */ }
  return out;
};

/** Keep `next` for after sign-in. In this tab's session storage, and in local storage too (with the time), so a sign-in
 * that comes back in a fresh tab still finds it. */
export function rememberNext(next: string | null, now = Date.now(), where: Store[] = stores()) {
  const safe = safeNext(next);
  for (const s of where) {
    try {
      if (safe) s.setItem(NEXT_PAGE, JSON.stringify({ to: safe, at: now }));
      else s.removeItem(NEXT_PAGE);
    } catch { /* storage full or off */ }
  }
}

/** The kept address, once (it is removed as it is read); null when there is none, it is stale, or it isn't ours. */
export function takeNext(now = Date.now(), where: Store[] = stores()): string | null {
  let found: string | null = null;
  for (const s of where) {
    let raw: string | null = null;
    try { raw = s.getItem(NEXT_PAGE); s.removeItem(NEXT_PAGE); } catch { /* storage off */ }
    if (!raw || found) continue;
    let to: unknown = raw, at = now;
    try { const v = JSON.parse(raw); if (v && typeof v === "object") { to = v.to; at = Number(v.at) || 0; } } catch { /* an older plain path */ }
    if (now - at <= MAX_AGE) found = safeNext(to);
  }
  return found;
}
