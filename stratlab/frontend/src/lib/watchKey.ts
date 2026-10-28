/* The two facts about Market Watch's panel the page needs before the panel's code is downloaded (MW-1): where its layout is kept
 * on this device, and when it is a full-height sheet. On their own so a visitor's first download holds them and not the panel's
 * layout code (the policy pages are held to a size: R5V-020). */
export const LAYOUT_KEY = "stratlab.watch.layout";

/** A phone's width and under: the panel is a full-height sheet, with no size or place of its own. */
export const isSheet = (vw: number): boolean => vw <= 900;
