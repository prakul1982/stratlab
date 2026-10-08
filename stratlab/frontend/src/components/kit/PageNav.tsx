/** "On this page": a row of jump links for a long page (the tax report, holdings, a company). Each goes to the card with
 * that `id` (give the Card an `id`), scrolls to it and moves focus there, so the keyboard follows. Keep it to five or six
 * links: the main blocks, in page order. */
export function PageNav({ items, label = "On this page" }: { items: { id: string; label: string }[]; label?: string }) {
  const go = (id: string) => (e: React.MouseEvent) => {
    const el = document.getElementById(id);
    if (!el) return;
    e.preventDefault();
    el.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    if (!el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
    el.focus({ preventScroll: true });
  };
  return (
    <nav className="k-pagenav" aria-label={label}>
      <span className="k-pagenav-k">{label}</span>
      {items.map((x) => <a key={x.id} className="k-pagenav-a" href={`#${x.id}`} onClick={go(x.id)}>{x.label}</a>)}
    </nav>
  );
}
