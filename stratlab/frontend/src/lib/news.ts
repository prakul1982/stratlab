/** The newsletters: market briefs for India and the US, and one on the user's own companies. */
import type { Region } from "./research";
import { fmtDate } from "./format";

export type NewsKind = "market" | "my_stocks";
export type Cadence = "daily" | "weekly" | "off";

export interface IssueRow {
  id: string; kind: NewsKind; region: Region | null; day: string; weekly: boolean; subject: string; preview: string;
}

export interface IssueLine { text: string; url?: string | null }
export interface IssueItem { text: string; url?: string | null; symbol?: string | null; region?: Region | null; lines?: IssueLine[];
  /** A weekly brief's headline: the day it ran ("Thu 22 Oct") */ day?: string | null;
  /** My stocks: the price, its move since the previous session and the "since …" label the email shows */ price?: number | null; currency?: string | null; change_pct?: number | null; since?: string | null }

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

/** The Briefs page's tabs: a region's Market Brief, or My stocks. */
export type NewsTab = "IN" | "US" | "mine";

/** The tab an issue is listed under, from its id (market.US.2026-10-08, my_stocks.<uid>.2026-10-09); null for another id. */
export function issueTab(id: string | null | undefined): NewsTab | null {
  const m = /^(market|my_stocks)\.([^.]+)\./.exec(String(id ?? ""));
  if (!m) return null;
  if (m[1] === "my_stocks") return "mine";
  return m[2] === "US" ? "US" : m[2] === "IN" ? "IN" : null;
}

/** The issue the reading pane shows for a tab: the one picked when it is this tab's, else (on a wide screen, where there is
 * room for both) the tab's latest, else none. `rows` is this tab's list, or null while it loads. R13-004: switching to
 * "Market brief: US" before the day's US issue existed kept India's brief open under the US tab, with no row highlighted. */
export function issueToShow(tab: NewsTab, rows: { id: string }[] | null, picked: string | null, wide: boolean): string | null {
  if (picked && issueTab(picked) === tab) return picked;
  if (!rows) return null;
  return wide && rows.length ? rows[0].id : null;
}

/** The stamp over an issue's numbers: a Market Brief's are the day's close ("the 16:00 ET close of 9 Oct 2026", R13-003),
 * My stocks' the moment it was built. */
/** The weekly issue is dated its Saturday; its numbers are the last weekday's close before it. */
export function closeDay(day: string, weekly?: boolean): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(day);
  if (!m || !weekly) return day;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  d.setDate(d.getDate() - ({ 6: 1, 0: 2 }[d.getDay()] ?? 0));
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function issueStamp(issue: { kind: NewsKind; region: Region | null; day: string; weekly?: boolean }, built: string | null): string | null {
  if (issue.kind === "market" && (issue.region === "US" || issue.region === "IN")) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(closeDay(issue.day, issue.weekly));
    if (m) {
      const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
      return `the ${issue.region === "US" ? "16:00 ET" : "15:30 IST"} close of ${d.getDate()} ${d.toLocaleDateString("en-GB", { month: "short" }).replace("Sept", "Sep")} ${d.getFullYear()}`;
    }
  }
  return built;
}

export const NEWS_FOOTER = "Facts from exchange filings, company documents and market data. Not investment advice.";
