import { useState, type ReactNode } from "react";
import { Badge, Disclosure } from "./kit";
import "../pages/trade/trade.css";

const read = (k: string) => { try { return localStorage.getItem(k) === "1"; } catch { return false; } };
const write = (k: string, v: boolean) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch { /* private mode */ } };

/** The advanced part of a form: closed until you open it, and remembered after that. `on` counts the
 * advanced settings in use, so they're never hidden without a trace. Simple by default, all there when wanted. */
export function More({ id, label = "More settings", what, on = 0, children }: {
  id: string; label?: string; what?: string; on?: number; children: ReactNode;
}) {
  const key = `stratlab.more.${id}`;
  const [open, setOpen] = useState(() => read(key));
  return (
    <Disclosure open={open} onToggle={(o) => { setOpen(o); write(key, o); }}
      summary={<><b>{label}</b>{what && <span className="k-note k-more-what">{what}</span>}{on > 0 && <Badge tone="ok" dot={false}>{on} on</Badge>}</>}>
      {children}
    </Disclosure>
  );
}

/** A titled step inside a card: one idea per block, with room around it. */
export function Block({ title, info, aside, children }: { title: ReactNode; info?: ReactNode; aside?: ReactNode; children: ReactNode }) {
  return (
    <div className="block">
      <div className="block-h"><span className="eyebrow k-inline">{title}{info}</span>{aside}</div>
      {children}
    </div>
  );
}
