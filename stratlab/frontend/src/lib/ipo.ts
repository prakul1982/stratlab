/* IPOs (Invest → IPOs): the types of the server's answers (ipo.py) and the calls the two pages make. The words and figures they
 * show are worked out in ipoText.ts (pure, so the unit tests can read it). */
import { api } from "./api";

export type Market = "IN" | "US";
export type Stage = "filed" | "upcoming" | "open" | "closed" | "listed";
export type EventKind = "open" | "close" | "allotment" | "listing";

export interface Perf { listing_price?: number; listing_change_pct?: number; latest?: number; change_pct?: number; latest_date?: string; at?: string }
export interface IpoRow {
  id: string; market: Market; segment?: "mainboard" | "sme"; name: string; symbol?: string; stage: Stage;
  open?: string; close?: string; allotment?: string; allotment_expected?: boolean; listing?: string; listing_expected?: boolean;
  low?: number; high?: number; price?: number; lot?: number; min_amount?: number; min_basis?: string; size?: number; size_basis?: string;
  exchanges?: string[]; exchange?: string; expected?: string; priced?: string; filed?: string; shares?: number; currency: string;
  docs?: string[]; sub_times?: number; sub_as_of?: string; perf?: Perf;
}
export interface AlertPrefs { on: boolean; events: EventKind[]; markets: Market[]; sme: boolean; allowed: boolean; plan: string; channels: string[]; event_names: Record<EventKind, string> }
export interface IpoList {
  market: Market; as_of: string | null; tabs: Record<Stage, IpoRow[]>; counts: Record<Stage, number>; note: string; problems: string[]; prefs: AlertPrefs; today: string;
}
export interface SubRow { label: string; sr: string; offered: number | null; bid: number | null; times: number | null }
export interface Subscription { rows: SubRow[]; times: number | null; as_of: string | null; live?: boolean; read?: string }
export interface DocLink { kind: string; label: string; source: string; url: string; date: string | null; read: boolean }
export interface Financials { page: number; unit: string; years: string[]; rows: { key: string; label: string; values: (number | null)[] }[] }
export interface Facts {
  state: "none" | "pending" | "ready"; kind?: string; read_at?: string; pages_read?: number;
  promoters?: string[]; selling?: { name: string; kind: string }[]; objects?: { page: number; text: string }; financials?: Financials;
  us?: { company_shares?: number; selling_shares?: number; price?: number; range?: number[]; listing?: string; symbol?: string; proceeds?: string };
}
export interface Statement { text: string; quote: string }
export interface Summary {
  allowed: boolean; plan: string; state: "locked" | "none" | "pending" | "problem" | "ready"; kind?: string | null; at?: string; message?: string;
  items?: { business: Statement | null; financials: Statement[]; objects: Statement[]; risks: Statement[]; promoters: Statement[] };
}
export interface IpoDetail {
  ipo: IpoRow & {
    isin?: string; industry?: string; retail_max?: number; face_value?: number; fresh?: number; ofs?: number; fresh_cr?: number; ofs_cr?: number; size_shares?: number;
    issue_type?: string; issue_text?: string; lead_managers?: string[]; registrar?: string; amount?: number; company_link?: string;
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
