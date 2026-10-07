import { useRef, useState, type ReactNode } from "react";
import { usePopover } from "./kit/Dialog";
import "../pages/trade/trade.css";

/** A small "More" menu for actions that don't need to be on show all the time. */
export function MoreMenu({ items, label = "More", icon, buttonClass = "btn quiet sm", align = "left" }: {
  items: { label: string; icon?: ReactNode; run: () => void; danger?: boolean }[]; label?: string; icon?: ReactNode; buttonClass?: string; align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  // focus onto the first item; Esc or a click outside closes, and focus goes back to the button
  usePopover(open, setOpen, btn, pop, { outside: box });
  return (
    <div className="more-menu" ref={box}>
      <button ref={btn} className={buttonClass} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>{icon}{label}<span className="more-caret" aria-hidden /></button>
      {open && (
        <div ref={pop} className={`more-pop${align === "right" ? " right" : ""}`} role="menu">
          {items.map((it) => (
            <button key={it.label} role="menuitem" className={it.danger ? "danger" : ""} onClick={() => { setOpen(false); it.run(); }}>{it.icon}{it.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}
