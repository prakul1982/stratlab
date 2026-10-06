import type { Focus } from "./types";
import { NAV, SPACE_LIST, type SpaceId } from "./nav";

/** StratLab's spaces. Trade is the strategy lab StratLab started as; Invest is company research; Money is the person's
 * own finances; Mine is the person's own home (what they pinned, their money and what is coming up). A space only
 * decides which menu shows and which home page `/` opens: every page stays one link away whatever is picked. */
export type Space = SpaceId;
/** What the menu shows: one space, or Mine (the person's own). */
export type SpaceView = Space | "mine";

export const SPACE_IDS: Space[] = SPACE_LIST;

export const SPACES: Record<Space, { label: string; home: string; what: string; paths: RegExp }> = {
  trade: { label: "Trade", home: NAV.trade.home, what: "Test strategies, paper trade them, options", paths: /^\/(trade|notebooks|new|n|paper|options|import|library)(\/|$)/ },
  invest: { label: "Invest", home: NAV.invest.home, what: "Research companies, scans, watchlist, alerts", paths: /^\/(invest|research|news|alerts|scans|watchlist)(\/|$)/ },
  money: { label: "Money", home: NAV.money.home, what: "Holdings, tax and everything you own", paths: /^\/(money|holdings|tax-report)(\/|$)/ },
};

/** The space a page belongs to; null for pages every space shares (Account, Plans, Admin). */
export function spaceOf(path: string): Space | null {
  return SPACE_IDS.find((s) => SPACES[s].paths.test(path)) ?? null;
}

/** The space someone's answer to "What brings you here?" starts them in. */
export function viewForFocus(focus: Focus | null | undefined): SpaceView | null {
  return focus === "both" ? "mine" : focus ?? null;
}

/** Mine has a home of its own: the person's net worth, the markets, what is coming up and their watchlist. */
export const MINE_HOME = "/mine";

/** The home page `/` opens: the space showing. */
export function homeOf(view: SpaceView, _focus?: Focus | null): string {
  return view === "mine" ? MINE_HOME : SPACES[view].home;
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
