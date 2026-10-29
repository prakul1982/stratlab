/* The StratLab cards that hold a Free account's ad place while ads are off or declined (ADS-1). They quote the plans' real numbers, so they
 * live apart from lib/ads.ts: that file is read by the consent banner on every public page (a policy page too), and the plans file with its
 * 14 kB of prices and feature lists would have come with it (R5V-020: a policy page stays under 400 KB of JavaScript). Only the app's slot, in the
 * signed-in app, draws these. */
import { LIMITS } from "./plans";

export interface HouseCard { id: "plans" | "luck" | "brief"; title: string; text: string; to: string; cta: string }
/** The cards that hold a Free account's slot while ads are off: StratLab's own pages, in plain facts. */
export const HOUSE: HouseCard[] = [
  { id: "plans", title: "Basic has more AI builds and deep dives",
    text: `Free includes ${LIMITS.free.ai_builds_per_month} AI strategy builds and ${LIMITS.free.deepdives_per_month} company deep dives a month. Basic includes ${LIMITS.basic.ai_builds_per_month} and ${LIMITS.basic.deepdives_per_month}, and has no ads.`,
    to: "/plans", cta: "See the plans" },
  { id: "luck", title: "Test your idea with the four luck checks",
    text: "Describe a rule in plain words. StratLab runs it on years of real prices and asks whether it held up on prices it never saw.",
    to: "/new", cta: "Test an idea" },
  { id: "brief", title: "Read today's market brief",
    text: "A short brief after each market close, for India, the US and the companies you follow.",
    to: "/news", cta: "Open the briefs" },
];

/** One card for a page, the same every time for the same `seed` (a company's symbol), so the card does not change as the page redraws. */
export function houseCard(seed: string): HouseCard {
  let h = 0;
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return HOUSE[h % HOUSE.length];
}
