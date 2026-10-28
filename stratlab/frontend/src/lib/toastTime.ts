/** How long a message stays: 4.5 s for a short one, 9 s with a button, and longer for a long one (a second and a half more
 * for every 25 characters, up to 15 s), so a failed upload's two sentences ("We couldn't find the holdings in that file. It
 * needs a column for the stock...") can be read before they go (RC5-006). */
export function toastMs(msg: string, action: boolean): number {
  return Math.min(15000, Math.max(action ? 9000 : 4500, 2500 + msg.length * 60));
}
