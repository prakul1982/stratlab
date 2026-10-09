/* What search engines and link previews are told about each public page: its title, its own description, its one
 * address (canonical) and whether it may be indexed. One table, read by the build (scripts/seoPages.mjs writes each
 * page's tags into its own HTML file, so a crawler that doesn't run scripts sees them) and by the app (lib/seo.ts keeps
 * the tags right while someone moves between pages). Plain data: no React. */

export const SITE = "https://stratlab.studio";

export const TAGLINE = "Test it, research it, track it.";
export const HOME_TITLE = "StratLab: test it, research it, track it";
export const HOME_DESCRIPTION = "Test trading ideas on years of real prices and paper trade them, options included. Research Indian and US companies from their own filings. Track your holdings, funds and tax. Facts, not tips.";

export type PageMeta = {
  /** the address the page lives at */
  path: string;
  title: string;
  description: string;
  /** false: the page is for people, not for search results (sign-in pages, a 404) */
  index: boolean;
  /** the address search engines should treat as the page's own (an alias names the page it repeats) */
  canonical?: string;
  /** when the page's words last changed, for the sitemap (YYYY-MM-DD) */
  updated?: string;
};

/** Pages anyone can open, and what each says about itself. */
export const PAGES: PageMeta[] = [
  { path: "/", title: HOME_TITLE, description: HOME_DESCRIPTION, index: true, updated: "2026-10-08" },
  { path: "/pricing", title: "Plans · StratLab",
    description: "What the Free, Basic and Pro plans include and cost. Prices are in rupees; outside India the price is shown in your currency and charged in rupees.", index: true, updated: "2026-10-08" },
  { path: "/faq", title: "Questions · StratLab",
    description: "Answers about StratLab: whether it gives tips or places real trades, how the four checks work, options, invite rewards, who can see your money data, and the app.", index: true, updated: "2026-10-08" },
  { path: "/library", title: "Strategy library · StratLab",
    description: "StratLab's own trading strategies, each with the rules that were tested, the results after costs and the four checks, shown as they came out on past prices.", index: true, updated: "2026-10-08" },
  { path: "/terms", title: "Terms · StratLab",
    description: "The terms for using StratLab: what it is, accounts, plans and payment, fair use, what you publish, market data and AI, and liability.", index: true, updated: "2026-09-26" },
  { path: "/privacy", title: "Privacy · StratLab",
    description: "What StratLab collects and why, who processes it, what your browser stores before and after sign-in, and how to see, correct or delete your data.", index: true, updated: "2026-10-08" },
  { path: "/refunds", title: "Refunds · StratLab",
    description: "How to cancel a StratLab plan, when a payment is refunded and how to ask. You can cancel any time from Account.", index: true, updated: "2026-09-26" },
  { path: "/contact", title: "Contact · StratLab",
    description: "How to reach StratLab for help, billing and refunds, or a privacy request, with the email address for each.", index: true, updated: "2026-09-26" },
  // addresses that open the landing page at a place, or ask for sign-in: not pages of their own
  { path: "/about", title: "About · StratLab", description: "What StratLab is: three spaces, Trade, Invest and Money, for Indian and US stocks.", index: false, canonical: "/" },
  { path: "/help", title: "Help · StratLab", description: "Help with StratLab: the questions people ask first, and how to reach a person.", index: false, canonical: "/faq" },
  { path: "/login", title: "Sign in · StratLab", description: "Sign in to StratLab with your Google account.", index: false },
  { path: "/signup", title: "Sign up · StratLab", description: "Create a free StratLab account with Google. No card needed.", index: false },
];

/** StratLab's own library strategies, [id, name], as backend/app/library_seed.py publishes them (backend test
 * test_review_r6v checks the two lists agree). The build writes each one's page with its own title, description and
 * address, so a crawler that doesn't run scripts never takes it for the home page (R6V-012). */
export const LIBRARY_SEEDS: [string, string][] = [
  ["seed-st-s2-in", "ST S2: Stage 2 + Supertrend · NIFTY 50 stocks"],
  ["seed-st-s2-us", "ST S2: Stage 2 + Supertrend · 20 US large caps"],
  ["seed-ema-20-50-in", "20/50 EMA cross · NIFTY 50 stocks"],
  ["seed-ema-20-50-us", "20/50 EMA cross · 20 US large caps"],
  ["seed-rsi2-revert-in", "RSI(2) mean reversion · NIFTY 50 stocks"],
  ["seed-rsi2-revert-us", "RSI(2) mean reversion · 20 US large caps"],
  ["seed-breakout-52w-in", "52-week breakout with ATR stop · NIFTY 50 stocks"],
  ["seed-breakout-52w-us", "52-week breakout with ATR stop · 20 US large caps"],
  ["seed-boll-squeeze-in", "Bollinger squeeze breakout · NIFTY 50 stocks"],
  ["seed-boll-squeeze-us", "Bollinger squeeze breakout · 20 US large caps"],
  ["seed-orb-15m-fo", "Opening-range breakout (intraday) · 25 most liquid F&O stocks"],
  ["seed-golden-cross-in", "Golden cross · NIFTY 50 stocks"],
  ["seed-golden-cross-us", "Golden cross · 20 US large caps"],
  ["seed-donchian-20-10-in", "Donchian 20/10 (turtle-style) · NIFTY 50 stocks"],
  ["seed-donchian-20-10-us", "Donchian 20/10 (turtle-style) · 20 US large caps"],
  ["seed-macd-cross-in", "MACD signal cross · NIFTY 50 stocks"],
  ["seed-macd-cross-us", "MACD signal cross · 20 US large caps"],
  ["seed-supertrend-in", "Supertrend flip · NIFTY 50 stocks"],
  ["seed-supertrend-us", "Supertrend flip · 20 US large caps"],
];

/** A library strategy's page: its own title, description and address. */
export const libraryMeta = (id: string, name: string): PageMeta => ({
  path: `/library/${id}`, title: `${name}: rules and verdict · StratLab`, index: true,
  description: `${name}: the rules StratLab tested, the return after costs beside buy and hold, and the four checks, as they came out on past prices. Facts about the past, not advice.`,
});

/** What a page that is not in the table says: a sign-in page for an address inside the app, or a missing page. */
export const GATE_DESCRIPTION = "Sign in to StratLab to open this page.";
export const NOT_FOUND_DESCRIPTION = "There is no page at this address on StratLab.";
export const VERDICT_DESCRIPTION = "A strategy's verdict on past prices, shared by link: the result after costs and the four checks it was put through.";

const tidy = (path: string) => (path.split(/[?#]/)[0].replace(/\/+$/, "") || "/");

/** The table's entry for an address, if it has one. */
export const pageMeta = (path: string): PageMeta | undefined => PAGES.find((p) => p.path === tidy(path));

/** The full web address for a path on the site. */
export const absolute = (path: string) => SITE + (path === "/" ? "/" : path);

/** The pages a sitemap lists: indexable, and the page itself rather than an alias. */
export const sitemapPages = () => PAGES.filter((p) => p.index);
