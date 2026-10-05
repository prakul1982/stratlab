/** Pages that share one menu entry and switch between each other with tabs. Every page keeps its own URL. */
export type Family = "scans" | "watch";

export const FAMILIES: Record<Family, { label: string; home: string; views: [string, string][] }> = {
  scans: {
    label: "Scans", home: "/research/scans",
    views: [["/research/scan", "Trend scan"], ["/research/screens", "Screener"], ["/research/rotation", "Sector rotation"], ["/research/filings", "Red flags"],
      ["/invest/breadth", "Market breadth"], ["/invest/etf-gaps", "ETF vs NAV"]],
  },
  watch: {
    label: "Watchlist", home: "/research/watchlist",
    views: [["/research/watchlist", "List"], ["/research/investor", "At a glance"]],
  },
};

/** The family a path belongs to, if any. */
export function familyOf(path: string): Family | null {
  for (const f of Object.keys(FAMILIES) as Family[]) if (FAMILIES[f].views.some(([p]) => p === path)) return f;
  return null;
}

const KEY = (f: Family) => `stratlab.view.${f}`;

/** The tab last opened in a family, so its menu entry reopens where you left off. */
export function lastView(f: Family): string {
  let saved: string | null = null;
  try { saved = localStorage.getItem(KEY(f)); } catch { /* storage off */ }
  return FAMILIES[f].views.some(([p]) => p === saved) ? saved! : FAMILIES[f].views[0][0];
}

export function rememberView(path: string) {
  const f = familyOf(path);
  if (f) try { localStorage.setItem(KEY(f), path); } catch { /* storage off */ }
}

/** One menu entry kept as data. `icon` names one of the menu's icons (ICONS in Shell); an unknown name gets a plain
 * one. `blurb` is the line under it on its space's home page. */
export type NavEntry = { to: string; label: string; icon?: string; title?: string; blurb?: string };

/** Menu groups kept as data, by name. "Money" is the Money space's menu, in order: each Money feature adds one line
 * here, and it shows both in the menu and as a card on the Money home, so only what's built ever appears. */
export const NAV_GROUPS: Record<string, NavEntry[]> = {
  /** Invest pages beyond the menu's fixed entries, kept as data like Money's. Each also opens as a tab among the Scans
   * (FAMILIES.scans), so the Scans menu entry already leads to it. */
  Invest: [
    { to: "/invest/breadth", label: "Market breadth", icon: "pulse", title: "How many stocks rise, fall, sit above their averages or make new highs",
      blurb: "Advances and declines, stocks above their 20/50/200-day averages, 52-week highs and lows, McClellan and sectors." },
    { to: "/invest/etf-gaps", label: "ETF vs NAV", icon: "lens", title: "Each Indian ETF's price against its indicative NAV and last NAV",
      blurb: "How far each ETF's price is from what a unit holds, the widest gap first, with 30 days of history and alerts." },
  ],
  /** Trade pages beyond the menu's fixed entries, kept as data like Money's. */
  Trade: [
    { to: "/trade/positioning", label: "Positioning", icon: "layers", title: "Participant-wise open interest, FII/DII flows, PCR, max pain and IV",
      blurb: "Who holds index futures and options, FII and DII cash flows, each index's PCR, OI by strike and ATM IV." },
    { to: "/trade/journal", label: "Trade journal", icon: "book", title: "Your real trades paired into round trips, judged by the verdict's checks",
      blurb: "Import your tradebook or tax P&L, equity and F&O: every round trip with its charges, your notes, and the verdict's honesty checks on your real trades." },
    { to: "/trade/fo-changes", label: "F&O changes", icon: "calendar", title: "Stocks entering and leaving F&O, lot-size revisions and expiry-day changes",
      blurb: "One dated list from the exchange's contract file and circulars: exits with the last series, old and new lots, expiry days." },
  ],
  Money: [
    { to: "/holdings", label: "My Holdings", icon: "book", title: "Your stocks from your broker's file",
      blurb: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and each stock's filings." },
    { to: "/tax-report", label: "Tax report", icon: "receipt", title: "Capital gains by financial year, from your tradebooks",
      blurb: "Capital gains by financial year from your tradebooks, matched first in, first out. An estimate to check with your CA." },
    { to: "/money/net-worth", label: "Net worth", icon: "wallet", title: "What you own minus what you owe, with your insurance policies",
      blurb: "Stocks, funds, PF, PPF, NPS, FDs, gold and property, minus loans; with EMIs, prepayment maths and your policies." },
    { to: "/money/mutual-funds", label: "Mutual funds", icon: "layers", title: "Your funds from your CAS: value, XIRR, allocation and capital gains",
      blurb: "Import your CAMS/KFintech statement: each fund's value, XIRR, category mix and capital gains by year." },
    { to: "/money/tax-tools", label: "Tax tools", icon: "receipt", title: "Dividends, advance tax and the long-term gains exemption",
      blurb: "Dividends with TDS, advance tax due on each date with reminders, and how much of the ₹1.25 lakh exemption is left." },
    { to: "/money/us-tax", label: "US stocks tax", icon: "compass", title: "US shares in Indian tax: gains in rupees, foreign tax credit and Schedule FA",
      blurb: "Your US sales in rupees at SBI's TT buying rate, the 24-month rule, the US tax credit and the calendar-year Schedule FA." },
    { to: "/money/itr", label: "ITR-ready export", icon: "receipt", title: "Your year laid out like the ITR schedules, and a PDF pack for your CA",
      blurb: "Schedule 112A, CG, dividends, F&O turnover, tax paid and Schedule FA as a spreadsheet or one PDF for your CA. Not a filed return." },
    { to: "/money/sip-test", label: "Test a SIP", icon: "pulse", title: "What a stock or ETF SIP of yours would have done on past prices",
      blurb: "An amount every day, week or month into stocks or ETFs, with a step-up or a dip rule: charges, XIRR, the deepest fall and a lump sum beside it." },
    { to: "/money/rates", label: "Rates", icon: "receipt", title: "T-bills, government bonds, small savings and your deposits, after your tax",
      blurb: "This quarter's small savings rates, T-bill cut-offs, bond yields and the repo rate, each with its yield after tax at your rate." },
    { to: "/money/calendar", label: "Money calendar", icon: "calendar", title: "Tax due dates, results, dividends and your own dates in one calendar",
      blurb: "Advance tax and ITR dates, results and dividends for your stocks, maturities, premiums and EMIs, with a calendar feed." },
  ],
};
