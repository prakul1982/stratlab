/* The "Markets" button and the panel it opens (MW-1), drawn once for the whole page: in the signed-in app by the Shell, in the public
 * half by the visitor app (which draws the button itself, from PublicLauncher, so a policy page's download stays small: R5V-020).
 * It holds the button, the panel's place on the page and the loading of the panel itself; the panel (and the chart, and the account code behind it) loads when it is first opened,
 * or when the button is pointed at. The visitor's panel is a read-only board and loads no account code. */
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import { usePersisted } from "../../lib/persist";
import { importWithRetry } from "../../lib/lazyRetry";
import { clampLayout, dockWidth, DEFAULT_LAYOUT, isSheet, LAYOUT_KEY, shapeOf, type PanelLayout } from "../../lib/watchLayout";
import { useConsentLift } from "../../lib/consentLift";
import { Markets } from "../Icons";
import "./launcher.css";

type PanelProps = { layout: PanelLayout; patch: (p: Partial<PanelLayout>) => void; vw: number; vh: number; onClose: () => void };
const loadApp = () => import("./WatchPanel");
const loadPublic = () => import("./PublicBoard");
const AppPanel = lazy(() => importWithRetry(loadApp)) as unknown as ComponentType<PanelProps>;
const PublicPanel = lazy(() => importWithRetry(loadPublic)) as unknown as ComponentType<PanelProps>;

/** Open (or shut, or flip) the panel from anywhere on the page; with `chart`, on that instrument's chart ("IN:RELIANCE"). */
export function openMarkets(detail: { open?: boolean | "toggle"; chart?: string } = { open: true }) {
  window.dispatchEvent(new CustomEvent("stratlab:markets", { detail }));
}

function useViewport(): [number, number] {
  const [v, setV] = useState<[number, number]>(() => [window.innerWidth, window.innerHeight]);
  useEffect(() => {
    const on = () => setV((o) => (o[0] === window.innerWidth && o[1] === window.innerHeight ? o : [window.innerWidth, window.innerHeight]));
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return v;
}

/** `button`: how the button is drawn when it differs from the panel (someone signed in on a public page has the app's panel and the visitor's button);
 * `autoOpen`: open at once (the visitor's button has just been pressed and this is its code arriving). */
export function MarketsLauncher({ mode, userId, button = mode, autoOpen }: { mode: "app" | "public"; userId?: string; button?: "app" | "public"; autoOpen?: boolean }) {
  const [raw, setRaw] = usePersisted<PanelLayout>(`${LAYOUT_KEY}.${mode === "app" ? userId ?? "guest" : "visitor"}`, DEFAULT_LAYOUT);
  const [vw, vh] = useViewport();
  const layout = useMemo(() => clampLayout(raw, vw, vh), [raw, vw, vh]);
  const patch = useCallback((p: Partial<PanelLayout>) => setRaw((o) => ({ ...clampLayout(o, window.innerWidth, window.innerHeight), ...p })), [setRaw]);
  const [opened, setOpened] = useState(false);          // the panel's code has been asked for: it stays mounted after that, so a re-open is instant
  const btn = useRef<HTMLButtonElement>(null);
  const had = useRef(false);

  // a sheet is never open at page load: a full-height sheet over a page that just opened is in the way, so a sheet shows only
  // once the person has asked for it on this page
  const asked = useRef(!isSheet(window.innerWidth));
  // a press before the account has loaded opens the panel under the guest's key; the person's own key, read once it loads, said closed,
  // so the press was lost (the Markets button did nothing about one time in eight in the browser tests): it is kept and applied then
  const pending = useRef<Partial<PanelLayout> | null>(null);
  const openIt = useCallback((p: Partial<PanelLayout> = {}) => {
    asked.current = true;
    if (mode === "app" && !userId) pending.current = p;
    patch({ ...p, open: true });
  }, [patch, mode, userId]);
  useEffect(() => {
    if (userId && pending.current) { const p = pending.current; pending.current = null; patch({ ...p, open: true }); }
  }, [userId, patch]);

  useEffect(() => { if (autoOpen) openIt(); }, []);   // eslint-disable-line react-hooks/exhaustive-deps -- once, as this mounts
  useEffect(() => {
    const on = (e: Event) => {
      const d = ((e as CustomEvent).detail ?? {}) as { open?: boolean | "toggle"; chart?: string };
      const open = d.open === "toggle" ? !layout.open : d.open !== false;
      if (open) openIt(d.chart ? { chart: d.chart } : {}); else patch({ open: false });
    };
    window.addEventListener("stratlab:markets", on);
    return () => window.removeEventListener("stratlab:markets", on);
  }, [patch, openIt, layout.open]);

  const shown = layout.open && asked.current;
  useEffect(() => { if (shown) setOpened(true); }, [shown]);
  // the page makes room for a docked panel, and the question about cookies moves out from under it
  const dock = shown ? dockWidth(layout, vw) : 0;
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--mw-dock", `${dock}px`);
    document.body.classList.toggle("mw-docked", dock > 0);
    return () => { document.body.classList.remove("mw-docked"); root.style.removeProperty("--mw-dock"); };
  }, [dock]);
  useConsentLift(true);          // the button, and a floating panel, rise above the question
  // focus goes back to the button when the panel closes with focus inside it
  useEffect(() => {
    if (shown) { had.current = true; return; }
    if (had.current) { had.current = false; if (!document.activeElement || document.activeElement === document.body) btn.current?.focus(); }
  }, [shown]);

  const close = useCallback(() => patch({ open: false }), [patch]);
  const Panel = mode === "app" ? AppPanel : PublicPanel;
  return (
    <>
      {!shown && (
        <button ref={btn} type="button" className={`mw-launch ${button}`} aria-label="Open Market Watch" title="Markets" aria-expanded={false} data-testid="markets-launch"
          onClick={() => openIt()} onPointerEnter={() => void (mode === "app" ? loadApp() : loadPublic()).catch(() => undefined)} onFocus={() => void (mode === "app" ? loadApp() : loadPublic()).catch(() => undefined)}>
          <Markets size={18} /><span>Markets</span>
        </button>
      )}
      {opened && (
        <Suspense fallback={shown ? <div className={`mw mw-${shapeOf(layout, vw)} mw-wait`} role="status" aria-label="Opening Market Watch" /> : null}>
          {shown && <Panel layout={layout} patch={patch} vw={vw} vh={vh} onClose={close} />}
        </Suspense>
      )}
    </>
  );
}
