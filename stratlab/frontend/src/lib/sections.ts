/* Sections a person can close and put in their own order (owner, 7 Nov: "give option to close every tab ... open by default but give
 * option to close and remember what closed", and "let users re arrange everything ... do it everywhere"). The words of it, with no
 * imports, so the unit tests run it as it is; kit/Section.tsx is the part on the page.
 *
 * What is kept, on this device and per person: which sections are closed (`<page>|<section>` → true) and, per page, the order of its
 * sections. A page is its route with the part that names one thing left out, so closing "Filings" on one company closes it on every
 * company. A section is its card's `id`, else its title's words. */

/** The page a path is: a company, a chart, a notebook... is one page whatever it shows. */
export function routeKey(path: string): string {
  const p = (path.replace(/\/+$/, "") || "/").split("?")[0].split("#")[0];
  const rules: [RegExp, string][] = [
    [/^\/research\/(IN|US)\/[^/]+\/deep$/, "/research/$1/*/deep"],
    [/^\/research\/(IN|US)\/[^/]+$/, "/research/$1/*"],
    [/^\/chart\/[^/]+\/[^/]+$/, "/chart/*"],
    [/^\/invest\/ipos\/[^/]+$/, "/invest/ipos/*"],
    [/^\/n\/[^/]+\/e\/[^/]+$/, "/n/*/e/*"],
    [/^\/n\/[^/]+(\/(compare|market))?$/, "/n/*$1"],
    [/^\/options\/s\/[^/]+$/, "/options/s/*"],
    [/^\/paper\/[^/]+$/, "/paper/*"],
    [/^\/trade\/signals\/[^/]+$/, "/trade/signals/*"],
  ];
  for (const [re, to] of rules) if (re.test(p)) return p.replace(re, to);
  return p;
}

/** A section's name in the kept settings: its id, else its title's words ("Who owns it" → "who-owns-it"). */
export function sectionSlug(id: string | undefined | null, title: string): string {
  if (id) return id;
  return title.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60);
}

export const foldKey = (route: string, section: string) => `${route}|${section}`;

/** One section moved one place up (-1) or down (+1) among the sections shown together, in the order they are shown now. */
export function moved(shown: string[], id: string, by: -1 | 1): string[] {
  const i = shown.indexOf(id), j = i + by;
  if (i < 0 || j < 0 || j >= shown.length) return shown;
  const next = [...shown];
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}

/** The page's kept order with one group of sections (those shown together) put in their new order; the other groups keep theirs. */
export function keptWith(kept: string[] | undefined, group: string[]): string[] {
  return [...(kept ?? []).filter((x) => !group.includes(x)), ...group];
}

/** The CSS `order` of each child of a box, from the kept order: each child that is not a section (null) keeps its place, and the
 * sections fill the places sections have, in the kept order. A section the kept order doesn't name (new since, or drawn later)
 * keeps its own place among them. No kept order: null (nothing to set). */
export function orders(kids: (string | null)[], kept: string[] | undefined): number[] | null {
  if (!kept || !kept.length) return null;
  const slots = kids.map((k, i) => (k ? i : -1)).filter((i) => i >= 0);
  const ids = slots.map((i) => kids[i] as string);
  const known = kept.filter((x) => ids.includes(x));
  if (!known.length) return null;
  const placed = [...known];
  ids.forEach((id, n) => { if (!known.includes(id)) placed.splice(Math.min(n, placed.length), 0, id); });
  const out = kids.map((_, i) => i);
  const used = new Set<number>();
  placed.forEach((id, n) => {
    // the n-th place for sections goes to the n-th section in the kept order (the first child with that id not yet placed)
    const from = kids.findIndex((k, i) => k === id && !used.has(i));
    if (from < 0) return;
    used.add(from);
    out[from] = slots[n];
  });
  return out;
}

/* Whose settings: the app says who is signed in (Shell); a visitor's are "guest". Kept here, not read from the account code, so a
 * public page's cards don't bring that code with them. */
let user = "guest";
const heard = new Set<() => void>();
export function setSectionUser(id: string | null | undefined): void {
  const u = id || "guest";
  if (u === user) return;
  user = u;
  heard.forEach((f) => f());
}
export const sectionUser = (): string => user;
export function onSectionUser(f: () => void): () => void { heard.add(f); return () => { heard.delete(f); }; }
export const FOLDS_KEY = "stratlab.folds";
export const ORDER_KEY = "stratlab.order";
