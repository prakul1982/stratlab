import { useEffect } from "react";

/** The consent question sits in the same corner as the Markets button: the button rises above it, whatever its height (MW-1). */
export function useConsentLift(on: boolean) {
  useEffect(() => {
    const root = document.documentElement;
    if (!on) return;
    let ro: ResizeObserver | null = null;
    const look = () => {
      const el = document.querySelector<HTMLElement>(".consent");
      ro?.disconnect();
      if (!el) { root.style.removeProperty("--mw-lift"); return; }
      const set = () => root.style.setProperty("--mw-lift", `${el.offsetHeight + 12}px`);
      set();
      if (typeof ResizeObserver !== "undefined") { ro = new ResizeObserver(set); ro.observe(el); }
    };
    look();
    const mo = new MutationObserver(look);
    mo.observe(document.body, { childList: true });
    return () => { mo.disconnect(); ro?.disconnect(); root.style.removeProperty("--mw-lift"); };
  }, [on]);
}
