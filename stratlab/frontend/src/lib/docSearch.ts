/* Search inside filings and call transcripts (backend app/doc_search.py): the answer's shape, the address of a search, and
 * the extracts read into text and marked words without ever putting a document's text into the page as HTML. */

export type DocRegion = "IN" | "US";

export interface DocHit {
  id: number; symbol: string; company: string; region: DocRegion; sector: string | null; kind: string; kind_label: string;
  title: string; filed_at: string; page: number | null; pages: number | null; url: string | null; source: string; ocr: boolean;
  /** At most two short extracts: escaped text, the matched words in <mark>. */
  snippet: string[];
}
export interface DocLimits { hits: number | null; days: number | null; filters: boolean; export: boolean }
export interface DocAnswer {
  q: string; region: DocRegion; symbols: string[]; theme: string | null; kinds: string[]; sectors: string[]; from: string | null; to: string | null;
  floor: string | null; limits: DocLimits; note: string; covers: string; ready: boolean; hits: DocHit[]; total: number; page: number; pages: number;
  more: boolean; by_date: boolean; locked: number; facets: { kinds: Record<string, number>; years: Record<string, number> };
}
export interface DocCoverage { documents: number; companies: number; newest: string | null; oldest: string | null; kinds: Record<string, number> }
export interface DocStatus {
  ready: boolean; coverage: Partial<Record<DocRegion, DocCoverage>>; sectors: Partial<Record<DocRegion, string[]>>;
  covers: Record<DocRegion, string>; kinds: Record<DocRegion, { id: string; label: string }[]>; limits: DocLimits; note: string;
}

/** What a search asks for, as the page's address keeps it. */
export interface DocQuery { q: string; region: DocRegion; symbols: string[]; sectors: string[]; kinds: string[]; theme: string; from: string; to: string; page: number }

export const EMPTY: DocQuery = { q: "", region: "IN", symbols: [], sectors: [], kinds: [], theme: "", from: "", to: "", page: 1 };

const list = (v: string | null) => (v ?? "").split(",").map((x) => x.trim()).filter(Boolean);

/** The search the page's address holds (?q=…&region=US&symbols=A,B&sector=…&kind=…&theme=…&from=…&to=…&page=2). */
export function readQuery(p: URLSearchParams): DocQuery {
  const page = Math.max(1, Math.floor(Number(p.get("page")) || 1));
  return { q: (p.get("q") ?? "").slice(0, 200), region: p.get("region")?.toUpperCase() === "US" ? "US" : "IN",
    symbols: list(p.get("symbols")).map((s) => s.toUpperCase()).slice(0, 20), sectors: list(p.get("sector")).slice(0, 12),
    kinds: list(p.get("kind")).slice(0, 4), theme: (p.get("theme") ?? "").slice(0, 80), from: p.get("from") ?? "", to: p.get("to") ?? "", page };
}

/** The page's address for a search (empty parts left out, the first page unnamed). */
export function writeQuery(d: DocQuery): URLSearchParams {
  const p = new URLSearchParams();
  if (d.q.trim()) p.set("q", d.q.trim());
  if (d.region !== "IN") p.set("region", d.region);
  if (d.symbols.length) p.set("symbols", d.symbols.join(","));
  if (d.sectors.length) p.set("sector", d.sectors.join(","));
  if (d.kinds.length) p.set("kind", d.kinds.join(","));
  if (d.theme.trim()) p.set("theme", d.theme.trim());
  if (d.from) p.set("from", d.from);
  if (d.to) p.set("to", d.to);
  if (d.page > 1) p.set("page", String(d.page));
  return p;
}

/** The API's address for a search; `filters` false (Free) sends only the words, the market and the companies. */
export function apiPath(d: DocQuery, filters: boolean, base = "/research/docs/search"): string {
  const p = new URLSearchParams({ q: d.q.trim(), region: d.region });
  if (d.symbols.length) p.set("symbols", d.symbols.join(","));
  if (filters) {
    if (d.sectors.length) p.set("sector", d.sectors.join(","));
    if (d.kinds.length) p.set("kind", d.kinds.join(","));
    if (d.theme.trim()) p.set("theme", d.theme.trim());
    if (d.from) p.set("frm", d.from);
    if (d.to) p.set("to", d.to);
  }
  if (d.page > 1 && base.endsWith("/search")) p.set("page", String(d.page));
  return `${base}?${p}`;
}

/** Filters set that the plan doesn't give (sent to a Free account's page from a link): named, so the page can say so. */
export function lockedFilters(d: DocQuery): string[] {
  return [d.sectors.length ? "sector" : "", d.kinds.length ? "kind of document" : "", d.theme.trim() ? "theme" : "", d.from || d.to ? "dates" : ""].filter(Boolean);
}

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', "#x27": "'", "#39": "'" };
const unescape = (s: string) => s.replace(/&(amp|lt|gt|quot|#x27|#39);/g, (_, e: string) => ENTITIES[e]);

/** An extract as pieces of plain text, each marked or not: only <mark> and </mark> are read as markup; everything else is text
 * (the server escaped it, so it is read back and drawn as text, never as HTML). */
export function snippetParts(html: string): { text: string; hit: boolean }[] {
  const out: { text: string; hit: boolean }[] = [];
  let hit = false;
  for (const part of html.split(/(<\/?mark>)/)) {
    if (part === "<mark>") hit = true;
    else if (part === "</mark>") hit = false;
    else if (part) out.push({ text: unescape(part), hit });
  }
  return out;
}

/** "Page 4 of 20 · NSE copy": where the link opens. */
export function whereLine(h: Pick<DocHit, "page" | "pages" | "source">): string {
  const page = h.page ? `Page ${h.page}${h.pages ? ` of ${h.pages}` : ""}` : "";
  return [page, `${h.source} copy`].filter(Boolean).join(" · ");
}

/** What the plan gives, in one line for under the results. */
export function planLine(l: DocLimits): string {
  if (l.hits != null) return `Free shows the first ${l.hits} results of a search from the last year, by company. Basic shows every result with every filter.`;
  if (l.days != null) return "Basic searches the last year with every filter. Pro searches every year stored and downloads the results.";
  return "Every year stored, every filter, and the results as a CSV.";
}

/** "27 documents" / "1 document"; with `more`, the search stopped at its limit and there may be others. */
export function totalLine(total: number, more: boolean): string {
  return `${more ? "At least " : ""}${total.toLocaleString("en-IN")} document${total === 1 ? "" : "s"}`;
}

/** The address of the search inside one company's documents (the company page's link). */
export const companySearch = (region: DocRegion, symbol: string, q = "") =>
  `/research/search?${writeQuery({ ...EMPTY, region, symbols: [symbol], q })}`;
