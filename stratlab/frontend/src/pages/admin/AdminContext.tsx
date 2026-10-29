import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { ServerBuild } from "../../lib/buildInfo";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import type { CalendarStatus } from "./HolidaysPanel";

export type Plan = "free" | "basic" | "pro";
export type AIRow = { label: string; configured: boolean; in_use: boolean; model: string | null; last_error: string | null; quota?: boolean; quick_rank?: number | null; research_rank?: number | null;
  /** whether it can answer now (a short rate limit still counts; a used-up free quota or a paused provider does not), and why
   * not in the provider's own words; how many of its models in use are paused; whether its free quota is used up */
  answering?: boolean | null; state_text?: string | null; paused_models?: number; quota_used?: boolean;
  /** what its last real result says (R7M-008): working, quota (free credit used up, or a card is needed), paused, failed,
   * untested (a key, nothing tried yet); null without a key. Older servers don't send it. */
  result?: "working" | "quota" | "paused" | "failed" | "untested" | null };
/** Which invoice seller details are still empty (R7M-001): `missing` names them; `gst` is whether invoices will carry GST. */
export type InvoiceSeller = { complete: boolean; missing: string[]; gst: boolean };
export type ServerError = { ref: string; at: string; method: string; path: string; error: string; where: string };

export interface Overview {
  server: {
    kite_ready: boolean; kite_token_day: string | null; kite_invalid?: string | null; feed_connected: boolean; live_sessions: number; india_sessions?: number; options_sessions?: number;
    /** how many people's options sessions those are (Admin counts every user's) */
    options_users?: number;
    auto_login: { at: string | null; ok: boolean | null; message: string; how?: string }; auto_login_configured: boolean;
    /** the next automatic data login (India time), when it is set up */
    auto_login_next?: string | null;
    recent_errors?: ServerError[];
    /** when this server started (India time, like each error's "at"), so errors kept from before it are told apart */
    server_started_at?: string | null;
    billing_enabled: boolean; billing_hook?: { mode: string; last_at: string | null }; ai: AIRow[]; research?: { finnhub: boolean }; promo_until?: string | null;
    calendar?: CalendarStatus; invoice_seller?: InvoiceSeller;
    rules_watch?: { failing: { name: string; fails: number; error: string | null }[]; pending: string[] };
    audit_mismatches?: Partial<Record<"IN" | "US", number>>;
    /** when the whole-market audit's mismatched rows were checked (DJ-026) */
    audit_checked?: Partial<Record<"IN" | "US", { oldest: string; newest: string }>>;
    admin_alerts?: { email_ready: boolean; via?: string | null; to: string[]; quota?: BrevoQuota | null };
    /** while Indian data is offline: whether India is shut today anyway, and when the data login runs (DJ-003) */
    data_note?: { closed: "weekend" | "holiday" | null; back_at: string | null } | null;
    /** which build the server is (R24-009; older servers don't send it) */
    build?: ServerBuild;
    option_recorder?: { enabled: boolean; targets: string[]; every_minutes: number; today: number; day: string | null; last_at: string | null; last_error: string | null };
  };
  stats: { users: number; plans: Record<Plan, number>; new_7d: number; signups_today: number; experiments_month: number; ai_month: number; ai_reads_month?: number;
    /** paid plans with a subscription behind them, and those the owner gave by hand (older servers send neither) */
    paying?: Record<"basic" | "pro", number>; given?: Record<"basic" | "pro", number>;
    /** people who pressed "Tell me when plans open" (older servers don't send it) */
    plan_interest?: number;
    /** the test accounts left out of every count above, unless shown (DJ-001) */
    test_accounts?: number;
    /** the invoices of the last 30 days, by currency (DJ-004) */
    revenue_30d?: { days: number; count: number; by_currency: Record<string, number> } | null;
    /** people who signed in or ran something in the last 7 days (DJ-004) */
    active_7d?: number | null };
}

/** Brevo's own figures for today (DJ-034): sends made, and what the plan has left of its daily limit. */
export type BrevoQuota = { sent_today: number | null; left_today: number | null; plan: string | null; limit_kind: string | null; error: string | null; dashboard: string };

export type JobRow = {
  id: string; name: string; schedule: string; /** the next time the schedule names, "Thu 29 Oct, 7:15 AM IST"; null when it is "every so often" */ next?: string | null; last_run: string | null; error: string | null; state: "ok" | "warn" | "bad"; running: boolean;
  log: string[]; run: { label: string; path: string }[]; note: string | null;
};
export type ReportedRow = {
  id: string; name: string; author: string; email: string | null; description: string; reports: number;
  reasons: Record<string, number>; hidden: boolean; hidden_by: string | null; published_at: string;
};
export type Reported = { entries: ReportedRow[]; reasons: Record<string, string> };

type Ctx = {
  ov: Overview | null; setOv: (f: (o: Overview | null) => Overview | null) => void;
  /** whether the test accounts are counted and listed (DJ-001), and the switch */
  showTest: boolean; setShowTest: (on: boolean) => void;
  jobs: JobRow[] | null; reported: Reported | null; loading: boolean;
  reload: () => Promise<void>; reloadJobs: () => Promise<void>;
};
const AdminCtx = createContext<Ctx | null>(null);

/** What every Admin section reads: the server's status, the job list and what users reported. Loaded once for the area,
 * and again when a section changes something (or Refresh is pressed). */
export function AdminData({ children }: { children: ReactNode }) {
  const { fail } = useApp();
  const [ov, setOvState] = useState<Overview | null>(null);
  const [jobs, setJobs] = useState<JobRow[] | null>(null);
  const [reported, setReported] = useState<Reported | null>(null);
  const [loading, setLoading] = useState(true);
  const [showTest, setShowTestState] = useState(() => { try { return localStorage.getItem("admin-show-test") === "1"; } catch { return false; } });
  const setShowTest = useCallback((on: boolean) => {
    setShowTestState(on);
    try { localStorage.setItem("admin-show-test", on ? "1" : "0"); } catch { /* remembered for this visit only */ }
  }, []);
  const reloadJobs = useCallback(async () => {
    try { setJobs((await api<{ jobs: JobRow[] }>("/admin/jobs")).jobs); } catch (e) { fail(e); }
  }, [fail]);
  const load = useCallback(async (fresh: boolean) => {
    setLoading(true);
    // the three reads at once, each shown as it arrives: one after another made a cold Admin 7 s (R8O-007). The server
    // keeps Overview's counts 45 s; Refresh and a change made from a section read them again (fresh)
    const ovDone = api<Overview>(overviewPath(fresh, showTest)).then(setOvState).catch(fail);
    const libDone = api<Reported>("/admin/library").then(setReported).catch(fail);
    try { await Promise.all([ovDone, libDone, reloadJobs()]); } finally { setLoading(false); }
  }, [fail, reloadJobs, showTest]);
  const reload = useCallback(() => load(true), [load]);
  useEffect(() => { load(false); }, [load]);
  const value = useMemo<Ctx>(() => ({ ov, setOv: (f) => setOvState((o) => f(o)), showTest, setShowTest, jobs, reported, loading, reload, reloadJobs }),
    [ov, showTest, setShowTest, jobs, reported, loading, reload, reloadJobs]);
  return <AdminCtx.Provider value={value}>{children}</AdminCtx.Provider>;
}

/** Overview's address: read again (`fresh`), and with the test accounts counted (DJ-001). */
export function overviewPath(fresh: boolean, test: boolean): string {
  const q = [fresh && "fresh=1", test && "test=1"].filter(Boolean).join("&");
  return `/admin/overview${q ? `?${q}` : ""}`;
}

export function useAdmin(): Ctx {
  const c = useContext(AdminCtx);
  if (!c) throw new Error("useAdmin outside Admin");
  return c;
}

/** The sections of Admin, in menu order. `tabs` are the old ?tab= names that now open each one. */
export const SECTIONS: { path: string; label: string; title: string; lede: string; tabs: string[] }[] = [
  { path: "", label: "Overview", title: "Overview", tabs: ["overview"], lede: "What needs you, how every service and data feed is doing, and today's numbers." },
  { path: "users", label: "Users and growth", title: "Users and growth", tabs: ["users"], lede: "Who is on StratLab, their plans, invite rewards and the launch offer." },
  { path: "money", label: "Money", title: "Money", tabs: ["billing"], lede: "Payments, prices outside India and invoices." },
  { path: "data", label: "Data and jobs", title: "Data and jobs", tabs: ["checks"], lede: "Every background job: when it last ran, when it runs next, and a button to run it now." },
  { path: "quality", label: "Quality", title: "Quality", tabs: [], lede: "Audits of the company data, strategies users reported, and the rates and rules StratLab uses." },
  { path: "system", label: "System", title: "System", tabs: ["services"], lede: "Server errors, other services, AI providers, platform checks and real prices for testing." },
  { path: "emails", label: "Email previews", title: "Email previews", tabs: [], lede: "Every email StratLab sends, as a reader gets it. The market briefs are the newest real issues; the rest use made-up details. Nothing here is sent." },
];
