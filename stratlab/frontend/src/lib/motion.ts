/** Did the reader ask their device for less motion? */
export const prefersReducedMotion = (): boolean => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** How a script should scroll: "smooth", unless the reader asked for less motion (A11Y-003). The style sheet's reduce-motion
 * rule stops animations and transitions but not a scroll a script starts, so each of those asks here. */
export const scrollBehavior = (): ScrollBehavior => (prefersReducedMotion() ? "auto" : "smooth");
