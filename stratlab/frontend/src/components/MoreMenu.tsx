import { useEffect, useRef, useState, type ReactNode } from "react";

/** A small "More" menu for actions that don't need to be on show all the time. */
export function MoreMenu({ items, label = "More" }: { items: { label: string; icon?: ReactNode; run: () => void; danger?: boolean }[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  return (
    <div className="more-menu" ref={box}>
      <button className="btn quiet sm" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{label}<span className="more-caret" aria-hidden /></button>
      {open && (
        <div className="more-pop" role="menu">
          {items.map((it) => (
            <button key={it.label} role="menuitem" className={it.danger ? "danger" : ""} onClick={() => { setOpen(false); it.run(); }}>{it.icon}{it.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
