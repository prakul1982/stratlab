/** The newsletters: market briefs for India and the US, and one on the user's own companies. */
import type { Region } from "./research";
import { fmtDate } from "./format";

export type NewsKind = "market" | "my_stocks";
export type Cadence = "daily" | "weekly" | "off";

export interface IssueRow {
  id: string; kind: NewsKind; region: Region | null; day: string; weekly: boolean; subject: string; preview: string;
}

export interface IssueLine { text: string; url?: string | null }
export interface IssueItem { text: string; url?: string | null; symbol?: string | null; region?: Region | null; lines?: IssueLine[] }

export interface Issue {
  id: string; kind: NewsKind; region: Region | null; day: string; weekly: boolean; subject: string;
  summary: string | null; /** the AI's words, under the facts line (R8B-007) */ ai_summary?: string | null; sections: { title: string; items: IssueItem[] }[]; html: string; at: string;
}

export interface NewsletterPrefs {
  market_in: Cadence; market_us: Cadence; my_stocks: Cadence;
  email: string | null; confirmed: boolean; allowed: { market_daily: boolean; my_stocks: boolean; my_stocks_daily?: boolean };
}

/** "2026-10-02" as a date in words, read as a calendar day (not midnight UTC, which is the day before in the Americas). */
export function dayName(day: string, long = false): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (!m) return day;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return long ? d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }) : fmtDate(d, { weekday: true });
}

export const NEWS_FOOTER = "Facts from exchange filings, company documents and market data. Not investment advice.";
