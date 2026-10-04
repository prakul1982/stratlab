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

/** The Money space's pages (personal finance): [path, menu label, tooltip]. Each Money feature adds one line here. */
export const MONEY: [string, string, string][] = [
  ["/money/tax-tools", "Tax tools", "Dividends, advance tax and the long-term gains exemption"],
];
