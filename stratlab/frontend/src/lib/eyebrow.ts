import { NAV, pageAt } from "./nav";

/** A page's eyebrow, "Invest · Market view": its space and group, read from the one map of the app (lib/nav.ts) so a page that
 * moves in the menu changes here too. `to` is the page's own address, as listed in the menu. */
export function eyebrowOf(to: string): string {
  const at = pageAt(to);
  return at ? `${NAV[at.space].label} · ${at.group.label}` : "Invest";
}
