import { searchWords } from "./helpTopics";
import { ALL_PAGES, NAV } from "./nav";

/** Everything StratLab can do, with the words people might search for. Used by search and the home page grid.
 * `to` is a route; "@notebook", "@market" and "@verdict" mean the notebook you're in (or your latest one). */
export interface Feature {
  id: string; title: string; what: string; to: string; words: string; home?: boolean;
  state?: Record<string, unknown>; level?: "all" | "advanced";
  /** Which goal it serves on the home page, grouped and ordered by what the user came for. */
  goal?: Goal;
}

export type Goal = "find" | "understand" | "test" | "trade";
export const GOALS: Record<Goal, { title: string; sub: string }> = {
  find: { title: "Find stocks worth a look", sub: "Trends, which sectors lead, and which companies filed red flags." },
  understand: { title: "Understand a company", sub: "The business, its numbers and whether management delivers." },
  test: { title: "Test a trading idea", sub: "Honest results on years of real prices, after costs." },
  trade: { title: "Trade it with fake money", sub: "Live prices, real fills, no real money at risk." },
};
export const GOAL_ORDER: Record<string, Goal[]> = {
  invest: ["find", "understand", "test", "trade"], trade: ["test", "trade", "find", "understand"],
  money: ["find", "understand", "test", "trade"], both: ["test", "trade", "understand", "find"],
};

export const FEATURES: Feature[] = [
  { id: "trade_home", title: "Trade", what: "The strategy lab: your notebooks, paper trading and options in one place.", to: "/trade",
    words: "trade trading home strategy lab notebooks paper options overview space" },
  { id: "invest_home", title: "Invest", what: "Your watchlist at a glance, today's results and red flags, and any company to look up.", to: "/invest",
    words: "invest investing home research watchlist results red flags overview space" },
  { id: "money_home", title: "Money", what: "Your holdings, this year's capital gains tax estimate and everything you own.", to: "/money",
    words: "money personal finance net worth wealth home holdings tax overview space my money" },
  { id: "idea", title: "Test an idea", what: "Describe a strategy in plain words and get an honest verdict on years of real prices.", to: "/new",
    words: "new notebook backtest test idea strategy rules describe plain english build", home: true, goal: "test" },
  { id: "research", title: "Research a company", what: "Price, key numbers, results, news and an AI read that ends with ideas to test.", to: "/research",
    words: "company stock fundamentals analysis ai read valuation news research", home: true, goal: "understand" },
  { id: "group", title: "Test on a whole group", what: "Run one set of rules on NIFTY 50, F&O stocks, US mega caps, big coins or your own list.", to: "@market",
    words: "group basket portfolio universe scanner momentum nifty 50 many stocks list", home: true, goal: "test" },
  { id: "options", title: "Paper trade options", what: "Straddles, strangles, iron flies, condors or any structure, filled at the live bid and ask.", to: "/options",
    words: "options straddle strangle iron fly condor spread ce pe nifty banknifty sensex fno f&o", home: true, goal: "trade" },
  { id: "options_greeks", title: "Option Greeks and what-if", what: "IV, delta, gamma, theta and vega for every strike and your position, the payoff today, and sliders for spot, IV and days.",
    to: "/options", words: "greeks delta gamma theta vega iv implied volatility what if whatif slider payoff today t+0 before expiry roll adjust black",
    level: "advanced", goal: "trade" },
  { id: "positioning", title: "Derivatives positioning", what: "Participant-wise open interest, FII/DII cash flows, PCR, max pain, OI by strike and ATM IV.",
    to: "/trade/positioning", words: "positioning fii dii pro client participant open interest oi pcr put call ratio max pain iv implied volatility flows cash fno f&o derivatives",
    goal: "trade" },
  { id: "options_signal", title: "Options on your own signal", what: "Let a notebook's rules decide: long buys your structure, short buys its mirror.", to: "/options?enter=rules",
    words: "options signal ema rsi rules trigger buy call put directional", home: true, level: "advanced", goal: "trade" },
  { id: "library", title: "Strategy library", what: "Rules other traders published with their honest verdicts. Copy one and re-test it.", to: "/library",
    words: "library community shared strategies browse copy others public published marketplace", home: true, goal: "test" },
  { id: "publish", title: "Publish to the library", what: "Share a strategy's rules with its verdict. From a verdict: Share verdict → Publish.", to: "@verdict",
    words: "publish library share rules community" },
  { id: "phone", title: "Install on your phone", what: "Put StratLab on your home screen and get trade alerts and the daily report as notifications.", to: "/app",
    words: "install app phone mobile home screen notifications push alerts pwa android iphone" },
  { id: "import", title: "Import a strategy", what: "Pine Script, Python, MetaTrader, AmiBroker, a config file or plain words.", to: "/import",
    words: "import pine script tradingview python metatrader amibroker config json bot code upload", home: true, goal: "test" },
  { id: "paper", title: "Paper trade", what: "Run rules live on real prices with fake money, until you stop them.", to: "/paper",
    words: "paper trading live forward test sessions running fake money simulate", home: true, goal: "trade" },
  { id: "risk", title: "All running sessions together", what: "Open value, today, total P&L, worst day and deepest fall across every paper session.", to: "/paper",
    words: "risk exposure portfolio overview all sessions combined drawdown worst day total pnl" },
  { id: "walkforward", title: "Walk-forward test", what: "Re-tune on the past, trade the next unseen stretch, repeat. On any verdict.", to: "@verdict",
    words: "walk forward walkforward out of sample optimise optimize tune robust", level: "advanced" },
  { id: "similar", title: "Does it work on similar stocks?", what: "Run the same rules on about 10 similar instruments. On any verdict.", to: "@verdict",
    words: "similar stocks peers other instruments robustness generalise", level: "advanced" },
  { id: "compare", title: "Compare experiments", what: "Two runs side by side: what changed and whether it helped.", to: "@notebook",
    words: "compare experiments runs versions diff side by side" },
  { id: "fast", title: "Faster group entries and a spread limit", what: "Enter on the live price, skip stocks whose spread is too wide. When you paper trade a group.", to: "@notebook",
    words: "fast entries tick live price spread liquidity filter minimum price group", level: "advanced" },
  { id: "share", title: "Share a verdict", what: "A card from your phone or a public link. Your rules stay private.", to: "@verdict",
    words: "share link card image whatsapp twitter public verdict" },
  { id: "alerts", title: "Alerts and the daily report", what: "Telegram or email for each trade, and a report after the market closes.", to: "/settings#notifications",
    words: "alerts telegram email notifications daily report close", home: true, goal: "trade" },
  { id: "themes", title: "Themes", what: "Map a sector or trend and see the listed companies linked to it.", to: "/research/themes", words: "themes sector industry shortlist ev defence banks", goal: "understand" },
  { id: "pulse", title: "Market pulse", what: "Index levels, headlines and today's mood.", to: "/research/pulse", words: "market pulse today news mood indices" },
  { id: "rcompare", title: "Compare two companies", what: "Side by side, with an AI read.", to: "/research/compare", words: "compare companies versus vs", home: true, goal: "understand" },
  { id: "watchlist", title: "Watchlist", what: "Companies you're keeping an eye on.", to: "/research/watchlist", words: "watchlist saved favourites" },
  { id: "scan", title: "Stage 2 + Supertrend scan", what: "Which stocks are in a rising trend (Stage 2) with the Supertrend line also pointing up, with a daily watchlist alert.", to: "/research/scan",
    words: "scan screener stage 2 stage two supertrend st s2 weinstein signals alert", home: true, goal: "find" },
  { id: "rotation", title: "Sector rotation", what: "Which sectors lead, weaken, lag or improve against the market. Click one to see its stocks.", to: "/research/rotation",
    words: "sector rotation relative strength momentum quadrant leading lagging improving weakening rrg sectors", home: true, goal: "find" },
  { id: "breadth", title: "Market breadth", what: "How many stocks rose or fell, sit above their 50- and 200-day averages or made 52-week highs and lows, with McClellan and sectors.", to: "/invest/breadth",
    words: "market breadth advance decline advances declines a/d line ad ratio mcclellan oscillator summation index new highs lows 52 week dma moving average stage 2 trin arms thrust sector breadth nifty 500 midcap smallcap" },
  { id: "filings", title: "Filings and red flags", what: "Fund raises (QIP), pledges, resignations and defaults your watchlist companies filed, with an evening alert.", to: "/research/filings",
    words: "filings announcements red flags qip fund raise preferential rights issue pledge resignation auditor default sebi rating downgrade nse bse alert", home: true, goal: "find" },
  { id: "deepdive", title: "Company deep dive", what: "Open any Indian or US company, then Deep dive: 10 years of numbers, its business, capex plans and whether management delivered.", to: "/research",
    words: "deep dive business model segments capex capacity expansion growth margins cash flow free cash flow presentation concall transcript management guidance report card promises checklist deck slides powerpoint pptx", home: true, goal: "understand" },
  { id: "investor", title: "Investor home", what: "Every watchlist company, India or US, on one page: trend, sector, red flags, checklist and management's track record.", to: "/research/investor",
    words: "investor home dashboard watchlist checklist report card management track record long term", home: true, goal: "find" },
  { id: "holdings", title: "My Holdings", what: "Upload your holdings file from Zerodha, Groww, Upstox, Angel One, ICICI Direct or HDFC Securities: value, P&L, sectors and each stock's filings.", to: "/holdings",
    words: "holdings portfolio my stocks import upload broker zerodha console kite groww upstox angel one icici direct hdfc securities csv excel xlsx pnl p&l profit loss value sector allocation", home: true, goal: "find" },
  { id: "networth", title: "Net worth", what: "Everything you own minus what you owe: stocks, EPF, PPF, NPS, FDs, gold, property and loans, with your insurance policies.", to: "/money/net-worth",
    words: "net worth networth assets liabilities epf ppf nps fd rd fixed deposit recurring gold sgb sovereign gold bond property cash crypto loan emi prepay prepayment home loan insurance policy premium term health money" },
  { id: "sip_test", title: "Test a SIP", what: "What a SIP into stocks or ETFs would have done on past prices, with charges, a step-up or a dip rule, and a lump sum beside it.", to: "/money/sip-test",
    words: "sip stock sip etf sip systematic investment plan monthly weekly daily step up dip rule lump sum xirr niftybees goldbees test", goal: "test" },
  { id: "rates", title: "Rates after tax", what: "T-bill cut-offs, government bond yields, the repo rate, this quarter's small savings rates and your deposits, each after tax at your rate.", to: "/money/rates",
    words: "rates fixed income fd fixed deposit t-bill treasury bill g-sec government bond repo ppf scss ssy nsc kvp post office small savings floating rate bond after tax yield slab tds" },
  { id: "news", title: "News and newsletters", what: "A short brief after each market close, for India, the US and the companies you follow. On the page or by email.", to: "/news",
    words: "news newsletter brief digest email daily weekly market close my stocks watchlist headlines", goal: "find" },
  { id: "plans", title: "Plans", what: "What each plan includes.", to: "/plans", words: "plans pricing upgrade pro basic free price billing" },
  { id: "account", title: "Account", what: "Your profile, plan, usage, invoices and how you sign in.", to: "/account",
    words: "account profile usage invoices sign in security sign out data delete" },
  { id: "settings", title: "Settings", what: "Where alerts and emails go, what you see first, the theme and a check of every data and AI service.", to: "/settings",
    words: "settings notifications emails newsletters theme dark light experience level focus connected accounts connection check" },
  { id: "assistant", title: "Connect an AI assistant", what: "Keys that let Claude or ChatGPT use your StratLab, each one revocable.", to: "/assistant",
    words: "assistant ai claude chatgpt mcp key connect" },
  { id: "invite", title: "Invite friends", what: "Your invite link, and the free months you earn when friends join.", to: "/invite",
    words: "invite friends referral link free month share" },
];

/** Features that only name a page already in the menu (lib/nav.ts) add their words to that page instead of listing twice.
 * These stay on their own: they are a part of a page with a name people look for. */
const OWN_ROW = ["options_greeks", "risk", "deepdive"];

const EXTRA: Feature[] = [
  { id: "features", title: "All features", what: "Every page by space and group, with what it is for in a line.", to: "/features",
    words: "all features pages list everything index menu map sitemap browse what can stratlab do where is" },
  { id: "mine_home", title: "My space", what: "Your net worth, today's change, the markets, what is coming up and your watchlist, in the order you choose.", to: "/mine",
    words: "mine my space home customise customize pinned dashboard today pnl net worth coming up" },
];

/** What search looks through: every page in the menu (by its name, its one-liner and the everyday words for it, such as "MTF"
 * or "borrowed money" for Margin funding), then the features that are not a page of their own. */
const SEARCHABLE: Feature[] = (() => {
  const merged = new Map<string, string[]>();
  const alone: Feature[] = [];
  for (const f of FEATURES) {
    if (!OWN_ROW.includes(f.id) && ALL_PAGES.some((l) => l.page.to === f.to)) merged.set(f.to, [...(merged.get(f.to) ?? []), f.words]);
    else alone.push(f);
  }
  const pages: Feature[] = ALL_PAGES.map(({ space, group, page }) => ({
    id: `page:${page.to}`, title: page.label, what: page.line, to: page.to,
    words: [page.words, ...(merged.get(page.to) ?? []), NAV[space].label, group.label].join(" "),
  }));
  return [...pages, ...alone, ...EXTRA];
})();

export function match(q: string, limit = 6): Feature[] {
  const text = q.toLowerCase().trim();
  const words = searchWords(q);         // "what is walk-forward?" looks for walk and forward, not "is" inside "list"
  if (!words.length) return [];
  const scored = SEARCHABLE.map((f) => {
    const title = f.title.toLowerCase();
    const hay = `${title} ${f.words}`.toLowerCase();
    let s = words.reduce((n, w) => n + (hay.includes(w) ? (title.includes(w) ? 3 : 1) : 0), 0);
    if (words.length > 1 && (hay.includes(text) || hay.includes(words.join(" ")))) s += 4;       // the whole phrase ("borrowed money") counts for more than its words
    if (title === text) s += 6;
    return [s, f] as const;
  }).filter(([s]) => s > 0);
  return scored.sort((a, b) => b[0] - a[0]).slice(0, limit).map(([, f]) => f);
}

/** Resolve "@notebook", "@market" and "@verdict" against where you are and your latest notebook. */
export function resolve(to: string, path: string, latest: { id: string } | null): string {
  if (!to.startsWith("@")) return to;
  const m = path.match(/^\/n\/([^/]+)(?:\/e\/(\d+))?/);
  const id = m?.[1] ?? latest?.id;
  if (!id) return to === "@market" ? "/new?then=group" : "/new";
  if (to === "@market") return `/n/${id}/market#group`;
  if (to === "@verdict" && m?.[2]) return path;
  return `/n/${id}`;
}
