/* The first-run guide: the "What brings you here?" question, then a four-step tour, then Home's first-steps checklist,
 * one at a time. The account remembers what was seen (/me's `onboarding`, PUT /me/onboarding), so it shows once per
 * person, not once per device; this browser's old flag still counts, and is copied to the account.
 * Pure rules plus a tiny store for "a guide is open"; unit/onboarding.test.mjs checks the rules. */
import { useSyncExternalStore } from "react";
import type { Me } from "./types";

/** This browser's flag from before the account kept it. Still read (and copied to the account), still written. */
export const TOUR_SEEN = "stratlab.tour.v1";

/** The question is asked only on a home page (`/` or a space's home), never over a page someone opened by a link. */
export const HOME_PATHS = ["/", "/trade", "/invest", "/money", "/mine"];
export const isHomePath = (path: string) => HOME_PATHS.includes(path.replace(/(.)\/$/, "$1"));

type MeLike = Pick<Me, "prefs" | "onboarding"> | null | undefined;

/** The welcome question is still to be asked: neither answered (level and focus) nor closed on any device. */
export function welcomePending(me: MeLike): boolean {
  if (!me) return false;
  const answered = !!me.prefs?.level && !!me.prefs?.focus;
  return !answered && !me.onboarding?.welcome;
}

/** Ask now: the account still needs the question, and the person is on a home page. */
export const askWelcome = (me: MeLike, path: string) => welcomePending(me) && isHomePath(path);

/** The tour was finished or closed: on the account, or (from before) in this browser. */
export function tourSeen(me: MeLike, local: string | null): boolean {
  return !!me?.onboarding?.tour || local === "1";
}

/** The tour starts by itself only right after the welcome question is answered, and only if it was never seen. Someone
 * who answered long ago (on any device) isn't shown it again; Help in the account menu opens it any time. */
export const autoTour = (justWelcomed: boolean, seen: boolean) => justWelcomed && !seen;

/* "A guide is open": while the question or the tour shows, Home's checklist waits, so a newcomer sees one guide at a time. */
let open = false;
const subs = new Set<() => void>();
export function setGuideOpen(v: boolean) {
  if (open === v) return;
  open = v;
  subs.forEach((f) => f());
}
const subscribe = (f: () => void) => { subs.add(f); return () => { subs.delete(f); }; };
export const useGuideOpen = () => useSyncExternalStore(subscribe, () => open, () => false);
