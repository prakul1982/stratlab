import { api } from "./api";
import type { Region } from "./research";

/* The theme deep dive (THEME-1): every figure is from the app's stored company facts, the AI writes none of them. These are the shapes the
 * server sends (backend/app/intel/theme_data.py, theme_prices.py, theme_routes.py) and the few plain helpers the tables share. */

export interface Stat { n: number; median: number; min: number; max: number }
export interface YearRow { year: string; sales: number | null; profit: number | null; opm: number | null }
export interface DiveRow {
  symbol: string; name: string; year: string | null; unit: string | null; bank: boolean; revenue: number | null; profit: number | null;
  ebitda: number | null; net: number | null; roce: number | null; cap: number | null; pe: number | null; debt_equity: number | null;
  sales_1y: number | null; sales_3y: number | null; profit_1y: number | null; stage: number | null; from_high: number | null;
  pb: number | null; interest_cover: number | null; ev_ebitda: number | null; quarter: { of: string; sales: number | null; profit: number | null } | null;
  what?: string | null; company_wide?: boolean; years?: YearRow[];
  /** the margins beyond ±100% of revenue, printed "n.m." on every surface (R64 theme_data.company_row, LIVE11A-008) */
  nm?: ("ebitda" | "net")[];
  /** 0 when its EBITDA margin is filed in whole points (LIVE7A-009: printed 12%, not 12.0%) */
  ebitda_dp?: number;
  /** its place in its layer's calculations, kept by the server (theme_data.calc_record; LIVE6-001: the page says what the deck says) */
  calc?: { in: boolean; why: string; kind?: string; detail?: string } | null; one_off?: boolean;
}
export interface BizRow {
  symbol: string; name: string; metric: string; unit: string | null; span: "month" | "quarter"; period: string; value: number; prev: number | null; year_ago: number | null;
  change_prev: number | null; change_year: number | null; filed: string; url: string | null; page: number | null; exchange: string | null;
  points: { period: string; value: number }[];
}
export interface History { years: string[]; ebitda: (number | null)[]; net: (number | null)[]; n: number; companies: string[] }
export interface Layer {
  layer: string; description: string; companies: DiveRow[]; n: number; revenue: number | null; line: string | null; history: History | null;
  stats: { ebitda: Stat | null; net: Stat | null; roce: Stat | null }; company_wide: string[]; left_out: number; stats_over: "own" | "all";
  /** every company the layer lists; `n` of them are in its calculations */
  listed?: number;
  /** e79: how many companies the theme's map places in the layer (a layer with members but none among those with figures) */
  placed?: number;
  /** one official industry's companies the AI didn't place in a layer (THEMES) */
  official?: boolean; basis?: "industry" | "list";
  /** the layer's EBITDA margins are mostly filed in whole points: its median and range print whole (LIVE7A-009) */
  ebitda_whole?: boolean;
}
export interface ChainRow { layer: string; n: number; listed?: number; revenue: number | null; ebitda: number | null; net: number | null; roce: number | null; ebitda_n: number; net_n?: number; roce_n?: number }
export interface SubCompany { symbol: string; name: string; what: string | null; cap: number | null; sales_1y: number | null; ebitda: number | null; ebitda_dp?: number; company_wide: boolean; year: string | null; nm?: ("ebitda" | "net")[] }
export interface Holding { symbol: string; name: string; quarter: string; promoter: number | null; institutions: number | null; promoter_change: number | null; institutions_change: number | null }
export interface Flag { symbol: string; name: string; at: string; label: string; severity?: string; subject?: string; url?: string | null }
export interface Dive {
  region: Region; sector: string; as_of: string | null; /** how many companies are at an earlier close than `as_of` (LIVE7A-003) */ as_of_older?: number; unit: string | null; basis: string; members: number; company_wide: string[];
  /** the theme's EBITDA margins are mostly filed in whole points: its medians print whole (LIVE7A-009) */
  ebitda_whole?: boolean;
  /** a kept dive served while the newer one is read behind the page (LIVE10A-008) */
  updating?: boolean;
  layers: Layer[]; chain: { rows: ChainRow[]; line: string | null; highest: string | null; lowest: string | null };
  subs: { name: string; detail: string; companies: SubCompany[] }[];
  placements?: { checked: boolean; pending: number; left_out: number; placed: number; unconfirmed?: number } | null;
  /** the figures are worked out on `shown` of the theme's `of` companies: every one the AI named, then the largest of the rest */
  figures?: { shown: number; of: number };
  notable: { kind: "gap" | "move" }[];
  /** e54: what each checked company's place in the theme rests on (theme_data.EVIDENCE_STATES), the figures' window... */
  evidence?: Record<string, EvidenceState>;
  membership?: { placed: number; confirmed: number; not_confirmed: number };
  /** the members in the theme with figures (every median and total is of these): a count apart from the membership check's */
  with_figures?: number;
  membership_evidence?: Partial<Record<EvidenceState, number>>;
  /** ...and the companies the membership check reached beyond it, with its progress after each stored read ([day, checked, total]) */
  membership_check?: { outside: Record<string, EvidenceState>; checked: number; total: number; history: [string, number, number][]; step?: number };
  sections: {
    size: { companies: number; with_value: number; total_cap: number | null; biggest: { symbol: string; name: string; cap: number; share: number }[]; top3_share: number | null };
    medians: Record<"ebitda" | "net" | "roce", Stat | null>;
    growth: { aggregate: Record<string, { value: number; n: number; year: string }>; median: Record<string, Stat> };
    margins: History | null;
    valuation: { pe: Stat | null; market_pe: Stat | null; market_n: number; pb: Stat | null; market_pb: Stat | null; ev_ebitda: Stat | null; ev_missing: number; history: { d: string; pe: number; n: number }[] };
    quarter: { companies: { symbol: string; name: string; of: string; sales: number | null; profit: number | null }[]; sales_up: number; sales_down: number; profit_up: number; profit_down: number; sales: Stat | null; profit: Stat | null };
    balance: { debt_equity: Stat | null; above_1: number; with_debt_equity: number; cfo_to_profit: Stat | null; cfo_n: number; interest_cover: Stat | null; cover_under_2: number };
    price: Record<"stage2" | "supertrend_up" | "near_high" | "near_low", { n: number; count: number; share: number | null }>;
    market: Record<string, Stat | null>;
    ownership: { holdings: Holding[]; promoter_up: number; promoter_down: number; promoter_median: Stat | null; insider_buys: { symbol: string; name: string; at: string }[]; pledges: Flag[]; red_flags: Flag[] };
    events: { results_due: { symbol: string; name: string; date: string; purpose: string | null }[];
      results_filed: { symbol: string; name: string; date: string; numbers: { label: string; value: string }[]; url: string | null }[];
      actions: { symbol: string; name: string; date: string; kind: string; label: string; text: string }[] };
    management: { companies: { symbol: string; name: string; met: number; missed: number }[]; met: number; missed: number; with_card: number };
    leaders: DiveRow[];
  };
}
/** e54: the evidence a company's place in a theme rests on, one state each (theme_data.EVIDENCE_STATES) */
export type EvidenceState = "description_verified" | "industry_code_supported" | "list_supported" | "not_confirmed" | "membership_unverified";
/** l55 (R55, the owner's review of the live R54 decks): the states by the deck's names, never one "confirmed" total */
export const EVIDENCE_ONE: Record<EvidenceState, string> = {
  description_verified: "Description-verified", industry_code_supported: "Industry-supported (official industry only)",
  list_supported: "List-supported (the theme's own list only)", not_confirmed: "Own words describe other work", membership_unverified: "Not checked",
};
const EVIDENCE_MANY: [EvidenceState, string][] = [["description_verified", "description-verified"],
  ["industry_code_supported", "industry-supported"], ["list_supported", "list-supported"],
  ["not_confirmed", "own words describe other work"], ["membership_unverified", "not checked"]];
/** said even at 0: the three states every count names */
const EVIDENCE_ALWAYS: EvidenceState[] = ["description_verified", "industry_code_supported", "membership_unverified"];

/** e54: each company's evidence state from the dive (its figures' window, then those the membership check reached), "membership_unverified"
 * for a company neither has; undefined for a dive kept before the states were. */
export function evidenceOf(dive: Dive | null | undefined): ((sym: string) => EvidenceState) | undefined {
  if (!dive?.evidence) return undefined;
  const inner = dive.evidence, outer = dive.membership_check?.outside ?? {};
  return (sym) => inner[sym] ?? outer[sym] ?? "membership_unverified";
}

/** e54/l55: "82 description-verified · 78 industry-supported · 62 not checked" over the companies listed (the same states and counts as
 * the deck's universe line, the three always named); "" with no states kept. */
export function evidenceLine(dive: Dive | null | undefined, symbols: string[]): string {
  const n = evidenceCounts(dive, symbols);
  if (!n) return "";
  return EVIDENCE_MANY.filter(([k]) => n.get(k) || EVIDENCE_ALWAYS.includes(k)).map(([k, w]) => `${(n.get(k) ?? 0).toLocaleString("en-IN")} ${w}`).join(" · ");
}

/** l55: each state's count over the companies listed, each company once; undefined with no states kept. */
export function evidenceCounts(dive: Dive | null | undefined, symbols: string[]): Map<EvidenceState, number> | undefined {
  const of = evidenceOf(dive);
  if (!of) return undefined;
  const n = new Map<EvidenceState, number>();
  for (const s of new Set(symbols)) n.set(of(s), (n.get(of(s)) ?? 0) + 1);
  return n;
}

/** l55 (R55): "Membership checked 160 of 211: 97 description-verified · 63 industry-supported · 51 not checked", the membership check's
 * count apart from the count with figures (the check reads no figure); "" with no states kept. */
export function membershipLine(dive: Dive | null | undefined, symbols: string[]): string {
  // r69e (LIVE13A-002): the dive's one tally (the deck's and the public page's), when the dive keeps it; else counted over the companies listed
  const t = (dive as { tally?: Record<string, number> | null } | null | undefined)?.tally;
  const n = t && t.total ? new Map<EvidenceState, number>(EVIDENCE_MANY.map(([k]) => [k, Number(t[k] ?? 0)])) : evidenceCounts(dive, symbols);
  if (!n) return "";
  const all = t && t.total ? Number(t.total) : new Set(symbols).size, none = n.get("membership_unverified") ?? 0, checked = all - none;
  // r69e (LIVE13A-002: "Membership checked 101 of 103: 93 description-verified · 8 industry-supported · 2 not checked", 93 + 8 + 2 = 103):
  // the states after the colon add up to the companies checked; the ones not checked are said after them
  const states = EVIDENCE_MANY.filter(([k]) => k !== "membership_unverified" && (n.get(k) || EVIDENCE_ALWAYS.includes(k)))
    .map(([k, w]) => `${(n.get(k) ?? 0).toLocaleString("en-IN")} ${w}`).join(" · ");
  return `Membership checked ${checked.toLocaleString("en-IN")} of ${all.toLocaleString("en-IN")}: ${states}; ${none.toLocaleString("en-IN")} not checked`;
}

export interface PriceRow { symbol: string; name: string; ret: Record<"1M" | "3M" | "1Y" | "3Y", number | null>; date: string; above200: boolean | null; near_high: boolean | null; near_low: boolean | null }
export interface Prices {
  companies: PriceRow[]; median: Record<string, { median: number; n: number } | null>; pending: number;
  /** companies with no price shown at all; the rest of `pending` are shown from their stored daily row until their candles are read (LIVE7A-002) */
  missing?: number; benchmark: string; as_of: string | null;
  above200: { n: number; count: number; share: number | null }; near_high: { n: number; count: number; share: number | null }; near_low: { n: number; count: number; share: number | null };
  line: { weeks: string[]; theme: number[]; bench: number[]; rs: number[] } | null;
  returns: Record<string, { theme: number | null; bench: number | null }> | null;
  /** the last close the theme's and the index's period changes run to (LIVE6-002) */
  returns_to?: string | null;
}
export interface NewsRow { at: string; headline: string; company: string | null; symbol: string | null; source: string; url: string; kind: "news" | "filing" }
export interface Listing { id: string; name: string; symbol: string | null; stage: string; industry: string | null; open: string | null; close: string | null; listing: string | null; groups: string[]; what: string }
export interface Business { allowed: boolean; layers: { layer: string; rows: BizRow[] }[]; subs: { name: string; rows: BizRow[] }[]; companies: number; of: number }

const q = (r: Region, theme: string) => `region=${r}&q=${encodeURIComponent(theme)}`;
export type LibraryTheme = { name: string; q: string; region: Region; at: string | null; day?: string | null; members: number | null; searched: number };

export const themeApi = {
  dive: (r: Region, theme: string, refresh = false) => api<Dive>(`/research/theme-dive?${q(r, theme)}${refresh ? "&refresh=true" : ""}`),
  prices: (r: Region, theme: string) => api<Prices>(`/research/theme-dive/prices?${q(r, theme)}`),
  news: (r: Region, theme: string) => api<{ items: NewsRow[]; as_of: string }>(`/research/theme-dive/news?${q(r, theme)}`),
  listings: (r: Region, theme: string) => api<{ items: Listing[]; checked: boolean; pending?: boolean }>(`/research/theme-dive/listings?${q(r, theme)}`),
  business: (r: Region, theme: string) => api<Business>(`/research/theme-dive/business?${q(r, theme)}`),
  /** EXPORT: the theme's deck, PowerPoint or PDF (counted against the plan's monthly decks, as a company's deck is) */
  deck: (r: Region, theme: string, format: "pptx" | "pdf") => api<Response>(`/research/theme-dive/deck?${q(r, theme)}&format=${format}`, { raw: true }),
  /** Themes StratLab has mapped and kept once for everyone that match what's typed (R19; the search box's shared "Ready to open" list). */
  suggest: (r: Region, typed: string) => api<{ items: LibraryTheme[] }>(`/research/theme-library/suggest?${q(r, typed)}`),
  draft: (r: Region, theme: string) => api<{ result: string; slug: string | null; problem?: string }>("/admin/blog/theme", { method: "POST", body: { q: theme, region: r } }),
};


export { amount, pc, pcw, times, points, span, layerLines, medCell, calcOf, calcWords, CALC_WORDS, MIN_BASE, NO_WORDS, NOT_QUOTED, noWords, olderNote, mapStamp, DIVE_UPDATING, unquotedLine, ownWords, libraryLabel, shortTheme, LIBRARY_HEAD, bizFor, plainIndustry, type LayerLine } from "./themeFormat";
