// A company's peers, statements and shareholding by quarter (lane c-f2): the shapes the server sends (backend/app/company_tables.py) and the
// pure helpers the three sections use, kept here so unit/company-tables.test.mjs can check them without a browser. Facts only.
import { bigMoney, CRORE, grouped, num, pctPlain } from "./format";

export type Region = "IN" | "US";
export interface Lock { plan: "basic" | "pro"; message: string }

export interface PeerRow {
  symbol: string; name: string; own: boolean;
  market_cap: number | null; sales_growth: number | null; ebitda: number | null; net: number | null; ret: number | null; pe: number | null;
}
export type PeerKey = "market_cap" | "sales_growth" | "ebitda" | "net" | "ret" | "pe";
export const PEER_KEYS: PeerKey[] = ["market_cap", "sales_growth", "ebitda", "net", "ret", "pe"];
export interface Peers {
  symbol: string; region: Region; basis: "industry" | "sector" | "none"; basis_words: string; lender: boolean;
  return_label: "ROE" | "ROCE"; unit: string; own: PeerRow | null; rows: PeerRow[]; total: number;
  median: (Record<PeerKey, number | null> & Record<string, number | null>) | null;
  can_sort: boolean; can_export: boolean; as_of: string | null; locked: Lock | null; export_locked: Lock | null;
}

export type Kind = "money" | "pct" | "days" | "per_share" | "count" | "ratio";
export interface StatementRow { label: string; kind: Kind; values: (number | null)[]; worked?: boolean }
export interface Section { key: "pl" | "balance" | "cashflow" | "ratios_table"; title: string; rows: StatementRow[] }
export interface Statements {
  symbol: string; region: Region; name: string; unit: string; currency: string; basis: string; bases: string[]; basis_note: string | null;
  lender: boolean; years_stored: number; cols: string[]; sections: Section[];
  quarters: { cols: string[]; rows: StatementRow[] } | null;
  full: boolean; can_export: boolean; locked: Lock | null; export_locked: Lock | null; notes: string[]; numbers_at: string | null;
  hidden?: { years: number; sections: string[]; quarters: number };
}

export type HolderKey = "promoters" | "fiis" | "diis" | "government" | "public" | "others";
export interface HoldingQuarter extends Partial<Record<HolderKey, number | null>> { quarter: string; shareholders: number | null; pledge: number | null }
export interface Shareholding {
  symbol: string; region: Region; available: boolean; note?: string; keys?: HolderKey[]; quarters: HoldingQuarter[]; stored?: number;
  full: boolean; chart?: boolean; pledge_note?: string; locked: Lock | null; numbers_at?: string | null;
}

/** A market value as the index keeps it (₹ crore in India, $ million in the US) in the units people say: ₹1.51 lakh cr, $412.3B. */
export function capText(v: number | null | undefined, region: Region): string {
  if (v == null || !Number.isFinite(v)) return "–";
  return region === "IN" ? bigMoney(v * CRORE, "INR") : bigMoney(v * 1e6, "USD");
}

/** A P/E: one decimal and the times sign; "–" for none. */
export function peText(v: number | null | undefined): string {
  return v == null || !Number.isFinite(v) ? "–" : `${num(v, 1)}×`;
}

/** A statement figure as its row is written: money in the table's unit grouped as its market writes it, a percentage, days, per share. */
export function cellText(v: number | null | undefined, kind: Kind, region: Region): string {
  if (v == null || !Number.isFinite(v)) return "–";
  switch (kind) {
    case "pct": return pctPlain(v, 1).replace("-", "−");
    case "days": return grouped(v, 0, region);
    case "per_share": return num(v, 2);
    case "ratio": return num(v, 2);
    case "count": return grouped(v, 0, region);
    default: return grouped(v, Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0, region);
  }
}

/** Rows sorted by a column, nulls last whichever way; equal figures keep their order (nearest in market value first). */
export function sortPeers(rows: PeerRow[], key: PeerKey, desc: boolean): PeerRow[] {
  return rows.map((r, i) => ({ r, i })).sort((a, b) => {
    const x = a.r[key], y = b.r[key];
    if (x == null && y == null) return a.i - b.i;
    if (x == null) return 1;
    if (y == null) return -1;
    return x === y ? a.i - b.i : desc ? y - x : x - y;
  }).map((x) => x.r);
}

export const HOLDER_NAME: Record<HolderKey, string> = {
  promoters: "Promoters", fiis: "FIIs", diis: "DIIs", government: "Government", public: "Public", others: "Others",
};

/** Each quarter's stacked bar: its segments bottom up ({key, from, to} in percent of the bar), in the order of `keys`; a quarter's
 * shares are drawn as filed, so a filing whose parts add up to 99.98% leaves that sliver empty, never stretched. */
export function stacks(quarters: HoldingQuarter[], keys: HolderKey[]): { quarter: string; parts: { key: HolderKey; from: number; to: number }[] }[] {
  return quarters.map((q) => {
    let at = 0;
    const parts = [];
    for (const k of keys) {
      const v = q[k];
      if (v == null || !Number.isFinite(v) || v <= 0) continue;
      const to = Math.min(100, at + v);
      parts.push({ key: k, from: at, to });
      at = to;
    }
    return { quarter: q.quarter, parts };
  });
}

/** The change in a holder group's share from the first quarter shown to the last, in points; null with fewer than two figures. */
export function changeOver(quarters: HoldingQuarter[], key: HolderKey): number | null {
  const got = quarters.map((q) => q[key]).filter((v): v is number => v != null && Number.isFinite(v));
  return got.length >= 2 ? Math.round((got[got.length - 1] - got[0]) * 100) / 100 : null;
}

/** "Mar 2026" → "FY26" for an Indian year that ends in March; any other column stays as it is. */
export function yearLabel(col: string, region: Region): string {
  const m = /^Mar (\d{4})$/.exec(col);
  return region === "IN" && m ? `FY${m[1].slice(2)}` : col;
}

/** The address of a company's table download. */
export function downloadPath(region: Region, symbol: string, what: "peers.csv" | "statements.xlsx" | "statements.csv", basis?: string): string {
  return `/research/company/${region}/${encodeURIComponent(symbol)}/${what}${basis ? `?basis=${encodeURIComponent(basis)}` : ""}`;
}
