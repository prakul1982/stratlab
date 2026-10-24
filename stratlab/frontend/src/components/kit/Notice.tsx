import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { StateAction } from "./States";
import { CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { unlockHint } from "../../lib/offer";
import { usePlanPrice } from "../../lib/currency";
import { PlanActions } from "../PlanInterest";

/** One line of words beside the page, with an optional button: a plan note ("on the Basic plan" + See plans), an
 * estimate-only reminder. `tone="warn"` gives it the orange edge. Use it instead of a bare `.banner`. */
export function Notice({ children, action, actions, tone = "info", label, role = "note", className }: {
  children: ReactNode; action?: StateAction; tone?: "info" | "warn"; label?: string; className?: string;
  /** More than one button (Apply, Dismiss): put them here, in place of `action`. */
  actions?: ReactNode; role?: "note" | "status";
}) {
  return (
    <div className={`k-notice${tone === "warn" ? " warn" : ""}${className ? ` ${className}` : ""}`} role={role} aria-label={label}>
      <span>{children}</span>
      {action && (action.to ? <Link className="btn sm" to={action.to}>{action.label}</Link> : <button type="button" className="btn sm" onClick={action.onClick}>{action.label}</button>)}
      {actions && <span className="k-row">{actions}</span>}
    </div>
  );
}

/** The plan note: the sentence, how to get it (honest while paid plans aren't on sale: ask for early access), then
 * "See plans". */
export function PlanNote({ children, plan }: { children: ReactNode;
  /** the plan it unlocks; else the first Basic or Pro its words name ("…on the Basic plan") */
  plan?: "basic" | "pro" }) {
  const { me } = useApp();
  const words = useRef<HTMLSpanElement>(null);
  const [named, setNamed] = useState<"basic" | "pro" | null>(null);
  useLayoutEffect(() => {
    const m = /\b(Basic|Pro)\b/.exec(words.current?.textContent ?? "");
    setNamed(m ? (m[1] === "Pro" ? "pro" : "basic") : null);
  });
  const price = usePlanPrice(plan ?? named);
  return <Notice className="plan-note" actions={<PlanActions source="lock" />}><span className="plan-lock" aria-hidden="true">🔒 </span><span ref={words}>{children}</span> {unlockHint(me?.offer, CFG.CONTACT_EMAIL || undefined, price)}</Notice>;
}
