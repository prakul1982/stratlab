import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { NAV, locate, locateGroup } from "./nav";
import { isAppPath } from "./deepLinks";

/** The browser tab's title. Every page gets one from the one map of pages (lib/nav.ts): "Holdings · StratLab". A page
 * that knows something more specific (a company's symbol and price, a notebook's name) sets it with `useDocTitle`. */
export const BRAND = "StratLab";
export const DEFAULT_TITLE = "StratLab: test it, research it, track it";

/** Pages that are not in a space's menu, by address. */
const OWN: Record<string, string> = {
  "/mine": "My space", "/account": "Account", "/settings": "Settings", "/assistant": "AI assistant", "/app": "Get the app",
  "/invite": "Invite friends", "/plans": "Plans", "/features": "All features", "/dev/kit": "Design kit", "/new": "New notebook",
  "/trade": "Trade home", "/invest": "Invest home", "/money": "Money home", "/research/compare": "Compare", "/help": "Help",
};

/** "Page · StratLab" (or the brand's line alone when the page has no name). */
export const withBrand = (name?: string | null) => (name ? `${name} · ${BRAND}` : DEFAULT_TITLE);

/** The title an address gets before the page adds anything of its own. */
export function titleFor(path: string): string {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (OWN[p]) return withBrand(OWN[p]);
  if (p === "/admin" || p.startsWith("/admin/")) return withBrand("Admin");
  const company = p.match(/^\/research\/(IN|US)\/([^/]+)(\/deep)?$/);
  if (company) {
    // the company's name from the first frame when it has been opened before (R8O-009: "POLYCAB · StratLab" until the
    // page's numbers arrived)
    const sym = decodeURIComponent(company[2]).toUpperCase();
    const name = knownName(company[1], sym);
    return withBrand(`${name ? `${name} (${sym})` : sym}${company[3] ? " deep dive" : ""}`);
  }
  const g = locateGroup(p);
  if (g) return withBrand(`${g.group.label} · ${NAV[g.space].label}`);
  const at = locate(p);
  if (at) return withBrand(at.page.label);
  return DEFAULT_TITLE;
}

const NAMES_KEY = "stratlab.company-names";

/** A company's name as its page last gave it, kept on this device for the tab's title (at most 200 companies). */
export function rememberName(region: string, symbol: string, name: string | null | undefined) {
  if (!name) return;
  try {
    const all = JSON.parse(localStorage.getItem(NAMES_KEY) || "{}") as Record<string, string>;
    const k = `${region}:${symbol.toUpperCase()}`;
    if (all[k] === name) return;
    delete all[k];
    all[k] = name;
    const keys = Object.keys(all);
    for (const old of keys.slice(0, Math.max(0, keys.length - 200))) delete all[old];
    localStorage.setItem(NAMES_KEY, JSON.stringify(all));
  } catch { /* storage off */ }
}

export function knownName(region: string, symbol: string): string | null {
  try { return (JSON.parse(localStorage.getItem(NAMES_KEY) || "{}") as Record<string, string>)[`${region.toUpperCase()}:${symbol.toUpperCase()}`] ?? null; }
  catch { return null; }
}

/** The pages anyone can open, with the name each gives its tab: the policies, the sign-in addresses and the landing page's
 * "about". Every public page has a title of its own, never the sign-in page's. */
export const PUBLIC_TITLES: Record<string, string> = {
  "/terms": "Terms", "/privacy": "Privacy", "/refunds": "Refunds", "/contact": "Contact",
  "/login": "Sign in", "/signup": "Sign up", "/about": "About", "/faq": "Questions", "/library": "Strategy library",
};

/** The title of a page nothing is at. */
export const NOT_FOUND_TITLE = withBrand("Page not found");

/** The title for a visitor who isn't signed in: "Sign in · Options builder · StratLab" on an app address (so a tab says
 * what it is waiting for), "Plans · StratLab" on /pricing and /plans, "Terms · StratLab" on a policy, "Page not found ·
 * StratLab" where nothing is, the brand's line on the landing page itself. */
export function signedOutTitle(path: string): string {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (PUBLIC_TITLES[p]) return withBrand(PUBLIC_TITLES[p]);
  if (p === "/pricing" || p === "/upgrade" || p === "/plans") return withBrand("Plans");
  if (p === "/help") return withBrand("Help");
  if (p === "/" || p === "/features") return DEFAULT_TITLE;
  if (!isAppPath(p)) return NOT_FOUND_TITLE;
  if (p === "/admin" || p.startsWith("/admin/")) return withBrand("Sign in");     // never names a page only some open
  const t = titleFor(p);
  return t === DEFAULT_TITLE ? withBrand("Sign in") : `Sign in · ${t}`;
}

/** Set the tab's title from a page (runs after the shell's default for the address, so it wins). Pass null while the
 * page has nothing better than the default. */
export function useDocTitle(name: string | null | undefined) {
  const { pathname } = useLocation();
  useEffect(() => { if (name) document.title = withBrand(name); }, [name, pathname]);
}
