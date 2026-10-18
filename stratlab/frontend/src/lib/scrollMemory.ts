import { useEffect, useLayoutEffect, useRef } from "react";
import { useLocation, useNavigationType } from "react-router-dom";

/* Back and Forward land where the page was left. The browser's own restore runs before a page's data has come in, when
 * the page is still short, so a long page of tables (the journal, the tax report) came back at the top (R53-003). Each
 * history entry's scroll is kept; on Back or Forward it is put back as soon as the page is tall enough, for a few
 * seconds, unless the reader scrolls first. A new page still starts at the top. */

const KEY = "stratlab.scroll";
const read = (): Record<string, number> => { try { return JSON.parse(sessionStorage.getItem(KEY) || "{}") || {}; } catch { return {}; } };
const write = (m: Record<string, number>) => { try { sessionStorage.setItem(KEY, JSON.stringify(m)); } catch { /* storage off */ } };

export function useScrollMemory() {
  const loc = useLocation();
  const nav = useNavigationType();
  const lastPath = useRef(loc.pathname);
  useLayoutEffect(() => {
    try { if ("scrollRestoration" in history) history.scrollRestoration = "manual"; } catch { /* old browser */ }
  }, []);
  // keep this entry's scroll as the reader moves. A layout effect, so the listener is gone in the same commit as the
  // page it watched: the next page, shorter at first, makes the browser clamp the scroll, and that is not this entry's
  useLayoutEffect(() => {
    let t = 0, y = -1;
    const keep = () => { if (y < 0) return; const m = read(); m[loc.key] = y; write(m); };
    // y is taken as it happens, so a click soon after scrolling still keeps where the page was
    const save = () => { y = window.scrollY; window.clearTimeout(t); t = window.setTimeout(keep, 120); };
    window.addEventListener("scroll", save, { passive: true });
    return () => { window.clearTimeout(t); window.removeEventListener("scroll", save); keep(); };
  }, [loc.key]);
  // put it back on Back or Forward, once the page has grown to it
  useEffect(() => {
    // a new page opens at its top; a tab or filter kept in the address (same page) stays where it is
    const moved = lastPath.current !== loc.pathname;
    lastPath.current = loc.pathname;
    if (nav !== "POP") { if (moved && !loc.hash) window.scrollTo(0, 0); return; }
    const y = read()[loc.key];
    if (!y) return;
    let stopped = false;
    const stop = () => { stopped = true; };
    for (const ev of ["wheel", "touchstart", "keydown"]) window.addEventListener(ev, stop, { passive: true, capture: true });
    const started = Date.now();
    const tick = () => {
      if (stopped) return;
      if (document.documentElement.scrollHeight - window.innerHeight >= y - 2) { window.scrollTo(0, y); return; }
      if (Date.now() - started < 4000) window.setTimeout(tick, 100);
    };
    tick();
    return () => { stopped = true; for (const ev of ["wheel", "touchstart", "keydown"]) window.removeEventListener(ev, stop, { capture: true }); };
  }, [loc.key, nav, loc.hash]);
}
