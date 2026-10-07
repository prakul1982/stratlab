import { titleFor, DEFAULT_TITLE } from "./title";

/** What a signed-out visitor who opened a deep link (a company, the tax report) is told on the front page: the page they
 * asked for by name, a sign-in that comes back to it, and for a company its public page, which needs no account. */
export type Gate = { name: string; publicUrl: string | null };

/** The gate for an address, or null for the front page itself. `publicBase` is where the public company pages are
 * served (the site itself in production, the API on a local copy). */
export function gateFor(path: string, publicBase: string): Gate | null {
  const p = path.split(/[?#]/)[0];
  if (p === "/" || p === "") return null;
  const company = p.match(/^\/research\/(IN|US)\/([A-Za-z0-9&._-]{1,20})(?:\/deep)?\/?$/i);
  const title = titleFor(p);
  const name = title === DEFAULT_TITLE ? "this page" : title.replace(/ · StratLab$/, "");
  const publicUrl = company ? `${publicBase.replace(/\/$/, "")}/stocks/${company[1].toLowerCase()}/${encodeURIComponent(company[2].toUpperCase())}` : null;
  return { name, publicUrl };
}
