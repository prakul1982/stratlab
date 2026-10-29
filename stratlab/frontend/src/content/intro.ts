/* The landing page's "What StratLab is" intro, as data: the page draws it (pages/Login.tsx) and unit/land2.test.mjs checks that the
 * words search engines read in the home page's own HTML (content/seo.ts, written into it at build time) say the same things (LAND-2).
 * Plain data: no React. Facts about the product only: nothing here says what to buy or sell, rates a company or names a data source. */

export const INTRO_TITLE = "What StratLab is";

/** The one sentence a first-time visitor needs. */
export const INTRO_LINE = "StratLab is a lab for testing trading ideas and understanding your own money, across ten markets, with paper trading only (never real orders) and facts, not tips.";

export type IntroSpace = { id: "trade" | "invest" | "money"; name: string; sub: string; line: string; things: [string, string][] };

/** The three spaces: what you do there in one line, and three concrete things it does (each one a real feature). */
export const INTRO_SPACES: IntroSpace[] = [
  { id: "trade", name: "Trade", sub: "The strategy lab", line: "Test a trading idea on years of real prices, then paper trade it.",
    things: [["Notebooks", "Ideas in plain words, four checks for luck."],
      ["Strategy library", "StratLab's own strategies, each checked."],
      ["Paper trading, options and the F&O desk", "Live prices, fake money."]] },
  { id: "invest", name: "Invest", sub: "Research", line: "Read any Indian or US company from its own numbers and filings.",
    things: [["Company pages", "Prices, key numbers, results, owners."],
      ["Screens and IPOs", "Filter by size, growth and debt; IPO dates."],
      ["Red flags", "Pledges and defaults, linked to the filing."]] },
  { id: "money", name: "Money", sub: "What you own", line: "See what you own, and what it means at tax time, from your own files.",
    things: [["Holdings and mutual funds", "Upload your files: value, gains and XIRR."],
      ["Tax report, US tax and ITR export", "Gains worked out, laid out for the ITR."],
      ["Net worth and the Money calendar", "What you own, plus tax dates and EMIs."]] },
];

export const HOW_TITLE = "How it works";
export const HOW_STEPS: [string, string][] = [
  ["Describe an idea", "Write it in plain words, like \"Buy Reliance when it's above its 200-day average.\" StratLab turns it into rules you can tap to change."],
  ["Test it on real prices", "See what it would have done over years of history, and whether the result was luck."],
  ["Trade it on paper", "Run it live with fake money, with a report after each close."],
];
/** Money has its own two steps, under the three above. */
export const HOW_MONEY = "Money works the same way: upload your files, then see your value, gains and tax worked out.";
// LIVE2-011: the old "What makes it different" trio (real costs, four checks for luck, your data stays yours) is gone: the Trade section below says the first two in
// full, the Money section the third. Each phrase is said once on the page.
