/** A page's intro under its title (owner, 18 Nov: "everything this just clutters the pages"): one short sentence shows, the rest is behind
 *  "More". An intro longer than LEDE_MAX characters is cut after its first sentence when that is short; otherwise null (it shows whole).
 *  LIVE13A (fix18): never at a colon or semicolon, which left half a sentence ("For each India watchlist company…" on the watchlist page).
 *  `joint` is kept for the callers: always "" now. */
export const LEDE_MAX = 120;
export function splitLede(text: string): { first: string; joint: string; rest: string } | null {
  if (text.length <= LEDE_MAX) return null;
  const s = text.match(/^(.{20,}?[.!?])\s+(?=[A-Z₹$"“(])/);
  if (s && s[1].length <= LEDE_MAX) return { first: s[1], joint: "", rest: text.slice(s[0].length).trim() };
  return null;
}
