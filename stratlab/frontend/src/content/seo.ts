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
  /** the address search engines should treat as the page's own, for an indexed page that repeats another. A page with
   * `index: false` names none (R10V-005: /about said "do not index" and "the canonical page is /" at once). */
  canonical?: string;
  /** when the page's words last changed, for the sitemap (YYYY-MM-DD) */
  updated?: string;
  /** the page's own heading and opening words, written into its HTML at build time, so a crawler that doesn't run scripts
   * reads this page's words and not the home page's (R7V-008). Without a summary, the description is the opening words. */
  heading: string;
  summary?: string[];
};

/** Pages anyone can open, and what each says about itself. */
export const PAGES: PageMeta[] = [
  // the home page's heading is the one the landing page draws (R8V-008: the raw page said "StratLab: test it, research it,
  // track it" over a drawn "Test it, research it, track it.")
  { path: "/", title: HOME_TITLE, description: HOME_DESCRIPTION, index: true, updated: "2026-10-08", heading: TAGLINE },
  { path: "/pricing", title: "Plans · StratLab",
    description: "What the Free, Basic and Pro plans include and cost. Prices are in rupees; outside India the price is shown in your currency and charged in rupees.", index: true, updated: "2026-10-08",
    heading: "Plans and prices",
    summary: ["StratLab has three plans: Free, Basic and Pro. Free costs nothing and needs no card. Basic and Pro are subscriptions billed monthly or yearly, with higher limits on experiments, AI builds and paper sessions.",
      "Prices are in Indian rupees. Outside India the page shows the price in your own currency and the payment is charged in rupees. You can cancel any time from Account."] },
  { path: "/faq", title: "Questions · StratLab",
    description: "Answers about StratLab: whether it gives tips or places real trades, how the four checks work, options, invite rewards, who can see your money data, and the app.", index: true, updated: "2026-10-08",
    heading: "Questions" },
  { path: "/library", title: "Strategy library · StratLab",
    description: "StratLab's own trading strategies, each with the rules that were tested, the results after costs and the four checks, shown as they came out on past prices.", index: true, updated: "2026-10-08",
    heading: "StratLab's own strategies",
    summary: ["Well-known rule sets that StratLab ran through its own backtest and four checks, each shown with the verdict it earned, the ones that failed as plainly as the ones that held up.",
      "Each strategy's page has the rules that were tested, the return after costs beside buy and hold, and the result of each check. A verdict describes the past, not what comes next, and nothing here is investment advice."] },
  { path: "/terms", title: "Terms · StratLab",
    description: "The terms for using StratLab: what it is, accounts, plans and payment, fair use, what you publish, market data and AI, and liability.", index: true, updated: "2026-09-26",
    heading: "Terms of service",
    summary: ["These terms cover your use of StratLab, the website and app at stratlab.studio. StratLab is a research and education tool: you test trading ideas on past market data and paper trade them with simulated money. No real orders are ever placed, and nothing on StratLab is investment advice.",
      "The terms cover your account, plans and payment, fair use, what you publish, market data and AI, liability, ending and changes."] },
  { path: "/privacy", title: "Privacy · StratLab",
    description: "What StratLab collects and why, who processes it, what your browser stores before and after sign-in, and how to see, correct or delete your data.", index: true, updated: "2026-10-08",
    heading: "Privacy policy" },
  { path: "/refunds", title: "Refunds · StratLab",
    description: "How to cancel a StratLab plan, when a payment is refunded and how to ask. You can cancel any time from Account.", index: true, updated: "2026-09-26",
    heading: "Cancellation and refunds" },
  { path: "/contact", title: "Contact · StratLab",
    description: "How to reach StratLab for help, billing and refunds, or a privacy request, with the email address for each.", index: true, updated: "2026-09-26",
    heading: "Contact us",
    summary: ["How to reach StratLab for help, billing and refunds, or a privacy request, with the email address for each.",
      "Help: support@stratlab.studio. Billing and refunds: billing@stratlab.studio. Privacy requests: privacy@stratlab.studio."] },
  // addresses that open the landing page at a place, or ask for sign-in: not pages of their own, so not indexed (R10V-005
  // checked /about: the app sends it to /features signed in, scrolls the landing page to its About place signed out, and
  // vercel.json and unit/seo.test.mjs both list it with the pages kept out of search results; the landing page and the
  // features page are what search engines list). Not indexed, so no canonical address either.
  { path: "/about", title: "About · StratLab", description: "What StratLab is: three spaces, Trade, Invest and Money, for Indian and US stocks.", index: false,
    heading: "About StratLab",
    summary: ["StratLab has three spaces for Indian and US stocks. Trade: test trading ideas on years of real prices after costs, put them through four checks and paper trade them. Invest: research companies from their own filings. Money: track your holdings, funds and tax.",
      "Facts, not tips: StratLab never says what to buy or sell, and no real orders are placed."] },
  { path: "/help", title: "Help · StratLab", description: "Help with StratLab: the questions people ask first, and how to reach a person.", index: false, heading: "Help" },
  { path: "/login", title: "Sign in · StratLab", description: "Sign in to StratLab with your Google account.", index: false, heading: "Sign in to StratLab" },
  { path: "/signup", title: "Sign up · StratLab", description: "Create a free StratLab account with Google. No card needed.", index: false, heading: "Sign up for StratLab" },
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

/** Each library strategy's rules in words, by its slug (seed-<slug>-<group>), as backend/app/library_seed.py states them
 * (backend test test_review_r7v checks they agree): the opening words of the strategy's page before any script runs. */
export const LIBRARY_RULES: Record<string, string> = {
  "st-s2": "Enters when a stock is in Stage 2 (price above a rising 150-day average) and its price is above the Supertrend (10, 3); leaves when the price crosses back below the Supertrend.",
  "ema-20-50": "Enters when the 20-day exponential average crosses above the 50-day one; leaves when it crosses back below.",
  "rsi2-revert": "Enters after a sharp short-term drop (2-day RSI under 10) while the price is above its 200-day average; leaves when the 2-day RSI is back above 70.",
  "breakout-52w": "Enters when the price closes above the highest high of the previous 252 trading days (about 52 weeks); the stop is 3 times the 14-day ATR below the entry; leaves when the price closes below its 50-day average.",
  "boll-squeeze": "A quiet spell followed by a breakout: enters when the price closes above the upper Bollinger band (20, 2) after the previous day's ATR was under 2% of the price; leaves when the price closes below the middle band. The quiet spell is measured by ATR, a stand-in for a narrow band.",
  "orb-15m": "On 15-minute candles, from 09:45 to 11:30, enters when a candle closes above the day's high so far (after the first half hour); one trade a day, a 0.6% stop, a 1.2% target, and everything is closed at 15:15.",
  "golden-cross": "Enters when the 50-day average crosses above the 200-day average; leaves when it crosses back below (the death cross).",
  "donchian-20-10": "Enters when the price closes above the highest high of the previous 20 days; leaves when it closes below the lowest low of the previous 10 days; the stop is 2 times the 14-day ATR below the entry.",
  "macd-cross": "Enters when the MACD line (12, 26) crosses above its 9-day signal line while the price is above its 200-day average; leaves when the MACD line crosses back below the signal line.",
  "supertrend": "Enters when the price crosses above the Supertrend (10, 3); leaves when it crosses back below.",
};

/** A library entry's strategy slug: "seed-golden-cross-in" → "golden-cross". */
export const librarySlug = (id: string) => id.replace(/^seed-/, "").replace(/-(in|us|fo)$/, "");

/** Where it was tested, unless the strategy's own name already says so ("Supertrend flip · 20 US large caps"): by the
 * words shown, or by the group's own name (`group`, when `where` adds a count to it). */
export const whereShown = (name: string, where: string | null | undefined, group?: string | null) => {
  const n = name.toLowerCase();
  return where && !n.includes(where.toLowerCase()) && !(group && n.includes(group.toLowerCase())) ? where : null;
};

/** The lead of a verdict's headline, for a tab title: "117.1 points behind buy and hold after costs" from "117.1 points
 * behind buy and hold after costs; passed all 3 checks run." Without a headline, the verdict's label. */
const lead = (factHeadline?: string | null, label?: string | null) =>
  ((factHeadline ?? "").split(";")[0].trim() || (label ?? "").trim()).replace(/\.\s*$/, "");

/** The longest title and description a search result shows whole: about 60 characters of title, 160 of description
 * (R10V-005: the verdict pages' titles ran to 117 characters and their descriptions to 293, which cut off the strategy's
 * name and StratLab). */
export const TITLE_MAX = 64;
export const DESCRIPTION_MAX = 160;

/** A strategy's short name for a title: "Stage 2 + Supertrend · NIFTY 50 stocks" is "Stage 2 + Supertrend" (the page and
 * the description say where it was tested). */
export const shortName = (name: string) => plainTerms(name).split(" · ")[0].trim();

/** `text` cut at a word to at most `max` characters, with "…" when it was cut. */
const cut = (text: string, max: number) => {
  if (text.length <= max) return text;
  const head = text.slice(0, Math.max(0, max - 1));
  return head.replace(/\s+\S*$/, "").replace(/[\s,;:·(+-]+$/, "") + "…";
};

/** A library strategy's tab title, the result first, as the page's headline leads with it (R7V-006: the title said
 * "Passed all 3 checks run" over a page that leads with "117.1 points behind buy and hold"), then a short strategy name and
 * StratLab, in at most TITLE_MAX characters: "117.1 points behind buy and hold: Supertrend flip · StratLab". Too long, the
 * lead says "pts", then the name loses its bracket, then its tail (R10V-005). */
export const libraryTitle = (name: string, factHeadline?: string | null, label?: string | null) => {
  const l = lead(factHeadline, label).replace(/\s+after costs$/i, "");
  const short = shortName(name);
  const make = (a: string, n: string) => (a ? `${a}: ${n} · StratLab` : `${n} · StratLab`);
  const abbreviated = l.replace(/\bpoints\b/, "pts");
  const bare = short.replace(/\s*\([^)]*\)/g, "").trim() || short;
  const clause = abbreviated.split(/;|,(?!\d)/)[0].trim();           // a long label ("Passed all 3 checks run, and returned…") to its first clause
  for (const [a, n] of [[l, short], [abbreviated, short], [abbreviated, bare], [clause, short], [clause, bare]]) {
    const t = make(a, n);
    if (t.length <= TITLE_MAX) return t;
  }
  return make(clause, cut(bare, TITLE_MAX - make(clause, "").length));
};

/** The sentences, in order, that fit in `max` characters: the first is always kept (cut if it alone is too long), each
 * later required one only whole, then each optional one that still fits, then the first closer that fits. */
const sentences = (required: string[], optional: string[], closers: string[], max: number) => {
  let out = "";
  const add = (t: string) => { const next = out ? `${out} ${t}` : t; if (next.length <= max) { out = next; return true; } return false; };
  required.forEach((t, i) => { if (!add(t) && i === 0) out = cut(t, max); });
  optional.forEach(add);
  closers.some(add);
  return out;
};

/** A library strategy's description for search results and link previews, in at most DESCRIPTION_MAX characters: the
 * headline first, then the strategy, with where it was tested only when its name doesn't already say it (R7V-006: "… 20 US
 * large caps on 20 US large caps"), then the entry's own reason and a closing line when they fit (R10V-005). */
export const libraryDescription = (e: { name: string; where?: string | null; group?: string | null; factHeadline?: string | null;
  headline?: string | null; reason?: string | null }) => {
  const on = whereShown(e.name, e.where, e.group);
  const one = (t?: string | null) => (t ?? "").replace(/\s+/g, " ").trim();
  const end = (t: string) => (t && !/[.!?]$/.test(t) ? `${t}.` : t);
  return sentences(
    [end(one(e.factHeadline ?? e.headline)), `${e.name}${on ? ` on ${on}` : ""}.`].filter(Boolean),
    [end(one(e.reason))].filter(Boolean),
    ["The rules, results after costs and the four checks, on past prices.", "The rules, results after costs and four checks.", "Rules and results after costs."],
    DESCRIPTION_MAX,
  ).replace(/\.\s*\./g, ".");
};

/** The scan's internal short name, spelled out: "ST S2: Stage 2 + Supertrend · NIFTY 50 stocks" becomes
 * "Stage 2 + Supertrend · NIFTY 50 stocks", and "Fresh ST S2" "Fresh Stage 2 + Supertrend" (lib/plainTerms.ts gives it to the app). */
export function plainTerms(text: string | null | undefined): string {
  return (text ?? "").replace(/\bST S2:\s*Stage 2 \+ Supertrend/g, "Stage 2 + Supertrend").replace(/\bST S2\b/g, "Stage 2 + Supertrend");
}

/** What a test group holds, said accurately: a group named "NIFTY 50 stocks" that holds 5 of them is "5 of the NIFTY 50
 * stocks", not "NIFTY 50 stocks (5)". A name with no number in it gets the count after it ("My banks · 3 in the test"). */
export function groupLabel(name: string, members?: number | null): string {
  if (members == null || !Number.isFinite(members) || members < 1) return name;
  const named = name.match(/\b(\d+)\b/);
  if (named) return Number(named[1]) === members ? name : `${members} of the ${name}`;
  return `${name} · ${members} in the test`;
}

/** What the build reads of a library entry from the server's public library (GET /public/library). */
export type LibraryEntryWords = {
  name?: string; reason?: string | null; market?: string; instrument?: { symbol?: string } | null;
  group?: { name: string; members?: unknown[] | null } | null;
  verdict?: { fact_headline?: string | null; headline?: string | null; label?: string | null; fact_summary?: string | null; summary?: string | null } | null;
};

/** Where an entry was tested, as its page says it: the group with its count, else the instrument or the market. */
const testedOn = (e: LibraryEntryWords) =>
  e.group ? groupLabel(e.group.name, Array.isArray(e.group.members) ? e.group.members.length : null) : e.instrument?.symbol ?? e.market ?? null;

/** A library strategy's page: its own title, description and address, and its heading and rules as the opening words.
 * With its entry from the server (`e`, read at build time), the title, description and heading are the ones the page
 * shows once drawn, the result first (R8V-008: the raw page said "…: rules and verdict" while the drawn one led with
 * "117.1 points behind buy and hold after costs"). */
export const libraryMeta = (id: string, name: string, e?: LibraryEntryWords | null): PageMeta => {
  const rules = LIBRARY_RULES[librarySlug(id)] ? [`The rules: ${LIBRARY_RULES[librarySlug(id)]}`] : [];
  const about = "StratLab ran these rules through its own backtest on every stock in the group, after costs, and through four checks: unseen years, nearby settings, a bad-luck drawdown and enough trades. The page shows the return beside buy and hold and the result of each check. A verdict describes the past, not what comes next, and nothing here is investment advice.";
  const v = e?.verdict;
  const head = v ? (v.fact_headline ?? v.headline ?? "").trim() : "";
  if (e && v && head) {
    const shown = plainTerms(e.name ?? name);
    return {
      path: `/library/${id}`, index: true,
      title: libraryTitle(shown, v.fact_headline, v.label ?? v.headline),
      description: libraryDescription({ name: shown, where: testedOn(e), group: e.group?.name, factHeadline: v.fact_headline, headline: v.headline, reason: e.reason }),
      heading: head,
      summary: [shown, ...((v.fact_summary ?? v.summary) ? [String(v.fact_summary ?? v.summary)] : []), ...rules, about],
    };
  }
  // no entry from the server at build time: the strategy's own words, in the same lengths
  const plainTitle = (n: string) => `${n}: rules and verdict · StratLab`;
  const bare = shortName(name).replace(/\s*\([^)]*\)/g, "").trim();
  return {
    path: `/library/${id}`, index: true,
    title: [name, shortName(name), bare].map(plainTitle).find((t) => t.length <= TITLE_MAX) ?? plainTitle(cut(bare, TITLE_MAX - plainTitle("").length)),
    description: sentences([`${name}: the rules StratLab tested, the return after costs beside buy and hold, and the four checks.`],
      [], ["Facts about the past, not advice.", "Facts, not advice."], DESCRIPTION_MAX),
    heading: name,
    summary: [...rules, about],
  };
};

/** A landing-page address's own heading ("Plans and prices" at /pricing), the h1 the landing page shows there, so the
 * address's own HTML and the drawn page agree (R8V-008); none for the home page and addresses without their own page. */
export const landingHeading = (path: string): string | undefined => {
  const p = pageMeta(path);
  return p && p.path !== "/" && p.heading !== TAGLINE ? p.heading : undefined;
};

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
