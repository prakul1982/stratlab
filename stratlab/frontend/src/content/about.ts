/** /about's text (AS1), on its own so the policy pages don't download it: LegalPage loads it only for /about, and the build
 * (scripts/seoPages.mjs) writes it whole into about/index.html as it does the policies. */
// AS1: who runs StratLab, what it is, where its figures come from and how they are checked, linked from every page's footer. Facts
// from the app itself only; the business's legal name, address and GSTIN come from the owner's settings, as on /contact
import type { Block } from "./legal";

export const ABOUT_BLOCKS: Block[] = [
    { p: "StratLab (stratlab.studio) is a research and education website and app for Indian (NSE and BSE) and US stocks. It does three things: it tests trading ideas on years of past prices after brokerage, taxes and slippage; it shows each listed company's prices, reported results and filings; and it adds up what a signed-in person owns, from the files they upload, for value, gains and tax." },
    { h: "What anyone can read without an account" },
    { ul: [
      "[Company pages](/stocks): every Indian and US listed company with a page, A to Z and by index: the last close, the year's range, key figures, several years of revenue and profit, and recent exchange or SEC filings with links to the documents.",
      "[Themes](/themes): listed companies grouped by investment theme, with the companies in each layer of the theme's value chain.",
      "[Strategy library](/library): well-known trading rule sets that StratLab ran through its own backtest, each shown with the rules tested, the return after costs beside buy and hold, and the result of four checks for luck, including the ones that failed.",
      "[Blog](/blog): a market brief for India and for the US after each trading day, worked out from the day's closing figures, and research posts on StratLab's own data, each with its method and its limits.",
      "[Data status](/status): every dataset the site shows, when it was last updated and when it is next due.",
    ] },
    { p: "Testing your own ideas, paper trading, the full research screens and the Money space need a free account, which signs in with Google. A link from a public page into the app says that it needs sign-in." },
    { h: "Where the figures come from" },
    { p: "Every figure comes from a company's reported results, its exchange filings (NSE and BSE in India, the SEC in the US), its own documents such as annual reports and presentations, daily market prices, or, in Money, the files a person uploads. Each company page says the date of the price it shows and lists its recent filings, and its section **How these figures are worked out** gives the formula behind each figure. A page with no recent price or no reported numbers says so and is kept out of search results." },
    { h: "How they are checked" },
    { ul: [
      "A market value is shown only when it agrees with the company's own reported figures; when it doesn't, the page shows n/a instead of a number that may be wrong.",
      "Every quote in an AI summary of a company's documents is checked against the document it comes from, and AI summaries restate facts only.",
      "The IPO lists are compared every day with the exchanges' and the regulator's own lists.",
      "Anyone signed in can report a figure that looks wrong from the figure itself; each report is checked and answered.",
    ] },
    { h: "Facts, not advice" },
    { p: "StratLab shows facts for research and education. It gives no tips, price targets, ratings or quality scores, never ranks stocks or funds, and nothing on it is investment advice. Backtests and paper trading use past prices and simulated money: no real orders are ever placed, and past results don't predict future returns. Tax figures are estimates, and StratLab files no tax return." },
    { h: "Who runs it" },
    { p: "StratLab's terms are governed by the laws of India, its prices are in Indian rupees, and its privacy policy is written to meet India's Digital Personal Data Protection Act, 2023. The Free plan costs nothing; the Basic and Pro subscriptions pay for the service, and public pages and Free accounts may show Google ads to a visitor who allows them (see the [privacy policy](/privacy)). Basic and Pro have no ads." },
    { ul: [
      "**Business:** {name}",
      { when: "address", text: "**Address:** {address}" },
      { when: "gstin", text: "**GSTIN:** {gstin}" },
      "**Help and questions:** [{email}](mail:email)",
      "**Payments, invoices and refunds:** [{billing}](mail:billing)",
      "**Privacy and your data:** [{privacy}](mail:privacy)",
    ] },
    { p: "Every way to reach StratLab is on the [contact page](/contact)." },
  ];
