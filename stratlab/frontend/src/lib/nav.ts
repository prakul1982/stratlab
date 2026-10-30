import { NAV_GROUPS, type NavEntry } from "./navGroups";

/** The whole map of StratLab: which page lives in which menu entry of which space. The sidebar, the tabs at the top of a
 * page, the entries' own pages, the breadcrumb, "All features", "More you can do" and ⌘K are all drawn from this one list,
 * so a page added here shows up in all of them. Keep it in the order people use things.
 *
 * IA-1 (owner, 29 Oct: "43 menu entries → about 15, nothing removed"): a menu entry (a NavGroup) is one page of tabs, and
 * each of its tabs (a NavPage) is a page that was an entry of its own before. Every tab keeps the address it always had,
 * so links in emails, briefs, the blog and bookmarks open the right tab; `was` keeps the old menu name for search, Help
 * and the "(Screener)" in a search result. */
export type SpaceId = "trade" | "invest" | "money";

export interface NavPage {
  /** The page's own address; its tab links here. */
  to: string;
  /** Its name as a tab (and in the breadcrumb). */
  label: string;
  /** One line on what it is for (a card on the entry's page, the line on "All features"). */
  line: string;
  /** A fuller line for its card on the entry's page. */
  blurb: string;
  /** Everyday words people might search for ("MTF", "borrowed money"): ⌘K finds the page by these too. */
  words: string;
  /** Name of a sidebar icon (see ICONS in Shell). */
  icon: string;
  /** Other addresses that are part of this page (a company's page is part of "Look up a company"). */
  also?: RegExp;
  /** Plan feature flag (plans.ts) when the page is on a paid plan. */
  flag?: string;
  /** Only part of the page is on `flag`'s plan, and the page has no gate of its own (lib/gates.ts): its card says
   * "Basic for part" (My Holdings' filings and dividends, DP2-009). */
  part?: boolean;
  /** The name it had in the menu before IA-1, when that was another ("Screener" for Find stocks' Figures). */
  was?: string;
  /** A tab of an entry every space shares (Calendar): the space it belongs to, which its address already says. */
  space?: SpaceId;
}
export interface NavGroup {
  id: string; label: string; blurb: string;
  /** The sidebar's icon for the entry. */
  icon: string;
  /** Its tabs, in order (one page: no tabs). */
  pages: NavPage[];
  /** The ids of the menu groups it took over (IA-1), so an old group page (/trade/g/build-and-test) opens this one. */
  was?: string[];
  /** In every space's menu (Calendar): where each space's entry opens it, pre-filtered for that space. */
  start?: Partial<Record<SpaceId, string>>;
}

const fromData = (to: string): NavEntry | undefined =>
  [...NAV_GROUPS.Trade, ...NAV_GROUPS.Invest, ...NAV_GROUPS.Money].find((e) => e.to === to);

/** A page whose texts are already written for its card on a space's home (NAV_GROUPS) reuses them. */
function page(to: string, label: string, icon: string, words: string, o: { line?: string; blurb?: string; also?: RegExp; flag?: string; part?: boolean; was?: string; space?: SpaceId } = {}): NavPage {
  const d = fromData(to);
  const line = o.line ?? d?.title ?? o.blurb ?? d?.blurb ?? label;
  // the old name is one of the words search looks through, so "Screener" still finds Find stocks' Figures
  return { to, label, icon, words: o.was ? `${o.was.toLowerCase()} ${words}` : words, line, blurb: o.blurb ?? d?.blurb ?? line,
    also: o.also, flag: o.flag, part: o.part, was: o.was, space: o.space };
}

/** One Calendar (IA-1 item 3): results, corporate actions, IPO dates, market events and the person's own money dates, in
 * every space's menu. Each space opens it pre-filtered: Trade on the market events, Invest on every date, Money on the
 * person's own. An IPO's own page stays (part of the IPOs tab). */
const CALENDAR: NavGroup = {
  id: "calendar", label: "Calendar", icon: "calendar", was: ["company-news"],
  blurb: "Every date that matters in one place: results days, dividends and other corporate actions, IPO dates, the RBI, the Fed and data releases, F&O expiries, and your own tax and money dates.",
  start: { trade: "/trade/events", invest: "/calendar", money: "/money/calendar" },
  pages: [
    page("/calendar", "All dates", "calendar", "calendar all dates upcoming week ahead what is coming dates results dividends ex date ipo open close listing rbi fed expiry holiday tax due my stocks",
      { line: "Results, corporate actions, IPO dates and market events, day by day, for your stocks or every company.",
        blurb: "One table of the days ahead: results days, ex-dates, IPO openings, closings and listings, and the market's own events, narrowed by type, company size, sector or your own stocks.", space: "invest" }),
    page("/research/results", "Results", "calendar", "results quarterly earnings calendar results dates q1 q2 q3 q4 profit revenue announcement board meeting", { line: "Results days for your stocks, or every company, week by week.", space: "invest",
        // its card on the Calendar's page said one short line beside two of three or four: a 90px hole in it at 1280 (ui-lint R13, item 43)
        blurb: "Each company's results day this week and next, its latest quarter's revenue and profit against a year before, and how its price moved on past results days." }),
    page("/research/corporate-actions", "Corporate actions", "calendar", "corporate actions dividend dividends ex date record date bonus issue stock split rights buyback demerger", { line: "Dividends, bonus issues and splits by ex-date, for your stocks or every company.", space: "invest",
        blurb: "Dividends, bonus issues, splits, buybacks, rights issues and demergers by ex-date, with the record date, the amount or ratio and a dividend's yield at today's price." }),
    page("/invest/ipos", "IPOs", "calendar", "ipo ipos initial public offering new issue public issue drhp rhp red herring prospectus price band lot size subscription subscribed times allotment listing listing gain sme mainboard s-1 f-1 prospectus nasdaq nyse upcoming open closed recently listed",
      { flag: "ipo_alerts", also: /^\/invest\/ipos\/[^/]+$/, space: "invest",
        line: "India's and the US's IPOs: dates, price band, lot, bids and how a listing has traded against its issue price.",
        blurb: "Upcoming, open, closed and recently listed IPOs for India and the US, each with its price band, lot, size, bids by category and the facts in its offer document." }),
    page("/trade/events", "Market events", "calendar", "market events calendar rbi policy fed data releases budget index changes expiry expiries weekly monthly f&o expiry holidays results dates", { space: "trade" }),
    page("/money/calendar", "My money dates", "calendar", "money calendar tax due dates advance tax itr results dividends maturities premiums emi expiries own dates feed reminders",
      { was: "Money calendar", space: "money" }),
  ],
};

export const NAV: Record<SpaceId, { label: string; home: string; groups: NavGroup[] }> = {
  trade: {
    label: "Trade", home: "/trade", groups: [
      { id: "strategies", label: "Strategies", icon: "book", was: ["build-and-test"],
        blurb: "Turn an idea into rules and test it on years of real prices after costs, start from a strategy someone published, or bring your own.", pages: [
        page("/notebooks", "Notebooks", "book", "notebook backtest test idea strategy rules describe plain english build new experiment verdict",
          { line: "Describe a trading idea in plain words and test it on years of real prices.",
            blurb: "Each notebook holds one idea: its rules, every test run on real prices after costs, and the verdict with its four checks for luck.", also: /^\/(new|n\/.*)$/ }),
        page("/library", "Strategy library", "library", "library community shared strategies browse copy others public published marketplace publish share rules",
          { line: "Rules other traders published, each with the verdict it earned. Copy one and re-test it." }),
        page("/import", "Import", "upload", "import pine script tradingview python metatrader amibroker config json bot code upload convert",
          { was: "Import a strategy", line: "Bring a strategy from Pine Script, Python, MetaTrader or AmiBroker, or a config file.", blurb: "Pine Script, Python, MetaTrader, AmiBroker, a config file or plain words: StratLab turns it into rules you can read, edit and test." }),
      ] },
      { id: "practise", label: "Practise", icon: "pulse",
        blurb: "Trade with fake money: rules live on real prices, option structures at the live bid and ask, your own alerts, or past candles. Nothing here sends a real order.", pages: [
        page("/paper", "Paper trading", "pulse", "paper trading live forward test sessions running fake money simulate practice demo risk exposure all sessions",
          { line: "Run a notebook's rules live on real prices with fake money, until you stop them.", blurb: "Run rules live on real prices with fake money. Every session keeps its orders, its open position and its running result.", also: /^\/(paper|options\/s)\/.*$/ }),
        page("/options", "Options builder", "layers", "options straddle strangle iron fly condor spread ce pe nifty banknifty sensex fno f&o greeks delta gamma theta vega iv payoff what if expiry expiries",
          { line: "Build straddles, strangles, condors or any legs and paper trade them at the live bid and ask.", blurb: "Straddles, strangles, iron flies, condors or any structure, filled at the live bid and ask, with Greeks and a what-if payoff." }),
        page("/trade/signals", "Forward test", "pulse", "forward test signal signals webhook tradingview chartink alert alerts paper live out of sample go forward",
          { line: "Run your strategy forward on paper: each TradingView or Chartink alert is filled at StratLab's own price.", also: /^\/trade\/signals\/.*$/, flag: "signal_webhooks" }),
        page("/trade/replay", "Chart replay", "lens", "chart replay practise past candles bar replay manual trading practice journal", { flag: "chart_replay" }),
      ] },
      { id: "fo-desk", label: "F&O desk", icon: "layers", blurb: "What the futures and options market is doing: who holds what, what is changing, how the closing auction prices.", pages: [
        page("/trade/positioning", "Positioning", "layers", "positioning fii dii pro client participant open interest oi pcr put call ratio max pain iv implied volatility flows cash fno f&o derivatives vix stock futures buildup rollover basis mwpl",
          { also: /^\/trade\/positioning\/stocks$/ }),
        page("/trade/fo-changes", "F&O changes", "calendar", "f&o changes lot size lot revisions entering leaving fno list ban expiry day contract exchange circular"),
        page("/trade/closing-auction", "Closing auction", "pulse", "closing auction 15:15 15:35 reference price indicative price settlement expiry day"),
      ] },
      { id: "my-trades", label: "Trade journal", icon: "book", blurb: "Your real trades, looked at honestly.", pages: [
        page("/trade/journal", "Trade journal", "book", "trade journal round trips tradebook import pnl charges notes real trades review mistakes win rate my trades"),
      ] },
      CALENDAR,
    ],
  },
  invest: {
    label: "Invest", home: "/invest", groups: [
      { id: "companies", label: "Companies", icon: "lens",
        blurb: "Look up any Indian or US company, put two side by side, read the monthly and quarterly updates companies file, or find where a holder is named.", pages: [
        page("/research", "Look up a company", "lens", "company stock fundamentals analysis ai read valuation news research search ticker deep dive business model capex growth margins cash flow management report card concall presentation",
          { line: "Any Indian or US company: price, key numbers, results, news, and a deep dive.", blurb: "Price, valuation, growth, news and an AI read for any Indian or US company, and a deep dive into 10 years of its numbers and its business.", also: /^\/research\/(IN|US)\/.*$/ }),
        page("/research/compare", "Compare", "layers", "compare companies versus vs side by side two stocks", { line: "Two companies side by side, with an AI read of the differences." }),
        // IA-1 item 4: each company's own updates and holders are on its page and in Themes; the lists across companies stay here
        page("/invest/business-updates", "Business updates", "calendar", "business updates monthly sales automakers vehicle sales lenders quarterly figures advances deposits", { flag: "biz_updates" }),
        page("/invest/holders", "Named holders", "layers", "named holders shareholders promoter fund fii dii mutual fund shareholding pattern above 1% who owns", { flag: "holders" }),
      ] },
      { id: "find-stocks", label: "Find stocks", icon: "search", blurb: "Find companies by their figures, by what their charts do, or by what they filed.", pages: [
        page("/research/screens", "Figures", "search", "screener screen filter companies growth debt returns roe pe fundamentals ratios",
          { was: "Screener", line: "Filter companies by plain facts: growth, debt, returns." }),
        page("/research/scan", "Chart rules", "pulse", "trend scan scanner stage 2 stage two supertrend st s2 weinstein signals nifty 50 daily alert build your own custom scanner chart rules",
          { was: "Trend scan", line: "Which stocks are in a rising trend (Stage 2) with the Supertrend line also pointing up, or your own chart rules run over a group." }),
        page("/research/filings", "Filings", "bell", "red flags filings announcements qip fund raise preferential rights issue pledge resignation auditor default sebi rating downgrade",
          { was: "Red flags", line: "Fund raises, pledges, resignations and defaults your held and watched companies filed." }),
      ] },
      { id: "themes", label: "Themes", icon: "compass", blurb: "Map a sector or trend and see the listed companies linked to it.", pages: [
        page("/research/themes", "Themes", "compass", "themes sector industry shortlist ev defence banks trend map listed companies value chain", { line: "Map a sector or trend and see the listed companies linked to it." }),
      ] },
      { id: "market-today", label: "Market today", icon: "pulse", was: ["market-view"],
        blurb: "The market as a whole today: its mood, how many stocks rise and fall, which sectors lead, where the institutions' money went, and today's brief.", pages: [
        page("/research/pulse", "Mood", "pulse", "market pulse today news mood indices nifty sensex headlines index levels", { was: "Market pulse", line: "Index levels, headlines and today's mood." }),
        page("/invest/breadth", "Breadth", "pulse", "market breadth advance decline advances declines a/d line ad ratio mcclellan oscillator summation index new highs lows 52 week dma moving average trin arms thrust sector breadth nifty 500 midcap smallcap",
          { was: "Market breadth" }),
        page("/research/rotation", "Sectors", "compass", "sector rotation relative strength momentum quadrant leading lagging improving weakening rrg sectors", { was: "Sector rotation", line: "Which sectors lead, weaken, lag or improve against the market." }),
        page("/invest/flows", "Flows", "wallet", "flows fii dii fpi foreign institutional domestic institutional cash market net buying selling crore money flow",
          { line: "What foreign and domestic institutions bought and sold in India's cash market, day by day.",
            blurb: "The FIIs' and DIIs' net buying in the cash market: the latest day's bought, sold and net, and every recorded day as a table and a chart." }),
        page("/news", "Today's brief", "news", "news briefs brief newsletter digest email daily weekly market close my stocks watchlist headlines subscribe", { was: "Briefs", line: "A short brief after each market close, for India, the US and the companies you follow." }),
      ] },
      { id: "market-data", label: "Market data", icon: "wallet", blurb: "The exchange's own data on prices and borrowing: ETFs against their NAV, margin-funded positions and stock lending fees.", pages: [
        page("/invest/etf-gaps", "ETF vs NAV", "lens", "etf nav premium discount gap price iopv nifty bees goldbees fund unit value"),
        page("/invest/margin-funding", "Margin funding", "wallet", "margin funding mtf margin trading facility borrowed money broker funding leverage loan to buy shares interest pledge exposure", { flag: "mtf" }),
        page("/invest/stock-lending", "Stock lending fees", "receipt", "stock lending fees slb securities lending borrowing borrowed shares lend my shares earn on holdings"),
      ] },
      CALENDAR,
      { id: "watch", label: "Watchlist", icon: "pin", blurb: "The companies you follow, and a message when something happens to them.", pages: [
        // "Stocks", not "Watchlist" again under Watchlist (the trail read "Watchlist › Watchlist")
        page("/research/watchlist", "Stocks", "pin", "watchlist saved favourites companies i follow at a glance investor home dashboard checklist report card track record",
          { was: "Watchlist", line: "The companies you follow, as a list or each one at a glance.", also: /^\/research\/investor$/ }),
        page("/alerts", "Alerts", "bell", "alerts stock alerts price alert notify notification telegram email push trigger", { was: "Stock alerts", line: "Messages when a stock or the market does something you asked about." }),
      ] },
    ],
  },
  money: {
    label: "Money", home: "/money", groups: [
      { id: "portfolio", label: "Portfolio", icon: "wallet", was: ["what-you-own"], blurb: "Everything you own and owe, from your own files, in one place.", pages: [
        page("/money/net-worth", "Net worth", "wallet", "net worth networth assets liabilities epf ppf nps fd rd fixed deposit recurring gold sgb sovereign gold bond property cash crypto loan emi prepay prepayment home loan insurance policy premium money wealth"),
        page("/holdings", "Holdings", "book", "holdings portfolio my stocks import upload broker zerodha groww upstox angel one icici direct hdfc securities csv excel xlsx pnl p&l profit loss value sector allocation connect account demat",
          // each stock's red flags, recent filings and results date are the filings feature (Basic), said on its card (DP2-009)
          { line: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and filings.", blurb: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and each stock's filings.",
            flag: "filings", part: true }),
        page("/money/mutual-funds", "Mutual funds", "layers", "mutual funds cas cams kfintech statement xirr sip fund returns category allocation capital gains"),
      ] },
      { id: "tax", label: "Tax", icon: "receipt", blurb: "What you owe on your gains and when, laid out for you and your CA.", pages: [
        page("/tax-report", "Tax report", "receipt", "tax report capital gains stcg ltcg tradebook fifo financial year grandfathering harvest p&l loss set off"),
        page("/money/tax-tools", "Tax tools", "receipt", "tax tools dividends tds advance tax due dates ltcg exemption 1.25 lakh section 87a"),
        page("/money/us-tax", "US stocks tax", "compass", "us stocks tax foreign tax credit schedule fa form 67 tt buying rate sbi 24 month rule indian investors us shares"),
        page("/money/itr", "ITR export", "receipt", "itr export itr-ready schedule 112a cg ca pdf pack income tax return filing f&o turnover audit", { was: "ITR-ready export" }),
      ] },
      { id: "plan", label: "Plan", icon: "compass", blurb: "Look ahead: what a SIP would have done, and what your savings earn after tax.", pages: [
        page("/money/sip-test", "Test a SIP", "pulse", "sip stock sip etf sip systematic investment plan monthly weekly daily step up dip rule lump sum xirr niftybees goldbees test", { flag: "sip_luck" }),
        page("/money/rates", "Rates", "receipt", "rates fixed income fd fixed deposit t-bill treasury bill g-sec government bond repo ppf scss ssy nsc kvp post office small savings after tax yield slab tds interest", { flag: "rates_slab" }),
      ] },
      CALENDAR,
    ],
  },
};

export const SPACE_LIST: SpaceId[] = ["trade", "invest", "money"];

export interface Located { space: SpaceId; group: NavGroup; page: NavPage }

/** Every page with where it lives, in menu order, each once: a tab of the Calendar every space shares is placed in the space
 * its own address belongs to. */
export const ALL_PAGES: Located[] = (() => {
  const out: Located[] = [];
  for (const space of SPACE_LIST) for (const group of NAV[space].groups) for (const p of group.pages) {
    if (out.some((l) => l.page.to === p.to)) continue;
    out.push({ space: p.space ?? space, group, page: p });
  }
  return out;
})();

/** Every menu entry once, with its space (the Calendar under Invest, where its own page is). */
export const ALL_GROUPS: { space: SpaceId; group: NavGroup }[] = SPACE_LIST.flatMap((space) => NAV[space].groups
  .filter((g) => !g.start || g.pages[0].space === space).map((group) => ({ space, group })));

/** Where a space's menu entry opens: its first tab, or the tab that space starts the shared Calendar on. */
export const startOf = (group: NavGroup, space: SpaceId) => group.start?.[space] ?? group.pages[0].to;

/** An entry's own address: the page of cards for everything in it. */
export const groupPath = (space: SpaceId, group: NavGroup | string) => `/${space}/g/${typeof group === "string" ? group : group.id}`;

/** The page an address belongs to (a company's page belongs to "Look up a company"), or null. */
export function locate(path: string): Located | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  return ALL_PAGES.find((l) => l.page.to === p) ?? ALL_PAGES.find((l) => l.page.also?.test(p)) ?? null;
}

/** The entry page `/trade/g/practise` names (an old group's id names the entry that took it over), or null. */
export function locateGroup(path: string): { space: SpaceId; group: NavGroup } | null {
  const m = path.split(/[?#]/)[0].match(/^\/(trade|invest|money)\/g\/([a-z-]+)\/?$/);
  if (!m) return null;
  const space = m[1] as SpaceId;
  const group = NAV[space].groups.find((g) => g.id === m[2]) ?? NAV[space].groups.find((g) => g.was?.includes(m[2]));
  return group ? { space, group } : null;
}

/** The page with this exact address, wherever it lives. */
export const pageAt = (to: string): Located | null => ALL_PAGES.find((l) => l.page.to === to) ?? null;

/** A page's name with its entry, for search and the tab's title: "Find stocks › Figures", or the page alone when the entry
 * is that one page ("Themes"). `was` adds the old name: "Find stocks › Figures (Screener)". */
export function placeName(l: Located, was = false): string {
  const own = l.group.pages.length === 1 ? l.page.label : `${l.group.label} › ${l.page.label}`;
  return was && l.page.was ? `${own} (${l.page.was})` : own;
}
