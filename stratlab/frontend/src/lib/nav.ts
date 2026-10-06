import { NAV_GROUPS, type NavEntry } from "./navGroups";

/** The whole map of StratLab: which page lives in which group of which space. The sidebar, the group landing pages, the
 * breadcrumb, the "All features" page and ⌘K are all drawn from this one list, so a page added here shows up in all of
 * them. Keep it in the order people use things. */
export type SpaceId = "trade" | "invest" | "money";

export interface NavPage {
  /** The page's own address; the sidebar links here. */
  to: string;
  label: string;
  /** One line on what it is for (a card on the group page, the line on "All features"). */
  line: string;
  /** A fuller line for its card on the group page. */
  blurb: string;
  /** Everyday words people might search for ("MTF", "borrowed money"): ⌘K finds the page by these too. */
  words: string;
  /** Name of a sidebar icon (see ICONS in Shell). */
  icon: string;
  /** Other addresses that are part of this page (a company's page is part of "Look up a company"). */
  also?: RegExp;
  /** Shipped on the date below: marked "New" on the "All features" page. */
  isNew?: boolean;
  /** Plan feature flag (plans.ts) when the page is on a paid plan. */
  flag?: string;
}
export interface NavGroup { id: string; label: string; blurb: string; pages: NavPage[] }

const fromData = (to: string): NavEntry | undefined =>
  [...NAV_GROUPS.Trade, ...NAV_GROUPS.Invest, ...NAV_GROUPS.Money].find((e) => e.to === to);

/** A page whose texts are already written for its card on a space's home (NAV_GROUPS) reuses them. */
function page(to: string, label: string, icon: string, words: string, o: { line?: string; blurb?: string; also?: RegExp; isNew?: boolean; flag?: string } = {}): NavPage {
  const d = fromData(to);
  const line = o.line ?? d?.title ?? o.blurb ?? d?.blurb ?? label;
  return { to, label, icon, words, line, blurb: o.blurb ?? d?.blurb ?? line, also: o.also, isNew: o.isNew, flag: o.flag };
}

export const NEW_SINCE = "5 Oct 2026";

export const NAV: Record<SpaceId, { label: string; home: string; groups: NavGroup[] }> = {
  trade: {
    label: "Trade", home: "/trade", groups: [
      { id: "build-and-test", label: "Build and test", blurb: "Turn an idea into rules, test it on years of real prices after costs, and keep every run.", pages: [
        page("/notebooks", "Notebooks", "book", "notebook backtest test idea strategy rules describe plain english build new experiment verdict",
          { line: "Describe a trading idea in plain words and test it on years of real prices.",
            blurb: "Each notebook holds one idea: its rules, every test run on real prices after costs, and the verdict with its four checks for luck.", also: /^\/(new|n\/.*)$/ }),
        page("/library", "Strategy library", "library", "library community shared strategies browse copy others public published marketplace publish share rules",
          { line: "Rules other traders published, each with the verdict it earned. Copy one and re-test it." }),
        page("/import", "Import a strategy", "upload", "import pine script tradingview python metatrader amibroker config json bot code upload convert",
          { line: "Bring a strategy from Pine Script, Python, MetaTrader or AmiBroker, or a config file.", blurb: "Pine Script, Python, MetaTrader, AmiBroker, a config file or plain words: StratLab turns it into rules you can read, edit and test." }),
        page("/trade/signals", "Forward test", "pulse", "forward test signal signals webhook tradingview chartink alert alerts paper live out of sample go forward",
          { line: "Run your strategy forward on paper: each TradingView or Chartink alert is filled at StratLab's own price.", also: /^\/trade\/signals\/.*$/, flag: "signal_webhooks", isNew: true }),
      ] },
      { id: "practise", label: "Practise", blurb: "Trade with fake money on live prices or on past candles. Nothing here sends a real order.", pages: [
        page("/paper", "Paper trading", "pulse", "paper trading live forward test sessions running fake money simulate practice demo risk exposure all sessions",
          { line: "Run a notebook's rules live on real prices with fake money, until you stop them.", blurb: "Run rules live on real prices with fake money. Every session keeps its orders, its open position and its running result.", also: /^\/paper\/.*$/ }),
        page("/options", "Options builder", "layers", "options straddle strangle iron fly condor spread ce pe nifty banknifty sensex fno f&o greeks delta gamma theta vega iv payoff what if",
          { line: "Build straddles, strangles, condors or any legs and paper trade them at the live bid and ask.", blurb: "Straddles, strangles, iron flies, condors or any structure, filled at the live bid and ask, with Greeks and a what-if payoff.", also: /^\/options\/s\/.*$/ }),
        page("/trade/replay", "Chart replay", "lens", "chart replay practise past candles bar replay manual trading practice journal", { isNew: true, flag: "chart_replay" }),
      ] },
      { id: "fo-desk", label: "F&O desk", blurb: "What the futures and options market is doing: who holds what, what is changing, what is coming.", pages: [
        page("/trade/positioning", "Positioning", "layers", "positioning fii dii pro client participant open interest oi pcr put call ratio max pain iv implied volatility flows cash fno f&o derivatives vix stock futures buildup rollover basis mwpl",
          { also: /^\/trade\/positioning\/stocks$/ }),
        page("/trade/fo-changes", "F&O changes", "calendar", "f&o changes lot size lot revisions entering leaving fno list ban expiry day contract exchange circular"),
        page("/trade/closing-auction", "Closing auction", "pulse", "closing auction 15:15 15:35 reference price indicative price settlement expiry day", { isNew: true }),
        page("/trade/events", "Market events", "calendar", "market events calendar rbi policy fed data releases budget index changes expiries holidays results dates", { isNew: true }),
      ] },
      { id: "my-trades", label: "My trades", blurb: "Your real trades, looked at honestly.", pages: [
        page("/trade/journal", "Trade journal", "book", "trade journal round trips tradebook import pnl charges notes real trades review mistakes win rate"),
      ] },
    ],
  },
  invest: {
    label: "Invest", home: "/invest", groups: [
      { id: "companies", label: "Companies", blurb: "Look up any Indian or US company, or put two side by side.", pages: [
        page("/research", "Look up a company", "lens", "company stock fundamentals analysis ai read valuation news research search ticker deep dive business model capex growth margins cash flow management report card concall presentation",
          { line: "Any Indian or US company: price, key numbers, results, news, and a deep dive.", blurb: "Price, valuation, growth, news and an AI read for any Indian or US company, and a deep dive into 10 years of its numbers and its business.", also: /^\/research\/(IN|US)\/.*$/ }),
        page("/research/compare", "Compare", "layers", "compare companies versus vs side by side two stocks", { line: "Two companies side by side, with an AI read of the differences." }),
      ] },
      { id: "find-stocks", label: "Find stocks", blurb: "Filter and scan companies by plain facts, trends and filings.", pages: [
        page("/research/screens", "Screener", "search", "screener screen filter companies growth debt returns roe pe fundamentals ratios", { line: "Filter companies by plain facts: growth, debt, returns." }),
        page("/research/scan", "Trend scan", "pulse", "trend scan stage 2 stage two supertrend st s2 weinstein signals nifty 50 daily alert", { line: "Which stocks are in a rising trend (Stage 2) with the Supertrend line also pointing up." }),
        page("/research/filings", "Red flags", "bell", "red flags filings announcements qip fund raise preferential rights issue pledge resignation auditor default sebi rating downgrade", { line: "Fund raises, pledges, resignations and defaults your watchlist companies filed." }),
        page("/research/themes", "Themes", "compass", "themes sector industry shortlist ev defence banks trend map listed companies", { line: "Map a sector or trend and see the listed companies linked to it." }),
      ] },
      { id: "market-view", label: "Market view", blurb: "The market as a whole: its mood, breadth, sectors, and the cost of borrowing to invest.", pages: [
        page("/research/pulse", "Market pulse", "pulse", "market pulse today news mood indices nifty sensex headlines index levels", { line: "Index levels, headlines and today's mood." }),
        page("/invest/breadth", "Market breadth", "pulse", "market breadth advance decline advances declines a/d line ad ratio mcclellan oscillator summation index new highs lows 52 week dma moving average trin arms thrust sector breadth nifty 500 midcap smallcap"),
        page("/research/rotation", "Sector rotation", "compass", "sector rotation relative strength momentum quadrant leading lagging improving weakening rrg sectors", { line: "Which sectors lead, weaken, lag or improve against the market." }),
        page("/invest/etf-gaps", "ETF vs NAV", "lens", "etf nav premium discount gap price iopv nifty bees goldbees fund unit value", { isNew: true }),
        page("/invest/margin-funding", "Margin funding", "wallet", "margin funding mtf margin trading facility borrowed money broker funding leverage loan to buy shares interest pledge exposure", { isNew: true, flag: "mtf" }),
        page("/invest/stock-lending", "Stock lending fees", "receipt", "stock lending fees slb securities lending borrowing borrowed shares lend my shares earn on holdings", { isNew: true }),
      ] },
      { id: "company-news", label: "Company news", blurb: "What companies report and announce: news, results, dividends, updates and who holds them.", pages: [
        page("/news", "News", "news", "news newsletter brief digest email daily weekly market close my stocks watchlist headlines subscribe", { line: "A short brief after each market close, for India, the US and the companies you follow." }),
        page("/research/results", "Results", "calendar", "results quarterly earnings calendar results dates q1 q2 q3 q4 profit revenue announcement", { line: "Results days for your stocks, or every company, week by week." }),
        page("/research/corporate-actions", "Corporate actions", "calendar", "corporate actions dividend ex date record date bonus issue stock split rights buyback demerger", { line: "Dividends, bonus issues and splits by ex-date, for your stocks or every company." }),
        page("/invest/business-updates", "Business updates", "calendar", "business updates monthly sales automakers vehicle sales lenders quarterly figures advances deposits", { isNew: true, flag: "biz_updates" }),
        page("/invest/holders", "Named holders", "layers", "named holders shareholders promoter fund fii dii mutual fund shareholding pattern above 1% who owns", { isNew: true, flag: "holders" }),
      ] },
      { id: "watch", label: "Watch", blurb: "The companies you follow, and a message when something happens to them.", pages: [
        page("/research/watchlist", "Watchlist", "pin", "watchlist saved favourites companies i follow at a glance investor home dashboard checklist report card track record",
          { line: "The companies you follow, as a list or each one at a glance.", also: /^\/research\/investor$/ }),
        page("/alerts", "Alerts", "bell", "alerts stock alerts price alert notify notification telegram email push trigger", { line: "Messages when a stock or the market does something you asked about." }),
      ] },
    ],
  },
  money: {
    label: "Money", home: "/money", groups: [
      { id: "what-you-own", label: "What you own", blurb: "Everything you own and owe, from your own files, in one place.", pages: [
        page("/money/net-worth", "Net worth", "wallet", "net worth networth assets liabilities epf ppf nps fd rd fixed deposit recurring gold sgb sovereign gold bond property cash crypto loan emi prepay prepayment home loan insurance policy premium money wealth"),
        page("/holdings", "Holdings", "book", "holdings portfolio my stocks import upload broker zerodha groww upstox angel one icici direct hdfc securities csv excel xlsx pnl p&l profit loss value sector allocation connect account demat",
          { line: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and filings.", blurb: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and each stock's filings." }),
        page("/money/mutual-funds", "Mutual funds", "layers", "mutual funds cas cams kfintech statement xirr sip fund returns category allocation capital gains"),
      ] },
      { id: "tax", label: "Tax", blurb: "What you owe on your gains and when, laid out for you and your CA.", pages: [
        page("/tax-report", "Tax report", "receipt", "tax report capital gains stcg ltcg tradebook fifo financial year grandfathering harvest p&l loss set off"),
        page("/money/tax-tools", "Tax tools", "receipt", "tax tools dividends tds advance tax due dates ltcg exemption 1.25 lakh section 87a"),
        page("/money/us-tax", "US stocks tax", "compass", "us stocks tax foreign tax credit schedule fa form 67 tt buying rate sbi 24 month rule indian investors us shares"),
        page("/money/itr", "ITR-ready export", "receipt", "itr export schedule 112a cg ca pdf pack income tax return filing f&o turnover audit", { isNew: true }),
      ] },
      { id: "plan", label: "Plan", blurb: "Look ahead: what a SIP would have done, what your savings earn, and the dates that matter.", pages: [
        page("/money/sip-test", "Test a SIP", "pulse", "sip stock sip etf sip systematic investment plan monthly weekly daily step up dip rule lump sum xirr niftybees goldbees test", { isNew: true, flag: "sip_luck" }),
        page("/money/rates", "Rates", "receipt", "rates fixed income fd fixed deposit t-bill treasury bill g-sec government bond repo ppf scss ssy nsc kvp post office small savings after tax yield slab tds interest", { isNew: true, flag: "rates_slab" }),
        page("/money/calendar", "Money calendar", "calendar", "money calendar tax due dates advance tax itr results dividends maturities premiums emi expiries own dates feed reminders", { isNew: true }),
      ] },
    ],
  },
};

export const SPACE_LIST: SpaceId[] = ["trade", "invest", "money"];

export interface Located { space: SpaceId; group: NavGroup; page: NavPage }

/** Every page with where it lives, in menu order. */
export const ALL_PAGES: Located[] = SPACE_LIST.flatMap((space) => NAV[space].groups.flatMap((group) => group.pages.map((page) => ({ space, group, page }))));

/** A group's own address: the page of cards for everything in it. */
export const groupPath = (space: SpaceId, group: NavGroup | string) => `/${space}/g/${typeof group === "string" ? group : group.id}`;

/** The page an address belongs to (a company's page belongs to "Look up a company"), or null. */
export function locate(path: string): Located | null {
  const p = path.split(/[?#]/)[0].replace(/(.)\/$/, "$1");
  return ALL_PAGES.find((l) => l.page.to === p) ?? ALL_PAGES.find((l) => l.page.also?.test(p)) ?? null;
}

/** The group page `/trade/g/practise` names, or null. */
export function locateGroup(path: string): { space: SpaceId; group: NavGroup } | null {
  const m = path.split(/[?#]/)[0].match(/^\/(trade|invest|money)\/g\/([a-z-]+)\/?$/);
  if (!m) return null;
  const space = m[1] as SpaceId;
  const group = NAV[space].groups.find((g) => g.id === m[2]);
  return group ? { space, group } : null;
}

/** The page with this exact address, wherever it lives. */
export const pageAt = (to: string): Located | null => ALL_PAGES.find((l) => l.page.to === to) ?? null;
