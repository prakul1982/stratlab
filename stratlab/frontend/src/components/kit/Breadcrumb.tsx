import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router-dom";

export type Crumb = { label: string; to: string };
export type Sibling = { to: string; label: string; current?: boolean };

/** The trail at the top of every page: "Invest › Market view › Margin funding ▾". The space and the group are links (the
 * group opens its page of cards); the last part is the page you are on, and opens a small menu of the other pages in the
 * same group. When `onTogglePin` is given the menu ends with "Pin to sidebar" / "Unpin from sidebar". `page` is left out
 * on a group's own page: the trail then ends with the group, as plain text. */
export function Breadcrumb({ trail, page, siblings = [], seeAll, pinned, onTogglePin }: {
  trail: Crumb[]; page?: string; siblings?: Sibling[]; seeAll?: Crumb; pinned?: boolean; onTogglePin?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLElement>("[role=menuitem]")?.focus();
    const key = (e: globalThis.KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); btn.current?.focus(); } };
    const down = (e: PointerEvent) => { const t = e.target as Node; if (!menu.current?.contains(t) && !btn.current?.contains(t)) setOpen(false); };
    document.addEventListener("keydown", key, true);
    document.addEventListener("pointerdown", down);
    return () => { document.removeEventListener("keydown", key, true); document.removeEventListener("pointerdown", down); };
  }, [open]);
  useEffect(() => setOpen(false), [page]);
  // up and down move between the items, as in any menu
  const keys = (e: KeyboardEvent) => {
    const items = Array.from(menu.current?.querySelectorAll<HTMLElement>("[role=menuitem]") ?? []);
    const i = items.indexOf(document.activeElement as HTMLElement);
    const to = e.key === "ArrowDown" ? (i + 1) % items.length : e.key === "ArrowUp" ? (i - 1 + items.length) % items.length : e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : null;
    if (to !== null) { e.preventDefault(); items[to]?.focus(); }
    else if (e.key === "Tab") setOpen(false);
  };
  const hasMenu = !!page && (siblings.length > 1 || !!onTogglePin || !!seeAll);
  return (
    <nav className="k-crumb" aria-label="Breadcrumb">
      <ol>
        {trail.map((c, i) => (
          <li key={c.to}>
            {i === trail.length - 1 && !page ? <span aria-current="page">{c.label}</span> : <Link to={c.to}>{c.label}</Link>}
            {(i < trail.length - 1 || page) && <span className="sep" aria-hidden="true">›</span>}
          </li>
        ))}
        {page && (
          <li className="here">
            {hasMenu ? (
              <>
                <button ref={btn} type="button" className="k-crumb-btn" aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
                  onClick={() => setOpen(!open)}><span aria-current="page">{page}</span><span className="caret" aria-hidden="true">▾</span><span className="sr-only"> (other pages in this group)</span></button>
                {open && (
                  <div ref={menu} id={id} className="k-crumb-menu" role="menu" aria-label={`Pages near ${page}`} onKeyDown={keys}>
                    {siblings.map((s) => (
                      <Link key={s.to} role="menuitem" to={s.to} aria-current={s.current ? "page" : undefined} onClick={() => setOpen(false)}>{s.label}</Link>
                    ))}
                    {seeAll && <Link role="menuitem" className="all" to={seeAll.to} onClick={() => setOpen(false)}>{seeAll.label}</Link>}
                    {onTogglePin && (
                      <>
                        <hr />
                        <button type="button" role="menuitem" onClick={() => { onTogglePin(); setOpen(false); btn.current?.focus(); }}>{pinned ? "Unpin from sidebar" : "Pin to sidebar"}</button>
                      </>
                    )}
                  </div>
                )}
              </>
            ) : <span aria-current="page">{page}</span>}
          </li>
        )}
      </ol>
    </nav>
  );
}
