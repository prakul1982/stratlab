import type { Focus } from "./types";
import { NAV, SPACE_LIST, locate, type SpaceId } from "./nav";

/** StratLab's spaces. Trade is the strategy lab StratLab started as; Invest is company research; Money is the person's
 * own finances; Mine is the person's own home (what they pinned, their money and what is coming up). A space only
 * decides which menu shows and which home page `/` opens: every page stays one link away whatever is picked. */
export type Space = SpaceId;
/** What the menu shows: one space, or Mine (the person's own). */
export type SpaceView = Space | "mine";

export const SPACE_IDS: Space[] = SPACE_LIST;

export const SPACES: Record<Space, { label: string; home: string; what: string; paths: RegExp }> = {
  trade: { label: "Trade", home: NAV.trade.home, what: "Test strategies, paper trade them, options", paths: /^\/(trade|notebooks|new|n|paper|options|import|library)(\/|$)/ },
  invest: { label: "Invest", home: NAV.invest.home, what: "Research companies, scans, watchlist, alerts", paths: /^\/(invest|research|news|alerts|scans|watchlist|calendar)(\/|$)/ },
  money: { label: "Money", home: NAV.money.home, what: "Holdings, tax and everything you own", paths: /^\/(money|holdings|tax-report)(\/|$)/ },
};

/** The space a page belongs to; null for pages every space shares (Account, Plans, Admin). */
export function spaceOf(path: string): Space | null {
  return SPACE_IDS.find((s) => SPACES[s].paths.test(path)) ?? null;
}

/** A page in more than one space's menu (the Calendar's tabs: its menu entry is in every space): it opens inside the space it
 * was opened from, not its own address's space (owner, 4 Nov: "whenever we click on something in Calendar it redirects to
 * Invest"). Worked out from the menu map itself (lib/nav.ts `start`), so any entry shared later is covered too. */
export function sharedPage(path: string): boolean {
  return !!locate(path)?.group.start;
}

/** The space a shared page's address carries (?space=trade), so a shared or bookmarked link keeps the space it was opened in. */
export function spaceParam(search: string | null | undefined): Space | null {
  const v = new URLSearchParams(search ?? "").get("space");
  return v === "trade" || v === "invest" || v === "money" ? v : null;
}

/** The menu an address shows: its own space's, so where you are is always in the menu. Pages that belong to no space
 * (Account, Settings, Plans, Admin, My space) show Mine's menu, as their breadcrumb says. Mine keeps its own menu on a
 * page it links to (`keepsMine`: a pinned page, Briefs) while Mine is the menu showing. A page in several spaces' menus
 * (`sharedPage`) stays in the space its address names (?space=), else in the space of the page it was reached from in
 * this visit (`from`; none on a fresh load, which opens the address's own space). Worked out from the address on every
 * render, so it never lags behind a saved choice that loads later. */
export function menuView(path: string, showing: SpaceView, keepsMine = false, o: { search?: string; from?: SpaceView | null } = {}): SpaceView {
  if (path === "/") return showing;          // the front door goes on to the home of the menu showing
  const here = spaceOf(path);
  if (!here) return "mine";
  // a shared page reached from a space (or naming one) stays in it before Mine's own claim: Mine lists the Calendar too, and
  // the account's saved choice ("My space") arriving after the click must not pull Trade's Calendar into it
  const kept = sharedPage(path) ? spaceParam(o.search) ?? (o.from && o.from !== "mine" ? o.from : null) : null;
  if (kept) return kept;
  if (showing === "mine" && keepsMine) return "mine";
  return here;
}

/** The space someone's answer to "What brings you here?" starts them in. */
export function viewForFocus(focus: Focus | null | undefined): SpaceView | null {
  return focus === "both" ? "mine" : focus ?? null;
}

/** Mine has a home of its own: the person's net worth, the markets, what is coming up and their watchlist. */
export const MINE_HOME = "/mine";
/** The one name for it, in the tab, the breadcrumb, the menu, the page title and every sentence. */
export const MINE_NAME = "My space";

/** The home page `/` opens: the space showing. */
export function homeOf(view: SpaceView, _focus?: Focus | null): string {
  return view === "mine" ? MINE_HOME : SPACES[view].home;
}

/** The one home `/` (and the logo) opens: the space for what the person said they came for (Settings → What you see first),
 * else the account's last choice, else My space. Not the space last visited on this device: `/` went to Trade after a look
 * at /trade, and to Money for someone set to "All of it" (DI-013). */
export function startView(focus: Focus | null | undefined, accountSpace?: unknown): SpaceView {
  return viewForFocus(focus) ?? viewFromSaved(accountSpace) ?? "mine";
}

export const SPACE_HOMES = [...SPACE_IDS.map((s) => SPACES[s].home), MINE_HOME];

/** The view's name as the server and older versions of the app wrote it: Mine was once called "All". */
export function viewFromSaved(v: unknown): SpaceView | null {
  return v === "all" || v === "mine" ? "mine" : v === "trade" || v === "invest" || v === "money" ? v : null;
}
export const viewToServer = (v: SpaceView) => (v === "mine" ? "all" : v);

const KEY = "stratlab.space";

/** The menu last shown on this device, if any. */
export function savedView(): SpaceView | null {
  let v: string | null = null;
  try { v = localStorage.getItem(KEY); } catch { /* storage off */ }
  return viewFromSaved(v);
}

export function saveView(v: SpaceView) {
  try { localStorage.setItem(KEY, v); } catch { /* storage off */ }
}
