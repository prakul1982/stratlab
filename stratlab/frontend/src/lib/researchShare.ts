/* Share links to research (bet 3): a dated public teaser of a deep dive or a theme at /r/<token>, made by the server
 * (backend/app/share.py), counted against the plan's share links a month (plans.py share_links_per_month; planFeatures.ts
 * SHARE_LINKS says the same), and turned off from Account. */
import type { Region } from "./research";

export type ShareMade = { token: string; url: string; title: string; kind: "deep" | "theme" };
export type ShareRow = { token: string; url: string; kind: "deep" | "theme"; title: string; region: Region; made: string; on: boolean };
export type ShareList = { links: ShareRow[]; used: number; limit: number | null };

/** "2 of 30 share links made this month" / "3 share links made this month (no limit on your plan)". */
export function shareCountLine(used: number, limit: number | null): string {
  const n = (k: number) => `${k} share link${k === 1 ? "" : "s"}`;
  return limit == null ? `${n(used)} made this month (no limit on your plan)` : `${used} of ${n(limit)} made this month`;
}

/** What a link is, for the list and the screen reader: "Deep dive · India" / "Theme · US". */
export function shareKindLabel(r: Pick<ShareRow, "kind" | "region">): string {
  return `${r.kind === "theme" ? "Theme" : "Deep dive"} · ${r.region === "US" ? "US" : "India"}`;
}

/** The note after a link is copied: what the person shared and who can see it. */
export function sharedNote(kind: "deep" | "theme"): string {
  return `Link copied. Anyone with it sees a dated snapshot of this ${kind === "theme" ? "theme" : "deep dive"}, not your account; turn it off any time in Account.`;
}
