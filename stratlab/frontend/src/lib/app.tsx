import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Session } from "@supabase/auth-js";
import { api, ApiError, setApiHandlers, supabase } from "./api";
import type { Focus, Level, Market, Me, NotebookItem } from "./types";
import { takeRef } from "./share";
import { identify, resetAnalytics, track, trackSignup } from "./analytics";

type Toast = { msg: string; action?: { label: string; run: () => void } } | null;

interface AppState {
  session: Session | null;
  ready: boolean;
  me: Me | null;
  meError: string | null;
  notebooks: NotebookItem[] | null;
  markets: Market[];
  dataOffline: boolean;
  toast: Toast;
  notify: (msg: string, action?: { label: string; run: () => void }) => void;
  fail: (e: unknown) => void;
  refreshMe: () => Promise<void>;
  refreshNotebooks: () => Promise<void>;
  /** every indicator beyond price, SMA, EMA and RSI (Basic and up) */
  allIndicators: boolean;
  /** Indian futures and options (Pro) */
  fno: boolean;
  level: Level | null;
  setLevel: (l: Level) => Promise<void>;
  /** What the user came for. Orders the menu, the home page and the examples; never hides anything. */
  focus: Focus | null;
  setFocus: (f: Focus) => Promise<void>;
  theme: "light" | "dark" | "system";
  setTheme: (t: "light" | "dark" | "system") => void;
}

const Ctx = createContext<AppState | null>(null);
export const useApp = () => useContext(Ctx)!;

export function AppProvider({ children, goToPlans }: { children: ReactNode; goToPlans: () => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [notebooks, setNotebooks] = useState<NotebookItem[] | null>(null);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [dataOffline, setDataOffline] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const timer = useRef<number>(undefined);
  const [theme, setThemeState] = useState<"light" | "dark" | "system">(() => {
    try { return (localStorage.getItem("stratlab-theme") as "light" | "dark") || "system"; } catch { return "system"; }
  });

  const notify = useCallback((msg: string, action?: { label: string; run: () => void }) => {
    setToast({ msg, action });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), action ? 9000 : 4500);
  }, []);

  // goToPlans changes with every page change; read it through a ref so `fail` stays the same function and
  // pages that load data with it don't load again each time the address changes
  const plans = useRef(goToPlans);
  plans.current = goToPlans;
  const fail = useCallback((e: unknown) => {
    const err = e as ApiError;
    if (err?.status === 402) notify(err.message, { label: "See plans", run: () => { track("upgrade clicked", { source: "limit" }); plans.current(); } });
    else notify(err?.message || "Something went wrong. Try again.");
  }, [notify]);

  const refreshMe = useCallback(async () => {
    try {
      const m = await api<Me>("/me");
      setMe(m);
      setMeError(null);
      setDataOffline(!m.data_online);
    } catch (e) {
      setMeError((e as Error).message);
    }
  }, []);

  const refreshNotebooks = useCallback(async () => {
    try { setNotebooks(await api<NotebookItem[]>("/notebooks")); } catch (e) { setNotebooks((n) => n ?? []); fail(e); }
  }, [fail]);

  useEffect(() => {
    setApiHandlers({
      unauthorized: () => { supabase.auth.signOut(); },
      offline: () => setDataOffline(true),
    });
    supabase.auth.getSession().then(({ data }) => { setSession(data.session); setReady(true); });
    const { data } = supabase.auth.onAuthStateChange((_e, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    if (!session) { setMe(null); setNotebooks(null); resetAnalytics(); return; }
    const ref = takeRef();          // arrived by a friend's invite link: say so once (the server counts new accounts only)
    if (ref) api("/me/referral", { method: "POST", body: { code: ref } }).catch(() => undefined);
    refreshMe();
    refreshNotebooks();
    api<Market[]>("/markets").then(setMarkets).catch(() => {});
  }, [session?.user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // usage analytics: this account by its id only, with its plan (does nothing without a key)
  useEffect(() => {
    if (!me?.id || !session) return;
    identify(me.id, { plan: me.plan, backtests: me.usage?.backtests_used, createdAt: session.user?.created_at });
    trackSignup(me.id, session.user?.created_at);
  }, [me?.id, me?.plan]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTheme = useCallback((t: "light" | "dark" | "system") => {
    setThemeState(t);
    try {
      if (t === "system") { localStorage.removeItem("stratlab-theme"); delete document.documentElement.dataset.theme; }
      else { localStorage.setItem("stratlab-theme", t); document.documentElement.dataset.theme = t; }
    } catch { /* private mode */ }
  }, []);

  const setLevel = useCallback(async (l: Level) => {
    setMe((m) => (m ? { ...m, prefs: { ...(m.prefs ?? {}), level: l } } : m));
    try { await api("/me/prefs", { method: "PUT", body: { level: l } }); } catch (e) { fail(e); }
  }, [fail]);

  const setFocus = useCallback(async (f: Focus) => {
    setMe((m) => (m ? { ...m, prefs: { level: m.prefs?.level ?? null, ...(m.prefs ?? {}), focus: f } } : m));
    try { await api("/me/prefs", { method: "PUT", body: { focus: f } }); } catch (e) { fail(e); }
  }, [fail]);

  const value = useMemo<AppState>(() => ({
    session, ready, me, meError, notebooks, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks,
    allIndicators: !!me?.plan_info.indicators, fno: !!me?.plan_info.fno, level: me?.prefs?.level ?? null, setLevel,
    focus: me?.prefs?.focus ?? null, setFocus, theme, setTheme,
  }), [session, ready, me, meError, notebooks, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks, setLevel, setFocus, theme, setTheme]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
