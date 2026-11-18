/** A page's intro under its title (owner, 18 Nov: "everything this just clutters the pages"): one short sentence shows, the rest is behind
 *  "More". An intro longer than LEDE_MAX characters is cut after its first sentence when that is short, else at its first colon or
 *  semicolon when the words before it are; otherwise null (it shows whole). `joint` is what joins the two parts: "" after a sentence, or the
 *  colon or semicolon, said only when the rest is shown. */
export const LEDE_MAX = 120;
export function splitLede(text: string): { first: string; joint: string; rest: string } | null {
  if (text.length <= LEDE_MAX) return null;
  const s = text.match(/^(.{20,}?[.!?])\s+(?=[A-Z₹$"“(])/);
  if (s && s[1].length <= LEDE_MAX) return { first: s[1], joint: "", rest: text.slice(s[0].length).trim() };
  const c = text.match(/^(.{30,}?)([:;])\s+/);
  if (c && c[1].length <= LEDE_MAX && !/\d$/.test(c[1])) return { first: c[1], joint: c[2], rest: text.slice(c[0].length).trim() };
  return null;
}
