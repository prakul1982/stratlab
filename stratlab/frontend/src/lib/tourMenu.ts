/* The tour holding the phone's menu open to point into it (DI-023). The request is kept here as well as sent, so the menu follows it
 * whenever the Shell starts listening or its page changes under the tour (LIVE3-014: /tour moves to Home as the tour opens, and
 * the move closed the drawer the first step had just opened, so "Four spaces" ringed the closed menu's off-screen switch). */
export const TOUR_MENU = "stratlab:tour-menu";
let held = false;
export const tourMenuHeld = (): boolean => held;
export function holdTourMenu(open: boolean) {
  held = open;
  window.dispatchEvent(new CustomEvent(TOUR_MENU, { detail: { open } }));
}
