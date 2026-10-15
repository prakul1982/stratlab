import { useEffect } from "react";

/** Close a `<details>` menu with Esc or a tap outside it, the way every other pop-up on the site closes. */
export function useDetailsDismiss(ref: React.RefObject<HTMLDetailsElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const close = (back: boolean) => { if (el.open) { el.open = false; if (back) el.querySelector("summary")?.focus(); } };
    const key = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") close(true); };
    const down = (e: Event) => { if (!el.contains(e.target as Node)) close(false); };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", down);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", down); };
  }, [ref]);
}
