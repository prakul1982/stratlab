import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { Session } from "@supabase/auth-js";
import { api, ApiError, setApiHandlers, supabase } from "./api";
import { clearLocalData } from "./localData";
import { signOutHere } from "./signout";
import { clearSignInEnded, noteSignInEnded } from "./signin";
import type { Focus, Level, Market, Me, NotebookItem } from "./types";
import { takeRef } from "./share";
import { identify, resetAnalytics, track, trackSignup } from "./analytics";
import { canBuy, plansCall } from "./offer";
import { planPriceFor } from "./currency";
import { JOINED, JOIN_LABEL, joinInterest, resetInterest } from "./planInterest";
import { readViewAs, writeViewAs, type ViewAs } from "./viewAs";
import { CFG } from "./config";
import { hasSavedSession } from "./entry";
import { useLiveRefresh } from "./liveRefresh";
import { saveView, savedView, viewForFocus, viewFromSaved, viewToServer, type SpaceView } from "./spaces";
import { toastMs } from "./toastTime";

const ME_RETRY_MS = 1500;
const SESSION_RETRY_MS = [2000, 5000];

/** No session, but one is saved in this browser: the sign-in service didn't answer while it was renewed (R20-002). The
 * person is still signed in; the page says it couldn't load instead of offering sign-in. */
export const sessionUnconfirmed = (ready: boolean, session: Session | null): boolean =>
  ready && !session && hasSavedSession(CFG.SUPABASE_URL, (() => { try { return localStorage; } catch { return null; } })());

type Toast = { msg: string; action?: { label: string; run: () => void } } | null;

interface AppState {
  session: Session | null;
  ready: boolean;
  me: Me | null;
  meError: string | null;
  notebooks: NotebookItem[] | null;
  /** the last read of the list failed: an empty `notebooks` is then not "no notebooks" */
  notebooksFailed: boolean;
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
  /** Several preferences in one save, like the welcome question's answers. */
  savePrefs: (p: Prefs, quiet?: boolean) => Promise<void>;
  /** The menu showing: one space (Trade, Invest, Money) or all of them. */
  space: SpaceView;
  /** Show another space's menu. `save` keeps it as the account's choice too (the switcher); a deep link into another
   * space only switches on this device. */
  setSpace: (s: SpaceView, save?: boolean) => void;
  /** The plan the site owner is viewing the app as, as the server confirms it (null: off, and always null for anyone else). */
  viewAs: ViewAs | null;
  /** Turn "View as" on for a plan, or off (null). Checked with the server, kept on this device, then the page reloads so every
   * lock, limit and number is read again as that plan. */
  setViewAs: (v: ViewAs | null) => Promise<void>;
  theme: "light" | "dark" | "system";
  setTheme: (t: "light" | "dark" | "system") => void;
}

type Prefs = { level?: Level; focus?: Focus; space?: SpaceView; /** My space's layout, on the account (DI-006) */ mine?: { order: string[]; hidden: string[] } };

const Ctx = createContext<AppState | null>(null);
export const useApp = () => useContext(Ctx)!;

/** The browser's bar colour follows the app's own paper colour: an explicit choice sets both variants, "system" puts back the
 *  light/dark pair that index.html carries for the OS scheme. */
export const THEME_COLOR = { light: "#F5F1E8", dark: "#141311" } as const;
export function applyThemeColor(t: "light" | "dark" | "system") {
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach((m) => {
    const dark = m.media.includes("dark");
    m.content = t === "system" ? (dark ? THEME_COLOR.dark : THEME_COLOR.light) : THEME_COLOR[t];
  });
}
export function AppProvider({ children, goToPlans }: { children: ReactNode; goToPlans: () => void }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [meError, setMeError] = useState<string | null>(null);
  const [notebooks, setNotebooks] = useState<NotebookItem[] | null>(null);
  const [notebooksFailed, setNotebooksFailed] = useState(false);
  const [markets, setMarkets] = useState<Market[]>([]);
  const [dataOffline, setDataOffline] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const timer = useRef<number>(undefined);
  const [spaceHere, setSpaceHere] = useState<SpaceView | null>(savedView);
  const [theme, setThemeState] = useState<"light" | "dark" | "system">(() => {
    try { return (localStorage.getItem("stratlab-theme") as "light" | "dark") || "system"; } catch { return "system"; }
  });

  const notify = useCallback((msg: string, action?: { label: string; run: () => void }) => {
    setToast({ msg, action });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), toastMs(msg, !!action));
  }, []);

  // goToPlans changes with every page change; read it through a ref so `fail` stays the same function and
  // pages that load data with it don't load again each time the address changes
  const plans = useRef(goToPlans);
  plans.current = goToPlans;
  const offer = useRef<Me["offer"]>(undefined);
  offer.current = me?.offer;
  const fail = useCallback((e: unknown) => {
    const err = e as ApiError;
    if (err?.status === 402) {
      // while no plan can be bought, "See plans" leads nowhere: offer to tell them when plans open instead
      const show = (msg: string) => {
        if (plansCall(offer.current, false).kind === "see") notify(msg, { label: "See plans", run: () => { track("upgrade clicked", { source: "limit" }); plans.current(); } });
        else notify(msg, { label: JOIN_LABEL, run: () => void joinInterest("limit").then(() => notify(JOINED)).catch(() => notify("Something went wrong. Try again.")) });
      };
      // the one lock wording (DP2-022, DP1-018): the server's words, then the plan's price in the visitor's own currency while a
      // plan can be bought (while none can, the server's words already say how to get early access)
      if (canBuy(offer.current) && err.plan) void planPriceFor(err.plan).then((p) => show(p ? `${err.message} ${p}` : err.message));
      else show(err.message);
    }
    else notify(err?.message || "Something went wrong. Try again.");
  }, [notify]);

  const refreshMe = useCallback(async () => {
    try {
      // one quiet second try when the server or the network had a moment (a 503 or no answer): the person sees the
      // error and its Retry button only if that fails too (R5O-002)
      const m = await api<Me>("/me").catch(async (e: ApiError) => {
        if (e?.status && e.status !== 503 && e.status !== 502 && e.status !== 504) throw e;
        await new Promise((ok) => window.setTimeout(ok, ME_RETRY_MS));
        return api<Me>("/me");
      });
      setMe(m);
      setMeError(null);
      setDataOffline(!m.data_online);
    } catch (e) {
      setMeError((e as Error).message);
    }
  }, []);

  // the newest ask's answer is the one kept: an older list landing after it put a renamed notebook's old name back in the
  // sidebar until a reload (DB-024)
  const nbSeq = useRef(0);
  const refreshNotebooks = useCallback(async () => {
    const n = ++nbSeq.current;
    try { const got = await api<NotebookItem[]>("/notebooks"); if (n === nbSeq.current) { setNotebooks(got); setNotebooksFailed(false); } }
    catch (e) { if (n !== nbSeq.current) return; setNotebooks((x) => x ?? []); setNotebooksFailed(true); fail(e); }
  }, [fail]);

  useEffect(() => {
    setApiHandlers({
      unauthorized: () => { noteSignInEnded(); void signOutHere(supabase.auth); },
      offline: () => setDataOffline(true),
    });
    // a saved sign-in that can't be renewed right now (no answer) comes back as "no session" with the saved one kept: ask
    // again a little later before anything is decided
    let live = true;
    const check = (tries: number) => supabase.auth.getSession().catch(() => ({ data: { session: null } })).then(({ data }) => {
      if (!live) return;
      if (data.session || tries >= SESSION_RETRY_MS.length || !sessionUnconfirmed(true, null)) { setSession(data.session); setReady(true); return; }
      window.setTimeout(() => check(tries + 1), SESSION_RETRY_MS[tries]);
    });
    check(0);
    const { data } = supabase.auth.onAuthStateChange((e, s) => {
      if (e === "SIGNED_OUT") { writeViewAs(null); clearLocalData(); }          // "View as" is the owner's, on this device: it doesn't outlive the sign-in
      setSession(s);
      if (s) { setReady(true); clearSignInEnded(); }        // signed in again: a later sign-out is the person's own
    });
    return () => { live = false; data.subscription.unsubscribe(); };
  }, []);

  useEffect(() => {
    if (!session) { setMe(null); setNotebooks(null); resetAnalytics(); resetInterest(); return; }
    const ref = takeRef();          // arrived by a friend's invite link: say so once (the server counts new accounts only)
    if (ref) api("/me/referral", { method: "POST", body: { code: ref } }).catch(() => undefined);
    refreshMe();
    refreshNotebooks();
    api<Market[]>("/markets").then(setMarkets).catch(() => {});
  }, [session?.user?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // the markets' list again each minute while the tab is in view (LIVE-1): the side menu's and the pages' "open / closes in" read the
  // hours from it, and a feed that was off at sign-in, a holiday added or a market's status changing reaches a page left open. The list
  // is replaced only when it changed, so nothing that reads it runs again for nothing.
  useLiveRefresh(!!session, () => {
    api<Market[]>("/markets").then((m) => setMarkets((cur) => (JSON.stringify(cur) === JSON.stringify(m) ? cur : m))).catch(() => undefined);
  });

  // usage analytics: this account by its id only, with its plan (does nothing without a key)
  useEffect(() => {
    if (!me?.id || !session) return;
    identify(me.id, { plan: me.plan, backtests: me.usage?.backtests_used, createdAt: session.user?.created_at });
    trackSignup(me.id, session.user?.created_at);
  }, [me?.id, me?.plan]); // eslint-disable-line react-hooks/exhaustive-deps

  // the choice is kept on this device; an account that isn't the owner's can't use it, so a stale one is dropped
  useEffect(() => { if (me && !me.is_admin && readViewAs()) writeViewAs(null); }, [me]);
  const setViewAs = useCallback(async (v: ViewAs | null) => {
    try { await api("/admin/view-as", { method: "PUT", body: { plan: v } }); } catch (e) { fail(e); return; }
    writeViewAs(v);
    window.location.reload();
  }, [fail]);

  const setTheme = useCallback((t: "light" | "dark" | "system") => {
    setThemeState(t);
    try {
      if (t === "system") { localStorage.removeItem("stratlab-theme"); delete document.documentElement.dataset.theme; }
      else { localStorage.setItem("stratlab-theme", t); document.documentElement.dataset.theme = t; }
    } catch { /* private mode */ }
    applyThemeColor(t);
  }, []);

  /** Save some of the preferences in one request (two at once could each overwrite the other's change). */
  const savePrefs = useCallback(async (p: Prefs, quiet = false) => {
    if (p.space) { setSpaceHere(p.space); saveView(p.space); }
    setMe((m) => (m ? { ...m, prefs: { level: m.prefs?.level ?? null, ...(m.prefs ?? {}), ...p, space: p.space ? viewToServer(p.space) : m.prefs?.space } } : m));
    try { await api("/me/prefs", { method: "PUT", body: p.space ? { ...p, space: viewToServer(p.space) } : p }); } catch (e) { if (!quiet) fail(e); }
  }, [fail]);
  const setLevel = useCallback((l: Level) => savePrefs({ level: l }), [savePrefs]);
  const setFocus = useCallback((f: Focus) => savePrefs({ focus: f }), [savePrefs]);
  const setSpace = useCallback((s: SpaceView, save = true) => {
    if (save) { savePrefs({ space: s }, true); return; }       // only a default: a failed save isn't worth a message
    setSpaceHere(s);
    saveView(s);
  }, [savePrefs]);
  // this device's last menu, else the account's choice, else what the person came for, else Trade
  const space: SpaceView = spaceHere ?? viewFromSaved(me?.prefs?.space) ?? viewForFocus(me?.prefs?.focus) ?? "trade";

  const value = useMemo<AppState>(() => ({
    session, ready, me, meError, notebooks, notebooksFailed, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks,
    allIndicators: !!me?.plan_info.indicators, fno: !!me?.plan_info.fno, level: me?.prefs?.level ?? null, setLevel,
    focus: me?.prefs?.focus ?? null, setFocus, savePrefs, space, setSpace, theme, setTheme,
    viewAs: me?.is_admin ? me.view_as ?? null : null, setViewAs,
  }), [session, ready, me, meError, notebooks, notebooksFailed, markets, dataOffline, toast, notify, fail, refreshMe, refreshNotebooks, setLevel, setFocus, savePrefs, space, setSpace, theme, setTheme, setViewAs]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
