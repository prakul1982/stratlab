import { useState, type ReactNode } from "react";

const read = (k: string) => { try { return localStorage.getItem(k) === "1"; } catch { return false; } };
const write = (k: string, v: boolean) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch { /* private mode */ } };

/** The advanced part of a form: closed until you open it, and remembered after that. `on` counts the
 * advanced settings in use, so they're never hidden without a trace. Simple by default, all there when wanted. */
export function More({ id, label = "More settings", what, on = 0, children }: {
  id: string; label?: string; what?: string; on?: number; children: ReactNode;
}) {
  const key = `stratlab.more.${id}`;
  const [open, setOpen] = useState(() => read(key));
  const toggle = () => { setOpen(!open); write(key, !open); };
  return (
    <div className={`more${open ? " open" : ""}`}>
      <button type="button" className="more-head" aria-expanded={open} onClick={toggle}>
        <span className="more-chev" aria-hidden>{open ? "−" : "+"}</span>
        <b>{label}</b>
        {what && <span className="muted small more-what">{what}</span>}
        {on > 0 && <span className="badge next">{on} on</span>}
      </button>
      {open && <div className="more-body">{children}</div>}
    </div>
  );
}

/** A titled step inside a card: one idea per block, with room around it. */
export function Block({ title, info, aside, children }: { title: ReactNode; info?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <div className="block">
      <div className="block-h"><span className="eyebrow row" style={{ gap: 0 }}>{title}{info}</span>{aside}</div>
      {children}
    </div>
  );
}
