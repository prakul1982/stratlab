/* Saved searches and AI reads (R19): the pure parts, kept apart from the API so they can be tested without the app. One mechanism for every
 * page that has one (the server's saved_searches.py): each saved item has a kind, a name, the page's own parameters and a small snapshot of
 * what it showed when it was last read ({rows: {key: [label, value]}, figures: {name: number}}), so Update can say what changed. */
import { asOf, writtenAt, marketTz } from "./format";
import { amount } from "./themeFormat";
import type { Region, SectorAI } from "./research";

export type SavedKind = "theme" | "filings" | "company_ai" | "compare" | "deep_dive";
export interface Snap { rows: Record<string, [string, number | null]>; figures: Record<string, number | null> }
export interface SavedItem {
  id: string; kind: SavedKind; kind_label: string; name: string; params: Record<string, string>;
  saved_at: string; read_at: string | null; figures: Record<string, number | null>; rows: number | null;
  /** an AI read (the read itself stays in the app's shared store) */
  ai?: boolean;
  /** Update opens the page: its own button reads it again (a deep dive draws on the plan's monthly deep dives) */
  open_only?: boolean;
}
export interface Row { key: string; label: string; value: number | null }
export interface Changes {
  added: Row[]; added_count: number; removed: Row[]; removed_count: number;
  moves: { key: string; label: string; before: number; after: number; pct: number }[];
  figures: { name: string; before: number | null; after: number | null; change: number | null; pct: number | null }[];
  same: boolean;
}

/** The page a saved item opens: its own address with its parameters, as the page itself writes them. */
export function savedUrl(item: Pick<SavedItem, "kind" | "params">): string {
  const p = item.params ?? {};
  const q = (keys: string[]) => { const s = new URLSearchParams(); for (const k of keys) if (p[k]) s.set(k, p[k]); const t = s.toString(); return t ? `?${t}` : ""; };
  const seg = (s: string | undefined) => encodeURIComponent(s ?? "");
  switch (item.kind) {
    case "theme": return `/research/themes${q(["region", "q"])}`;
    case "filings": return `/research/filings${q(["region", "view", "flag", "range", "frm", "to", "q"])}`;
    case "company_ai": return `/research/${seg(p.region)}/${seg(p.symbol)}`;
    case "deep_dive": return `/research/${seg(p.region)}/${seg(p.symbol)}/deep`;
    case "compare": return `/research/compare${q(["region", "a", "b"])}`;
  }
}

/** Every company a theme read shows (each layer's, then those named in a sub-theme only), once each. */
function themeCompanies(r: SectorAI) {
  const seen = new Map<string, { name: string; cap: number | null; base: boolean }>();
  for (const c of [...r.value_chain.flatMap((v) => v.companies), ...r.sub_themes.flatMap((s) => s.companies)]) {
    if (c?.ticker && !seen.has(c.ticker)) seen.set(c.ticker, { name: c.name || c.ticker, cap: c.cap ?? null, base: !!c.base });
  }
  return seen;
}

/** A theme read is finished when its map and every company's check are in (the Themes page's own "still being prepared" test): a snapshot
 * of a read half done would list companies as added or removed that are only waiting for their check. */
export function themeReady(r: SectorAI): boolean {
  const pl = r.placements;
  if (r.ai?.state === "working" || r.ai?.state === "failed") return false;
  return !(pl && !pl.checked && (pl.pending > 0 || pl.industries_by === "pending"));
}

export function themeSnap(r: SectorAI): Snap {
  const cos = themeCompanies(r);
  const rows: Snap["rows"] = {};
  let total = 0, priced = 0, added = 0;
  for (const [t, c] of cos) {
    rows[t] = [c.name, c.cap];
    if (c.cap != null && Number.isFinite(c.cap)) { total += c.cap; priced++; }
    if (!c.base) added++;
  }
  return { rows, figures: { companies: cos.size, market_value: priced ? Math.round(total) : null, added } };
}

export interface FilingsOut { total: number; companies: number; items: { id: string; symbol: string; label: string }[] }
export function filingsSnap(out: FilingsOut): Snap {
  const rows: Snap["rows"] = {};
  for (const f of out.items ?? []) if (f?.id) rows[String(f.id)] = [`${f.symbol}: ${f.label}`, null];
  return { rows, figures: { filings: out.total ?? 0, companies: out.companies ?? 0 } };
}

/** An AI read's snapshot: when it was written (the read itself stays in the shared store). */
export const readSnap = (writtenSeconds: number | null | undefined): Snap => ({ rows: {}, figures: { written: writtenSeconds ?? null } });

const FIGURE_NAMES: Record<string, string> = {
  companies: "Companies", market_value: "Market value of the companies", added: "Companies added from other industries",
  filings: "Filings", written: "Read written",
};
export const figureName = (name: string) => FIGURE_NAMES[name] ?? name.replace(/_/g, " ");

/** A figure as the page writes it: money in the market's way, a written time as a date, counts as counts. */
export function figureText(name: string, v: number | null | undefined, region: string): string {
  if (v == null || !Number.isFinite(v)) return "–";
  if (name === "market_value") return amount(v, (region === "US" ? "US" : "IN") as Region);
  if (name === "written") return writtenAt(v, marketTz(region)) || "–";
  return Math.round(v).toLocaleString("en-IN");
}

/** "Last updated 6 Nov 2026": an AI read by when the read was written, a search by when it was last read. */
export function lastUpdated(item: Pick<SavedItem, "read_at" | "figures" | "params">): string {
  const w = item.figures?.written;
  if (w != null && Number.isFinite(w)) return asOf(new Date(w * 1000).toISOString().slice(0, 10)) ?? "–";
  return item.read_at ? asOf(item.read_at.slice(0, 10)) ?? "–" : "Not read yet";
}

/** What the saved item is for, in a few words: "India · India defence", "US · AAPL vs MSFT". */
export function savedWhat(item: Pick<SavedItem, "kind" | "params"> & { name?: string }): string {
  const p = item.params ?? {};
  const market = p.region === "US" ? "US" : "India";
  const bits = item.kind === "theme" ? [p.q] : item.kind === "compare" ? [`${p.a} vs ${p.b}`] : item.kind === "filings" ? [p.view === "mine" ? "Your stocks" : "Every company", p.flag ? p.flag.split(",").join(", ") : null, p.q] : [p.symbol];
  const same = (b: string | null | undefined) => !!item.name && String(b).toLowerCase() === item.name.toLowerCase();     // the name says it already
  return [market, ...bits.filter((b) => b && !same(b))].join(" · ");
}

/** One line for an update: "2 companies added, 1 removed; market value +20.4%" or "No change since the saved read". */
export function changeLine(c: Changes | null, kind: SavedKind): string {
  if (!c) return "Read kept. The next Update says what changed since this read.";
  if (c.same) return "No change since the saved read.";
  const noun = kind === "filings" ? ["filing", "filings"] : ["company", "companies"];
  const n = (k: number) => `${k} ${k === 1 ? noun[0] : noun[1]}`;
  const parts: string[] = [];
  if (c.added_count) parts.push(kind === "filings" ? `${n(c.added_count)} new` : `${n(c.added_count)} added`);
  if (c.removed_count) parts.push(kind === "filings" ? `${n(c.removed_count)} no longer in the list` : `${n(c.removed_count)} removed`);
  const w = c.figures.find((f) => f.name === "written");
  if (w && w.change) parts.push("the read was written again");
  const mv = c.figures.find((f) => f.name === "market_value");
  if (mv && mv.pct != null && mv.pct !== 0) parts.push(`market value ${mv.pct > 0 ? "+" : "−"}${Math.abs(mv.pct).toFixed(1)}%`);
  return parts.length ? parts.join("; ").replace(/^./, (s) => s.toUpperCase()) + "." : "Some figures moved since the saved read.";
}
