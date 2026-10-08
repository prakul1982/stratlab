/* The landing page's questions, one list: the page draws it, and the search-engine markup (FAQPage) is built from the same
 * words at build time, so the two can't say different things. Plain data: no React, so the build and the tests read it
 * as it is. An answer is a list of short paragraphs. Facts only: nothing here says what to buy or sell. */

export type Faq = { q: string; a: string[] };

export const FAQ: Faq[] = [
  { q: "Does StratLab tell me what to buy?",
    a: ["No. It shows facts: reported numbers, filings, prices and how a set of rules would have done in the past. It never says buy, sell or hold, gives no price targets or ratings, and nothing on StratLab is investment advice."] },
  { q: "Does StratLab place real trades?",
    a: ["No. Testing is on past prices and paper trading uses fake money. No real orders are ever placed."] },
  { q: "Do I need to know how to code?",
    a: ["No. You describe the idea in plain words. If something is missing, like when to sell, StratLab asks. You can also tap any rule to change it."] },
  { q: "Why not just look at the backtest return?",
    a: ["Because almost any idea can be tuned to look great on past prices. The four checks ask whether it would have worked on data it never saw, with slightly different settings, and with worse luck. That's the difference between an edge and a coincidence."] },
  { q: "Who can see my money data?",
    a: ["Only you. Your holdings, funds, net worth, trades and tax figures are kept per account, never shown to anyone else, and each page deletes its data in one step. A mutual fund statement and its password are read once and not stored."] },
  { q: "Does StratLab file my tax return?",
    a: ["No. The tax report is an estimate to check with a chartered accountant, and the ITR-ready export lays out your year the way the ITR-2 and ITR-3 schedules ask for it. You or your CA file the return."] },
  { q: "Can I backtest options?",
    a: ["No. Backtesting options needs real past prices for every strike, and StratLab doesn't fill the gap with a pricing model. It records the NIFTY, BANKNIFTY, FINNIFTY, MIDCPNIFTY and SENSEX chains every 5 minutes to build that history.",
      "What you can do today is paper trade options: live on NSE, BSE, MCX and NSE currency option prices, with fills at the real bid and ask, at a set time or when a notebook's rules signal. The Greeks and the payoff before expiry are model estimates, labelled with their inputs."] },
  { q: "How do invite rewards work?",
    a: ["You and a friend can each get a free month of Basic. Your invite link is in Account.",
      "Your friend: joins with your link and uses StratLab on 3 different days in their first 14 days. They then get a free month of Basic.",
      "You: a free month of Basic when such a friend becomes active, for your first 2 friends in any 12 months. Another free month when a friend you invited pays for a plan (their first payment, within 90 days of joining), again for your first 2 paying friends in 12 months. After that, each further paying friend gives you 8 days free, up to 8 times in 12 months.",
      "If you already pay for a plan, your free time is saved and starts when your paid plan ends."] },
  { q: "Is there an app?",
    a: ["StratLab installs from the browser: on Android or a computer choose Install app, on an iPhone tap Share, then Add to Home Screen. It opens full screen with its own icon and sends alerts as notifications."] },
];

/** An answer as one block of text, for the page's markup for search engines. */
export const faqText = (f: Faq) => f.a.join(" ");
