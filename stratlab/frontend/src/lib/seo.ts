import { absolute, GATE_DESCRIPTION, NOT_FOUND_DESCRIPTION, pageMeta, VERDICT_DESCRIPTION } from "../content/seo";

/* The tags a search engine or a link preview reads, kept right while someone moves between pages (the static page
 * already carries the right ones for its own address: scripts/seoPages.mjs). Every page gets a description of its own, a
 * canonical address, and noindex unless it is a public page worth finding. */

export type Seo = { description: string; canonical: string; index: boolean; title?: string };
export type SeoKind = "public" | "gate" | "notfound" | "verdict" | "account";

const tidy = (path: string) => (path.split(/[?#]/)[0].replace(/\/+$/, "") || "/");

/** What to tell search engines about an address. `kind` says what the page is when the table doesn't know it. */
export function seoFor(path: string, kind: SeoKind = "public", over: Partial<Seo> = {}): Seo {
  const p = tidy(path);
  const known = kind === "public" ? pageMeta(p) : undefined;
  const base: Seo = known
    ? { description: known.description, canonical: absolute(known.canonical ?? known.path), index: known.index }
    : { description: kind === "notfound" ? NOT_FOUND_DESCRIPTION : kind === "verdict" ? VERDICT_DESCRIPTION : GATE_DESCRIPTION, canonical: absolute(p), index: false };
  return { ...base, ...over };
}

function meta(selector: string, make: () => HTMLElement, set: (el: HTMLElement) => void) {
  let el = document.head.querySelector<HTMLElement>(selector);
  if (!el) { el = make(); document.head.appendChild(el); }
  set(el);
}
const named = (attr: "name" | "property", key: string, content: string) =>
  meta(`meta[${attr}="${key}"]`, () => { const m = document.createElement("meta"); m.setAttribute(attr, key); return m; }, (el) => el.setAttribute("content", content));

/** Write the tags into the page's head. */
export function applySeo(s: Seo, title = document.title) {
  named("name", "description", s.description);
  named("name", "robots", s.index ? "index, follow" : "noindex, follow");
  named("property", "og:title", title);
  named("property", "og:description", s.description);
  named("property", "og:url", s.canonical);
  named("name", "twitter:title", title);
  named("name", "twitter:description", s.description);
  meta('link[rel="canonical"]', () => { const l = document.createElement("link"); l.rel = "canonical"; return l; }, (el) => el.setAttribute("href", s.canonical));
}
