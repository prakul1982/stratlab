/* site87 (owner: with India picked, "India defence" open, then "$ United States": the US mapped "India defence"): India and the US are kept
 * strictly apart on the theme page. A theme whose name names one market's country is that market's own; on a market switch the open theme
 * is cleared back to the chooser, or swapped for the other market's own theme of the same name when its library has one. The API refuses
 * the rest (backend app/intel/theme_market.py, the same patterns). */
export type Market = "IN" | "US";

const COUNTRY: Record<Market, RegExp> = {
  IN: /\b(india|indian|indias|bharat|bharatiya)\b/i,
  US: /\b(usa|u\.s\.a?\.?|united states|america|american|americas)(?=\W|$)|^us\b|\bus$/i,
};

/** The market whose country a theme's name names, or null (neither, or both). */
export function countryOf(name: string): Market | null {
  const s = name.split(/\s+/).filter(Boolean).join(" ");
  const hits = (Object.keys(COUNTRY) as Market[]).filter((m) => COUNTRY[m].test(s));
  if (/\bUS\b/.test(s) && !hits.includes("US")) hits.push("US");
  return hits.length === 1 ? hits[0] : null;
}

/** Whether a theme belongs to the other market (its name names that market's country). */
export const foreignTheme = (name: string, market: Market): boolean => { const c = countryOf(name); return !!c && c !== market; };

/** A theme's name with its country taken out ("India defence" → "Defence"). */
export function withoutCountry(name: string): string {
  const s = name.replace(/\b(india|indian|indias|bharat|bharatiya|usa|united states|america|american|americas)\b|\bu\.s\.a?\.?|\bUS\b|^us\b|\bus$/gi, " ")
    .replace(/\s+/g, " ").replace(/^[\s'’s-]+|[\s-]+$/g, "").trim();
  return s ? s[0].toUpperCase() + s.slice(1) : "";
}

/** The other market's word for a theme, where they differ ("Defence" in India is "Aerospace and defense" in the US). */
const SAME_THEME: Record<string, Record<Market, string>> = {
  defence: { IN: "Defence", US: "Aerospace and defense" },
  defense: { IN: "Defence", US: "Aerospace and defense" },
  "aerospace and defense": { IN: "Defence", US: "Aerospace and defense" },
  "aerospace and defence": { IN: "Defence", US: "Aerospace and defense" },
};

/** The names to look for in the other market's library for the theme open now, in order (never one naming another country). */
export function twinNames(name: string, to: Market): string[] {
  const base = withoutCountry(name);
  if (!base) return [];
  const out = [SAME_THEME[base.toLowerCase()]?.[to], base].filter((x): x is string => !!x && !foreignTheme(x, to) && countryOf(x) === null);
  return Array.from(new Set(out));
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
/** The library theme that is `want` by name (its name or its search words), or null. */
export function sameByName<T extends { name: string; q?: string }>(items: T[], want: string): T | null {
  const w = norm(want);
  return items.find((i) => norm(i.name) === w || (i.q != null && norm(i.q) === w)) ?? null;
}

/** The theme ideas offered under the box, with none the library chips already show and none of the other market's country. */
export function ideasBeside(ideas: string[], shown: { name: string; q?: string }[], market: Market, short: (n: string) => string = (n) => n): string[] {
  const have = new Set(shown.flatMap((i) => [norm(i.name), norm(short(i.name)), ...(i.q ? [norm(i.q)] : [])]));
  return ideas.filter((t) => !foreignTheme(t, market) && !have.has(norm(t)));
}
