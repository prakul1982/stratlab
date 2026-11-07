import { useLayoutEffect, useState } from "react";
import { scrollBehavior } from "../../lib/motion";
import { openSection, useSectionOrder } from "./Section";

/** "On this page": a row of jump links for a long page (the tax report, holdings, a company). Each goes to the card with
 * that `id` (give the Card an `id`), scrolls to it and moves focus there, so the keyboard follows. Keep it to five or six
 * links: the main blocks, in page order. A section the person moved (kit/Section.tsx) is linked where it now is, and a closed one opens. */
export function PageNav({ items, label = "On this page" }: { items: { id: string; label: string }[]; label?: string }) {
  // in the order the sections are shown: the page's own, or the person's (a kept order moves them with CSS, so their places are measured)
  const kept = useSectionOrder();
  const [seq, setSeq] = useState<string[] | null>(null);
  const sig = items.map((x) => x.id).join(" ");
  useLayoutEffect(() => {
    if (!kept?.length) { setSeq(null); return; }
    const at = (id: string) => { const r = document.getElementById(id)?.getBoundingClientRect(); return r ? r.top + window.scrollY : Infinity; };
    setSeq(items.map((x) => x.id).sort((a, b) => at(a) - at(b)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig, kept?.join(" ")]);
  const shown = seq ? [...items].sort((a, b) => seq.indexOf(a.id) - seq.indexOf(b.id)) : items;
  const go = (id: string) => (e: React.MouseEvent) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    openSection(el);
    el.scrollIntoView({ behavior: scrollBehavior(), block: "start" });
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    el.focus({ preventScroll: true });
  };
  return (
    <nav className="k-pagenav" aria-label={label}>
      <span className="k-pagenav-k">{label}</span>
      {shown.map((x) => <a key={x.id} className="k-pagenav-a" href={`#${x.id}`} onClick={go(x.id)}>{x.label}</a>)}
    </nav>
  );
}
