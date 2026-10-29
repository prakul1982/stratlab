/* IPOs (Invest → IPOs): the types of the server's answers (ipo.py) and the calls the two pages make. The words and figures they
 * show are worked out in ipoText.ts (pure, so the unit tests can read it). */
import { api } from "./api";

export type Market = "IN" | "US";
/* "withdrawn" holds the issues the exchange names withdrawn, postponed or cancelled (issue_status says which) and "social" the Social
 * Stock Exchange fund raises, which are not IPOs: neither is a stage an issue passes through, so neither is a tab. */
export type Stage = "filed" | "upcoming" | "open" | "closed" | "listed" | "withdrawn" | "social";
export type IssueStatus = "withdrawn" | "postponed" | "cancelled";
export type EventKind = "open" | "close" | "allotment" | "listing";

export interface Perf { listing_price?: number; listing_change_pct?: number; latest?: number; change_pct?: number; latest_date?: string; at?: string }
export interface IpoRow {
  id: string; market: Market; segment?: "mainboard" | "sme"; name: string; symbol?: string; stage: Stage;
  open?: string; close?: string; close_time?: string; allotment?: string; allotment_expected?: boolean; listing?: string; listing_expected?: boolean;
  low?: number; high?: number; price?: number; lot?: number; min_amount?: number; min_basis?: string; size?: number; size_basis?: string;
  exchanges?: string[]; exchange?: string; expected?: string; priced?: string; filed?: string; shares?: number; currency: string;
  docs?: string[]; sub_times?: number; sub_as_of?: string; sub_read?: string; perf?: Perf;
  issue_status?: IssueStatus;
  /** A book-built issue with one part in rupees and one in shares: the parts, shown instead of a size until the price band gives a total. */
  size_parts?: { fresh_cr?: number; ofs_cr?: number; fresh?: number; ofs?: number };
}
export interface AlertPrefs { on: boolean; events: EventKind[]; markets: Market[]; sme: boolean; allowed: boolean; plan: string; channels: string[]; event_names: Record<EventKind, string> }
export interface IpoList {
  market: Market; as_of: string | null; bids_read?: string | null; problems_at?: string | null; tabs: Record<Stage, IpoRow[]>; counts: Record<Stage, number>; note: string; problems: string[]; prefs: AlertPrefs; today: string;
}
export interface SubRow { label: string; sr: string; offered: number | null; bid: number | null; times: number | null }
export interface Subscription { rows: SubRow[]; times: number | null; as_of: string | null; live?: boolean; read?: string }
export interface DocLink { kind: string; label: string; source: string; url: string; date: string | null; read: boolean }
export interface Financials { page: number; unit: string; years: string[]; rows: { key: string; label: string; values: (number | null)[] }[] }
/** The tables the rules read from an Indian offer document (ipo_docs.py): each with the page it is on. */
export interface Utilisation { page: number; unit: string; rows: { label: string; amount: number | null }[] }
export interface Risk { n: number; page: number; text: string }
export interface KpiPeriod { label: string; values: Record<string, number | null>; peers: Record<string, (number | null)[]> }
export interface Kpis { page: number; unit: string; peers: string[]; periods: KpiPeriod[] }
export interface Holder { group: string; name: string; shares: number | null; pct: number | null; post_pct: number | null; total: boolean }
export interface PeerRow { name: string; price: number | null; revenue: number | null; eps: number | null; nav: number | null; pe: number | null; ronw: number | null }
export interface PeerTable { page: number; price_on?: string; company: { revenue?: number | null; eps?: number | null; nav?: number | null; ronw?: number | null }; peers: PeerRow[] }
export interface Facts {
  state: "none" | "pending" | "ready"; kind?: string; read_at?: string; pages_read?: number;
  utilisation?: Utilisation; risks?: Risk[]; kpis?: Kpis; holding?: { page: number; rows: Holder[] }; peers?: PeerTable; eps?: { page: number; rows: { period: string; basic: number | null; diluted: number | null }[] };
  promoters?: string[]; selling?: { name: string; kind: string }[];
  objects?: { page: number; text: string; table?: { unit: string | null; rows: { label: string; figures: string | null }[] } }; financials?: Financials;
  us?: { company_shares?: number; selling_shares?: number; price?: number; range?: number[]; listing?: string; symbol?: string; proceeds?: string };
}
export interface Statement { text: string; quote: string }
export interface Summary {
  allowed: boolean; plan: string; state: "locked" | "none" | "pending" | "problem" | "ready"; kind?: string | null; at?: string; message?: string;
  items?: { business: Statement | null; segments: Statement[] };
}
export interface IpoDetail {
  ipo: IpoRow & {
    isin?: string; industry?: string; retail_max?: number; face_value?: number; fresh?: number; ofs?: number; fresh_cr?: number; ofs_cr?: number; size_shares?: number;
    issue_type?: string; hours?: string; credit?: string; credit_expected?: boolean; size_in_bids?: number; anchor_shares?: number; issue_text?: string; lead_managers?: string[]; registrar?: string; amount?: number; company_link?: string;
  };
  documents: DocLink[]; facts: Facts; summary: Summary; subscription: Subscription | null; perf: (Perf & { issue_price?: number; day_close?: number; day_change_pct?: number; listed?: string; basis?: string }) | null;
  note: string; prefs: AlertPrefs;
}

export const ipoApi = {
  list: (m: Market) => api<IpoList>(`/invest/ipos?market=${m}`),
  one: (id: string) => api<IpoDetail>(`/invest/ipos/${encodeURIComponent(id)}`),
  summary: (id: string) => api<{ facts: Facts; summary: Summary }>(`/invest/ipos/${encodeURIComponent(id)}/summary`, { method: "POST" }),
  saveAlerts: (p: { on: boolean; events: EventKind[]; markets: Market[]; sme: boolean }) => api<AlertPrefs>("/invest/ipos/alerts", { method: "PUT", body: p }),
};
