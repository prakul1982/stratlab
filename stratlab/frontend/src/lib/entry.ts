/* Which half of the site a page load needs. Someone with no saved sign-in (and not just back from Google) can only see
 * the public pages, so those load without the sign-in library, the account state and the app's menu: the policies and
 * the landing page are a fraction of the size. Everyone else gets the whole app. Pure functions, no imports: the entry
 * point reads them before /config.js is known, and unit/entry.test.mjs checks them. */

/** The key the sign-in library saves its session under for a project address (lib/config.ts uses the same one). */
export function sessionKeyFor(supabaseUrl: string | undefined): string {
  let host = "localhost";
  try { host = new URL((supabaseUrl || "http://localhost").replace(/\/?$/, "/")).hostname; } catch { /* keep the default */ }
  return `sb-${host.split(".")[0]}-auth-token`;
}

/** The address carries a sign-in coming back from Google (the tokens are in the part after the #). */
export function hasAuthInUrl(search: string, hash: string): boolean {
  const parts = `${search.replace(/^\?/, "")}&${hash.replace(/^#/, "")}`;
  return /(^|&)(access_token|refresh_token|provider_token|code)=/.test(parts);
}

/** True when this page load needs the app (a saved sign-in, or one arriving now); false for a plain visitor. */
export function wantsAccount(o: { supabaseUrl?: string; search?: string; hash?: string; storage?: Pick<Storage, "getItem"> | null }): boolean {
  if (hasAuthInUrl(o.search ?? "", o.hash ?? "")) return true;
  try { return !!o.storage?.getItem(sessionKeyFor(o.supabaseUrl)); } catch { return true; }       // storage that throws: let the app sort it out
}

/** The pages anyone sees the same way, signed in or not: the policies and a shared verdict or library entry. */
export const PUBLIC_FOR_ALL = [/^\/(terms|privacy|refunds|contact)\/?$/, /^\/verdict\/[^/]+\/?$/, /^\/library\/[^/]+\/?$/];
export const isPublicForAll = (path: string) => PUBLIC_FOR_ALL.some((re) => re.test(path.split(/[?#]/)[0]));

/** The server's public answers a visitor's first page will ask for, by its address: asked at once, alongside the page's
 * code, instead of after it (R8V-013: /library's one question waited for some forty files and about 3 s). The pages take
 * them through lib/http's publicGet; each address is written exactly as its page writes it. */
export function publicReads(path: string): string[] {
  const p = path.split(/[?#]/)[0];
  const one = (s: string) => { try { return encodeURIComponent(decodeURIComponent(s)); } catch { return encodeURIComponent(s); } };
  const lib = p.match(/^\/library\/([^/]+)\/?$/);
  const verdict = p.match(/^\/verdict\/([^/]+)\/?$/);
  return /^\/library\/?$/.test(p) ? ["/public/library"]
    : lib ? [`/public/library/${one(lib[1])}`]
    : verdict ? [`/public/v/${one(verdict[1])}`]
    : /^\/(pricing|plans|upgrade|help|faq|features|login|signup|about)?\/?$/.test(p) ? ["/pricing", "/public/library?sort=new&limit=60"]
    : [];
}
