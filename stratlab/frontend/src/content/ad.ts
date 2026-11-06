/* R15: the ad landing's words (/start, and "/" for a visit from the social ad). Kept out of content/seo.ts, which the landing page
 * downloads: only the ad landing's own file and the build (scripts/seoPages.mjs, its HTML) read them (R5V-020). */
export const AD_TITLE = "Try StratLab free · StratLab";
export const AD_HEADLINE = "Test trading ideas on real prices, research any company, track your money.";
export const AD_POINTS = ["Backtests after costs, with four checks for luck.", "Company numbers and filings, India and US.", "Holdings, gains and tax from your own files."];
export const AD_DESCRIPTION = "StratLab tests a trading idea on years of real prices after costs, shows any Indian or US company's numbers and filings, and works out your holdings, gains and tax. Free to start, no card.";
/** The page as the build writes it: the home page is its canonical address, so it is not in the sitemap. */
export const AD_PAGE = { path: "/start", title: AD_TITLE, description: AD_DESCRIPTION, index: true, canonical: "/", heading: AD_HEADLINE,
  summary: [AD_POINTS.join(" "), "Free to start, no card."] };
