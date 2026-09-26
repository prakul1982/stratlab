import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Session } from "@supabase/supabase-js";
import { api, ApiError, setApiHandlers, supabase } from "./api";
import type { Level, Market, Me, NotebookItem } from "./types";

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
  isPro: boolean;
  level: Level | null;
  setLevel: (l: Level) => Promise<void>;
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

  const fail = useCallback((e: unknown) => {
    const err = e as ApiError;
    if (err?.status === 402) notify(err.message, { label: "See plans", run: goToPlans });
    else notify(err?.message || "Something went wrong. Try again.");
  }, [notify, goToPlans]);

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
    if (!session) { setMe(null); setNotebooks(null); return; }
    refreshMe();
    refreshNotebooks();
    api<Market[]>("/markets").then(setMarkets).catch(() => {});
  }, [session?.user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

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

  const value = useMemo<AppState>(() => ({
    session, ready, me, meError, notebooks, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks,
    isPro: !!me?.plan_info.pro_features, level: me?.prefs?.level ?? null, setLevel, theme, setTheme,
  }), [session, ready, me, meError, notebooks, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks, setLevel, theme, setTheme]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
