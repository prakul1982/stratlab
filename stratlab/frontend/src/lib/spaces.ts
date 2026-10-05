import type { Focus } from "./types";

/** StratLab's three spaces. Trade is the strategy lab StratLab started as; Invest is company research; Money is the
 * person's own finances. A space only decides which menu shows and which home page `/` opens: every page stays one
 * link away whatever is picked. */
export type Space = "trade" | "invest" | "money";
/** What the menu shows: one space, or every group folded ("all"). */
export type SpaceView = Space | "all";
/** The sidebar's menu groups. */
export type GroupId = "notebooks" | "trading" | "research" | "watch" | "money";

export const SPACE_IDS: Space[] = ["trade", "invest", "money"];

export const SPACES: Record<Space, { label: string; home: string; what: string; groups: GroupId[]; paths: RegExp }> = {
  trade: {
    label: "Trade", home: "/trade", what: "Test strategies, paper trade them, options",
    groups: ["notebooks", "trading"], paths: /^\/(trade|notebooks|new|n|paper|options|import|library)(\/|$)/,
  },
  invest: {
    label: "Invest", home: "/invest", what: "Research companies, scans, watchlist, alerts",
    groups: ["research", "watch"], paths: /^\/(invest|research|news|alerts|scans|watchlist)(\/|$)/,
  },
  money: {
    label: "Money", home: "/money", what: "Holdings, tax and everything you own",
    groups: ["money"], paths: /^\/(money|holdings|tax-report)(\/|$)/,
  },
};

/** Every group in the order "All" lists them: Trade first, as the brand's origin. */
export const ALL_GROUPS: GroupId[] = SPACE_IDS.flatMap((s) => SPACES[s].groups);

/** The space a page belongs to; null for pages every space shares (Account, Plans, Admin). */
export function spaceOf(path: string): Space | null {
  return SPACE_IDS.find((s) => SPACES[s].paths.test(path)) ?? null;
}

/** The space someone's answer to "What brings you here?" starts them in. */
export function viewForFocus(focus: Focus | null | undefined): SpaceView | null {
  return focus === "both" ? "all" : focus ?? null;
}

/** "All" has a home of its own: the newest features and the top tools of each space. */
export const ALL_HOME = "/all";

/** The home page `/` opens: the space showing, or for "All" its own home. */
export function homeOf(view: SpaceView, _focus?: Focus | null): string {
  return view === "all" ? ALL_HOME : SPACES[view].home;
}

export const SPACE_HOMES = [...SPACE_IDS.map((s) => SPACES[s].home), ALL_HOME];

const KEY = "stratlab.space";
const VIEWS: SpaceView[] = [...SPACE_IDS, "all"];

/** The menu last shown on this device, if any. */
export function savedView(): SpaceView | null {
  let v: string | null = null;
  try { v = localStorage.getItem(KEY); } catch { /* storage off */ }
  return VIEWS.includes(v as SpaceView) ? (v as SpaceView) : null;
}

export function saveView(v: SpaceView) {
  try { localStorage.setItem(KEY, v); } catch { /* storage off */ }
}
