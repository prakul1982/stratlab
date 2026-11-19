import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { locate, locateGroup } from "./nav";
import { isAppPath } from "./deepLinks";
import { BRAND, HOME_TITLE, withBrand } from "../content/seo";

/** The browser tab's title. Every page gets one from the one map of pages (lib/nav.ts): "Holdings · StratLab", the page's
 * own name in the menu and the brand, one pattern everywhere (owner, 18 Nov; content/seo.ts withBrand). A page that knows something
 * more specific (a company's name, a notebook's name) sets it with `useDocTitle`. */
export { BRAND, withBrand };
export const DEFAULT_TITLE = BRAND;

/** Pages that are not in a space's menu, by address. */
const OWN: Record<string, string> = {
  "/mine": "My space", "/account": "Account", "/settings": "Settings", "/assistant": "Connect an AI assistant", "/app": "Get the app",
  "/invite": "Invite friends", "/plans": "Plans", "/features": "All features", "/dev/kit": "Design kit", "/new": "New notebook",
  "/trade": "Trade home", "/invest": "Invest home", "/money": "Money home", "/research/compare": "Compare", "/help": "Help",
};

/** The Admin sections' names (pages/admin/AdminContext.tsx SECTIONS), by the path after /admin/. */
export const ADMIN_SECTIONS: Record<string, string> = {
  users: "Users and growth", money: "Money", data: "Data and jobs", quality: "Quality", system: "System", emails: "Email previews",
};

/** A notebook's tab titles: the notebook itself is "<notebook>", one of its runs "Run v2: <notebook>" and the compare
 * page "Compare runs: <notebook>", so a notebook and its run pages never share a title. */
export const notebookTitle = (name: string | null | undefined, page?: string | null) => (name ? (page ? `${page}: ${name}` : name) : null);

/** The title an address gets before the page adds anything of its own. */
export function titleFor(path: string): string {
  return withBrand(pageName(path));
}

/** The page's own name for its tab (null where the address names no page): the name it has in the menu, alone. A renamed
 * tab ("Breadth", was "Market breadth") and an entry page ("Practise") are named like every other page, not "Breadth · Market
 * today" beside "Movers" (LIVE13A-023). */
export function pageName(path: string): string | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (OWN[p]) return OWN[p];
  if (p === "/admin" || p.startsWith("/admin/")) return `Admin: ${ADMIN_SECTIONS[p.split("/")[2]] ?? "Overview"}`;
  const company = p.match(/^\/research\/(IN|US)\/([^/]+)(\/deep)?$/);
  if (company) {
    // the company's name from the first frame when it has been opened before (R8O-009: "POLYCAB · StratLab" until the
    // page's numbers arrived)
    const sym = decodeURIComponent(company[2]).toUpperCase();
    const name = knownName(company[1], sym);
    return `${companyName(name, sym)}${company[3] ? " deep dive" : ""}`;
  }
  const chart = p.match(/^\/chart\/([^/]+)\/([^/]+)$/);
  if (chart) { let sym = chart[2]; try { sym = decodeURIComponent(sym); } catch { /* as written */ } return `${sym.toUpperCase()} chart`; }
  const g = locateGroup(p);
  if (g) return g.group.label;
  return locate(p)?.page.label ?? null;
}

/** A company's name for its tab: "Reliance Industries (RELIANCE)", or the symbol alone when the name is the symbol or not
 * known yet. The page's first frame and the drawn page give the same title, with no price in it (owner, 18 Nov). */
export const companyName = (name: string | null | undefined, symbol: string) =>
  name && name.toUpperCase() !== symbol.toUpperCase() ? `${name} (${symbol})` : symbol;

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

/** The title for a visitor who isn't signed in: "Sign in: Options builder · StratLab" on an app address (so a tab says
 * what it is waiting for), "Plans · StratLab" on /pricing and /plans, "Terms · StratLab" on a policy, "Page not found ·
 * StratLab" where nothing is, the brand alone on the landing page itself. */
export function signedOutTitle(path: string): string {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  if (PUBLIC_TITLES[p]) return withBrand(PUBLIC_TITLES[p]);
  if (p === "/plans" || p === "/pricing" || p === "/upgrade") return withBrand("Plans");      // signed in or out, one name (LIVE13A-023)
  if (p === "/help") return withBrand("Help");
  if (p === "/") return HOME_TITLE;
  if (p === "/tour") return withBrand("How StratLab works");          // a visitor's tour: the landing's spaces and steps (LIVE9B-029)
  if (p === "/features") return withBrand("What StratLab does");      // its own title, not the home page's (DI-033)
  if (p === "/app") return withBrand("Get the app");                 // readable signed out: the install steps (DI-029)
  if (!isAppPath(p)) return NOT_FOUND_TITLE;
  if (p === "/admin" || p.startsWith("/admin/")) return withBrand("Sign in");     // never names a page only some open
  const name = pageName(p);
  return withBrand(name ? `Sign in: ${name}` : "Sign in");
}

/** Set the tab's title from a page (runs after the shell's default for the address, so it wins). Pass null while the
 * page has nothing better than the default. */
export function useDocTitle(name: string | null | undefined) {
  const { pathname } = useLocation();
  useEffect(() => { if (name) document.title = withBrand(name); }, [name, pathname]);
}
