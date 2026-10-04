/** Pages that share one menu entry and switch between each other with tabs. Every page keeps its own URL. */
export type Family = "scans" | "watch";

export const FAMILIES: Record<Family, { label: string; home: string; views: [string, string][] }> = {
  scans: {
    label: "Scans", home: "/research/scans",
    views: [["/research/scan", "Trend scan"], ["/research/screens", "Screener"], ["/research/rotation", "Sector rotation"], ["/research/filings", "Red flags"]],
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
  Money: [
    { to: "/holdings", label: "My Holdings", icon: "book", title: "Your stocks from your broker's file",
      blurb: "Your stocks from your broker's file: value, gain or loss, sectors, dividends and each stock's filings." },
    { to: "/tax-report", label: "Tax report", icon: "receipt", title: "Capital gains by financial year, from your tradebooks",
      blurb: "Capital gains by financial year from your tradebooks, matched first in, first out. An estimate to check with your CA." },
    { to: "/money/net-worth", label: "Net worth", icon: "wallet", title: "What you own minus what you owe, with your insurance policies",
      blurb: "Stocks, funds, PF, PPF, NPS, FDs, gold and property, minus loans; with EMIs, prepayment maths and your policies." },
    { to: "/money/mutual-funds", label: "Mutual funds", icon: "layers", title: "Your funds from your CAS: value, XIRR, allocation and capital gains",
      blurb: "Import your CAMS/KFintech statement: each fund's value, XIRR, category mix and capital gains by year." },
  ],
};
