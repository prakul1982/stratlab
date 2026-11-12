/* The in-app intro (owner, 12 Nov: "the intro we have on the website itself is also trash, it only shows like 5 steps to get in"):
 * after the welcome question, a short tour of the space the person picked, each step on a real page pointing at a real control;
 * one tour per space, offered the first time they enter that space, and all of them from "Take the tour" in the Account menu.
 * Pure data and rules, no React: components/Tour.tsx draws them and unit/intro.test.mjs checks them (every page is in the menu
 * map, no step points at a page its plan locks without saying so, no advice words). */
import { planOf, PLAN_NAME, LIMITS, FLAGS } from "./plans";
import { gateFor } from "./gates";
import { spaceOf, sharedPage } from "./spaces";

export type TourId = "mine" | "trade" | "invest" | "money";
export const TOUR_IDS: TourId[] = ["mine", "trade", "invest", "money"];

/** Something the step lets the person do there and then: open search, or open what the ringed list links to first. */
export type StepAct = { label: string; kind: "search" } | { label: string; kind: "follow"; sel: string };

export interface IntroStep {
  id: string;
  title: string;
  body: string;
  /** The text on a phone, when it differs (a shortcut key means nothing on a touch screen). */
  phone?: string;
  /** The page the step is on; opened when the page showing isn't one of `here`. None: the step is about the menu, any page. */
  go?: string;
  /** Pages that already show the thing (a company step is happy on any company's page). Default: `go` exactly. */
  here?: RegExp;
  /** No fixed address: open `page`, then the first link there matching `sel` (the company step opens the first suggested company). */
  via?: { page: string; sel: string };
  /** Where the ring goes: CSS selectors, any of which may match (the laptop's place, then the phone's). */
  at: string[];
  /** Used only when none of `at` shows up in time (a page still loading, an empty account). */
  or?: string;
  /** On a phone the thing is inside the menu: the step opens the menu (DI-023). */
  menu?: boolean;
  /** A plan feature part of what the step shows needs: said in the note when the person's plan lacks it. */
  flag?: string;
  /** Said on the Free plan: a monthly limit the step's feature has there. */
  free?: string;
  act?: StepAct;
}

export interface IntroTour { id: TourId; name: string; line: string; steps: IntroStep[] }

const exactly = (p: string) => new RegExp(`^${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}$`);
/** A company page, any company, India or the US (not its deep dive). */
const COMPANY = /^\/research\/(IN|US)\/[^/]+$/;
/** The company suggestions under Look up a company's search box (the app's own starters): the company step opens the first. */
const SUGGESTED = "main a.btn[href^='/research/IN/'], main a.btn[href^='/research/US/']";

export const TOURS: Record<TourId, IntroTour> = {
  mine: {
    id: "mine", name: "Getting around", line: "My space, the four spaces, search, Market Watch, the daily brief and your account.",
    steps: [
      { id: "mine-home", title: "My space is yours", go: "/mine", at: ["main .mine-slot"], or: "main h1",
        body: "Your net worth, today's gain or loss on your holdings, paper sessions, the markets and what is coming up, on one page. Customise hides cards and sets their order." },
      { id: "spaces", title: "Four spaces", at: [".sidebar .space-switch"], menu: true,
        body: "Trade is for testing trading ideas on past prices and paper trading them. Invest is for researching companies and the market. Money is what you own and the tax on it. Each has its own menu and home page." },
      { id: "ask", title: "Ask or do anything", at: [".sidebar .search-btn", ".topbar [aria-label='Search or ask anything']"],
        body: "Type a company, a page or a question: \"heatmap\", \"results this week\", \"test RSI below 30 on NIFTY 50\". Ctrl K opens it from any page.",
        phone: "Type a company, a page or a question: \"heatmap\", \"results this week\", \"test RSI below 30 on NIFTY 50\". The magnifier at the top opens it from any page.",
        act: { label: "Try it", kind: "search" } },
      { id: "watch", title: "Market Watch, on every page", at: [".mw-launch", ".topbar [aria-label='Markets']"],
        body: "Lists of any stock, index, coin or currency with live prices, and a chart for each, in a panel that stays open as you move from page to page." },
      { id: "brief", title: "A brief after each close", go: "/news", at: ["main .news-issue h2", "main .news-pick"], or: "main h1",
        body: "A short brief after each market close: India, the US, and what changed for the stocks you hold or watch. Settings, under Notifications, sends it by email." },
      { id: "account", title: "Your account, and these tours", at: [".sidebar .acct-btn"], menu: true,
        body: "The Account button opens your plan, Settings and Help. Dark mode is in Settings, under Experience. “Take the tour” there brings back any of these tours." },
    ],
  },
  trade: {
    id: "trade", name: "Trade", line: "Test an idea on years of real prices, read its verdict, paper trade it, price options.",
    steps: [
      { id: "idea", title: "Describe an idea, get a test", go: "/new", at: ["main #idea"],
        body: "Write a trading idea in plain words, like “the 20-day average crossing above the 50-day on NIFTY 50”. StratLab turns it into rules you can read and edit, then tests them on years of real prices after costs." },
      { id: "verdict", title: "A verdict, with four checks for luck", go: "/library", at: ["main tbody tr .badge", "main tbody tr"], or: "main h1",
        body: "Every test ends in a verdict with four checks: data the rules never saw, nearby settings, a bad-luck drawdown and enough trades. The library shows published rules with the verdict each earned, good or bad; Copy re-tests one in a notebook of your own." },
      { id: "paper", title: "Paper trade with fake money", go: "/paper", at: ["main .k-card", "main .btn"], or: "main h1",
        body: "Run a notebook's rules live on real prices with fake money until you stop them. Each session keeps its orders, its open position and its running result. StratLab never places a real order." },
      { id: "options", title: "Options, priced before you start", go: "/options", at: ["main [data-testid=opt-words]"], or: "main h1", flag: "options",
        body: "Pick an index, an expiry and a structure (a straddle, a strangle, an iron condor or your own legs). It is written out here in words, with the charges, breakevens, Greeks and payoff below; then paper trade it." },
      { id: "fo", title: "Who holds what in F&O", go: "/trade/positioning", at: ["main [data-testid=part-figs]"], or: "main h1", flag: "positioning",
        body: "Open interest by clients, FIIs, DIIs and proprietary traders, the FIIs' and DIIs' net flows in the cash market, the put-call ratio, max pain and India VIX, from the exchange's own files." },
    ],
  },
  invest: {
    id: "invest", name: "Invest", line: "Any company in depth, Themes with slides, the Heatmap and every date ahead.",
    steps: [
      { id: "lookup", title: "Look up any company", go: "/research", at: ["main input.k-input"],
        body: "Type any Indian or US company by its name or symbol, or open one of the suggestions under the box.",
        act: { label: "Open one", kind: "follow", sel: SUGGESTED } },
      { id: "company", title: "One company, in depth", via: { page: "/research", sel: SUGGESTED }, here: COMPANY, at: ["main a.btn[href$='/deep']"], or: "main h1",
        // FREE-TIER: 1 deep dive a month and no slide decks (the sample deck on Plans shows one)
        free: `On Free: ${LIMITS.free.deepdives_per_month} deep dive a month; slide decks are on Basic.`,
        body: "Its price chart, key numbers, results, who owns it, filings, deals and an AI read of the figures. Deep dive adds ten years of figures, the business and its plans read from the company's own documents, an investor checklist, and slides to download." },
      { id: "themes", title: "Themes, company by company", go: "/research/themes", at: ["main form"], or: "main h1",
        body: "Type a sector or a trend. StratLab lists the listed companies in it, places each in a layer of the value chain with that layer's figures, and turns the whole theme into slides (PowerPoint or PDF) to download." },
      { id: "heatmap", title: "The whole market at a glance", go: "/invest/heatmap", at: ["main [data-testid=heatmap]"], or: "main h1",
        body: "Each company of an index is a tile, sized by market value and coloured by its move over the period you pick; a click opens the company. Mood, Breadth, Sectors and Flows are the tabs beside it." },
      { id: "dates", title: "Every date ahead", go: "/calendar", at: ["main [data-testid=cal-all]"], or: "main h1",
        body: "Results days, dividends and splits, IPO openings and listings, the RBI, the Fed and F&O expiries in one table, for every company or only yours. Results and IPOs have tabs of their own." },
    ],
  },
  money: {
    id: "money", name: "Money", line: "Your holdings from your broker's file, capital gains tax, net worth and tax tools.",
    steps: [
      { id: "holdings", title: "Your holdings, from your broker's file", go: "/holdings", at: ["main [data-main-action]", "main label.k-upload"], or: "main h1", flag: "filings",
        body: "Upload the holdings file your broker gives you, or add stocks by hand, to see their value, gain or loss, sectors and dividends in one place." },
      { id: "tax", title: "Capital gains, worked out", go: "/tax-report", at: ["main label.k-upload"], or: "main h1", flag: "tax_export",
        body: "Upload tradebooks or your broker's tax P&L: each sale is matched to its purchase, split into short and long term at the rates for its date, with the exemption and set-off, year by year. An estimate to check with your CA." },
      { id: "networth", title: "Everything you own and owe", go: "/money/net-worth", at: ["main button.btn:not(.quiet)"], or: "main h1", flag: "networth",
        body: "Add deposits, EPF, PPF, NPS, gold, property and loans beside your holdings and funds; each is valued by its own rule, with its date." },
      { id: "taxtools", title: "Dividends, advance tax and the exemption", go: "/money/tax-tools", at: ["main [aria-label='Tax tools']"], or: "main h1", flag: "tax_tools",
        body: "Dividends with the TDS expected on them, advance tax due dates, and how much of the year's long-term exemption is used." },
    ],
  },
};

/** The tour a welcome answer starts: the space they came for, or Getting around for "All of it". */
export function tourForFocus(focus: string | null | undefined): TourId {
  return focus === "trade" || focus === "invest" || focus === "money" ? focus : "mine";
}

/** The pages a step is happy on. */
export const stepHere = (s: IntroStep): RegExp | null => s.here ?? (s.go ? exactly(s.go) : s.via ? exactly(s.via.page) : null);
/** The step's page is the one showing (a menu step is on any page). */
export const onStepPage = (s: IntroStep, path: string) => { const h = stepHere(s); return !h || h.test(path); };

type Features = Record<string, boolean> | null | undefined;

/** What the step shows that the person's plan doesn't include, in one factual line, or null. */
export function lockLine(s: IntroStep, features: Features): string | null {
  if (!s.flag || features?.[s.flag] !== false) return null;
  const name = FLAGS.find(([f]) => f === s.flag)?.[1] ?? s.flag;
  return `${name}: on the ${PLAN_NAME[planOf(s.flag)]} plan.`;
}

/** The step's plan lines: what is locked, and a Free limit. */
export function planLines(s: IntroStep, features: Features, plan: string | null | undefined): string[] {
  const out: string[] = [];
  const lock = lockLine(s, features);
  if (lock) out.push(lock);
  if (s.free && plan === "free") out.push(s.free);
  return out;
}

/** A step on a page whose plan gate covers the whole page would be pointing at a locked page: none may. */
export const lockedWhole = (s: IntroStep) => [s.go, s.via?.page].some((p) => !!p && !!gateFor(p)?.whole);

/* ---------- what the person has seen, kept on this device per account ---------- */

export interface IntroState {
  /** Started a tour from the welcome or the tour list: other spaces' tours are offered as they enter them. */
  on: boolean;
  done: TourId[];
  /** Offers they said "Not now" to. */
  no: TourId[];
  /** A tour closed part way: where it stopped. */
  at: { tour: TourId; step: number } | null;
}

export const EMPTY: IntroState = { on: false, done: [], no: [], at: null };
const key = (uid: string | null | undefined) => `stratlab.intro.${uid ?? "guest"}`;
const isTour = (x: unknown): x is TourId => typeof x === "string" && (TOUR_IDS as string[]).includes(x);

export function parseState(raw: string | null): IntroState {
  try {
    const j = raw ? JSON.parse(raw) : null;
    if (!j || typeof j !== "object") return { ...EMPTY };
    const at = j.at && isTour(j.at.tour) && Number.isInteger(j.at.step) ? { tour: j.at.tour as TourId, step: Math.max(0, j.at.step as number) } : null;
    return { on: !!j.on, done: (Array.isArray(j.done) ? j.done : []).filter(isTour), no: (Array.isArray(j.no) ? j.no : []).filter(isTour), at };
  } catch { return { ...EMPTY }; }
}
export function loadState(uid: string | null | undefined): IntroState {
  try { return parseState(localStorage.getItem(key(uid))); } catch { return { ...EMPTY }; }
}
export function saveState(uid: string | null | undefined, s: IntroState) {
  try { localStorage.setItem(key(uid), JSON.stringify(s)); } catch { /* private window */ }
}

const add = (list: TourId[], t: TourId) => (list.includes(t) ? list : [...list, t]);
/** A tour started: offers are on from now, and a tour picked from the list is no longer "not now". */
export const started = (s: IntroState, t: TourId): IntroState => ({ ...s, on: true, no: s.no.filter((x) => x !== t) });
/** A tour finished: done, and nothing to resume. */
export const finished = (s: IntroState, t: TourId): IntroState => ({ ...s, done: add(s.done, t), at: s.at?.tour === t ? null : s.at });
/** A tour closed part way at `step`: kept, to resume from the tour list; and not offered again by itself. */
export const stopped = (s: IntroState, t: TourId, step: number): IntroState => ({ ...s, no: add(s.no, t), at: step > 0 ? { tour: t, step } : s.at?.tour === t ? null : s.at });
export const declined = (s: IntroState, t: TourId): IntroState => ({ ...s, no: add(s.no, t) });

/** The space a page is in, for the offer: a space's own page, or My space's home. A page every space shares (the Calendar) is
 * none of them, nor are Account, Settings and the like. */
export function tourOfPath(path: string): TourId | null {
  if (path === "/mine") return "mine";
  if (sharedPage(path)) return null;
  return spaceOf(path);
}

/** The tour to offer on this page, or null: only to someone who started the intro, the first time they are in a space whose tour
 * they have neither taken nor waved away. */
export function offerFor(s: IntroState, path: string): TourId | null {
  if (!s.on) return null;
  const t = tourOfPath(path);
  return t && !s.done.includes(t) && !s.no.includes(t) ? t : null;
}

/* ---------- the tour that is showing, kept for a reload ---------- */
const RUN = "stratlab.intro.run";
export type Run = { tour: TourId; step: number; from?: string };
export function loadRun(): Run | null {
  try {
    const j = JSON.parse(sessionStorage.getItem(RUN) ?? "null");
    if (!j || !isTour(j.tour) || !Number.isInteger(j.step)) return null;
    const step = Math.max(0, Math.min(j.step as number, TOURS[j.tour as TourId].steps.length - 1));
    return { tour: j.tour as TourId, step, from: typeof j.from === "string" && j.from.startsWith("/") ? j.from : undefined };
  } catch { return null; }
}
export function saveRun(r: Run | null) {
  try { if (r) sessionStorage.setItem(RUN, JSON.stringify(r)); else sessionStorage.removeItem(RUN); } catch { /* storage off */ }
}
