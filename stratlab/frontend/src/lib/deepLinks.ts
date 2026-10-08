/* What an address in the app is, for someone who isn't signed in (or for a page that doesn't exist): the app's own
 * addresses, the landing page's, and a name for each ("Holdings", "this notebook", the company's symbol), so a signed-out
 * visitor on /research/IN/RELIANCE gets "Sign in to see RELIANCE" instead of the landing page at that address, and an
 * address nobody routes gets "Page not found". unit/deepLinks.test.mjs checks APP_ROUTES against main.tsx's routes. */
import { locate, locateGroup } from "./nav";

/** Every route main.tsx has for a signed-in person (its <Route path>s, without the catch-all). */
export const APP_ROUTES = [
  "/", "/mine", "/all", "/features", "/trade/g/:group", "/invest/g/:group", "/money/g/:group", "/trade", "/invest", "/money",
  "/notebooks", "/new", "/n/:id", "/n/:id/market", "/n/:id/compare", "/n/:id/e/:v", "/import", "/library", "/options",
  "/trade/positioning", "/trade/positioning/stocks", "/options/s/:sid", "/paper", "/paper/:sid", "/trade/journal",
  "/trade/fo-changes", "/trade/closing-auction", "/trade/replay", "/trade/signals", "/trade/signals/:sid", "/trade/events",
  "/plans", "/pricing", "/upgrade", "/help", "/account", "/settings", "/assistant", "/app", "/invite", "/admin/*", "/news",
  "/holdings", "/tax-report", "/money/net-worth", "/money/mutual-funds", "/money/tax-tools", "/money/calendar",
  "/money/us-tax", "/money/itr", "/money/sip-test", "/money/rates", "/alerts", "/research", "/research/themes",
  "/research/pulse", "/research/compare", "/research/watchlist", "/research/scan", "/research/scans", "/scans",
  "/watchlist", "/research/screens", "/research/rotation", "/invest/breadth", "/invest/etf-gaps", "/invest/holders",
  "/invest/business-updates", "/invest/stock-lending", "/invest/margin-funding", "/dev/kit", "/research/filings",
  "/research/results", "/research/corporate-actions", "/research/IN/:symbol/deep", "/research/US/:symbol/deep",
  "/research/investor", "/research/:region/:symbol",
];

const PATTERNS = APP_ROUTES.map((r) => new RegExp("^" + r.replace(/\/\*$/, "(/.*)?").replace(/:[A-Za-z]+/g, "[^/]+") + "/?$"));

/** The landing page and its sections: shown to a visitor as the landing page, scrolled to the section. */
export const LANDING_SECTIONS: Record<string, string | null> = { "/": null, "/pricing": "pricing", "/plans": "pricing", "/upgrade": "pricing", "/help": "faq", "/features": "trade" };

const clean = (path: string) => path.split(/[?#]/)[0] || "/";

/** One of the app's addresses (a page a signed-in person can open, or one that redirects to one). */
export function isAppPath(path: string): boolean {
  const p = clean(path);
  return PATTERNS.some((re) => re.test(p));
}

/** A landing-page address for a visitor: "/", "/pricing", "/help"… (the section to scroll to, or null for the top). */
export function landingSection(path: string): string | null | undefined {
  const p = clean(path).replace(/(.)\/$/, "$1");
  return p in LANDING_SECTIONS ? LANDING_SECTIONS[p] : undefined;
}

export type Described = { what: string; company?: { region: "IN" | "US"; symbol: string; deep: boolean } };

/** A name for what's at this address, for "Sign in to see …". Null for an address the app doesn't have. */
export function describePath(path: string): Described | null {
  const p = clean(path).replace(/(.)\/$/, "$1");
  if (!isAppPath(p)) return null;
  const co = p.match(/^\/research\/(IN|US)\/([^/]+?)(\/deep)?$/i);
  if (co && !["themes", "pulse", "compare", "watchlist", "scan", "scans", "screens", "rotation", "filings", "results", "corporate-actions", "investor"].includes(co[2].toLowerCase())) {
    let symbol = co[2];
    try { symbol = decodeURIComponent(symbol); } catch { /* keep it as written */ }
    symbol = symbol.toUpperCase().slice(0, 20);
    const deep = !!co[3];
    return { what: deep ? `the deep dive on ${symbol}` : symbol, company: { region: co[1].toUpperCase() as "IN" | "US", symbol, deep } };
  }
  if (/^\/n\/[^/]+\/e\//.test(p)) return { what: "this experiment" };
  if (/^\/n\/[^/]+\/compare$/.test(p)) return { what: "this comparison of experiments" };
  if (/^\/n\/[^/]+/.test(p)) return { what: "this notebook" };
  if (/^\/paper\/[^/]+$/.test(p)) return { what: "this paper trading session" };
  if (/^\/options\/s\/[^/]+$/.test(p)) return { what: "this options session" };
  if (/^\/trade\/signals\/[^/]+$/.test(p)) return { what: "this signal session" };
  if (/^\/admin(\/|$)/.test(p)) return { what: "the admin pages" };
  const named: Record<string, string> = {
    "/": "your StratLab", "/mine": "My space", "/all": "My space", "/trade": "your Trade home", "/invest": "your Invest home",
    "/money": "your Money home", "/notebooks": "your notebooks", "/new": "the idea builder", "/plans": "the plans",
    "/account": "your account", "/settings": "your settings", "/assistant": "your AI assistant keys", "/app": "the app",
    "/invite": "your invite link", "/news": "your briefs", "/features": "everything StratLab does", "/dev/kit": "the design kit",
  };
  if (named[p]) return { what: named[p] };
  const g = locateGroup(p);
  if (g) return { what: g.group.label };
  const at = locate(p);
  return { what: at ? at.page.label : "this page" };
}
