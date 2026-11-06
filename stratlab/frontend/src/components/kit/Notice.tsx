import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useLockSlot } from "../../lib/lockSlot";
import type { StateAction } from "./States";
import { CFG } from "../../lib/api";
import { useApp } from "../../lib/app";
import { unlockHint } from "../../lib/offer";
import { usePlanPrice } from "../../lib/currency";
import { PlanActions } from "../PlanInterest";
import { Lock } from "../Icons";

/** One line of words beside the page, with an optional button: a plan note ("on the Basic plan" + See plans), an
 * estimate-only reminder. `tone="warn"` gives it the orange edge. Use it instead of a bare `.banner`.
 *
 * A standing note about the whole page (an "Estimate only" disclaimer: the default role "note", the info tone, no button, drawn
 * between the page's sections rather than inside a card) goes to the top of the page, under its title, on every page (owner, 7 Nov:
 * "put this at top not in between this do globally"). `top` says it outright: true moves any notice there, false keeps one in place. */
export function Notice({ children, action, actions, tone = "info", label, role = "note", className, top }: {
  children: ReactNode; action?: StateAction; tone?: "info" | "warn"; label?: string; className?: string;
  /** More than one button (Apply, Dismiss): put them here, in place of `action`. */
  actions?: ReactNode; role?: "note" | "status"; top?: boolean;
}) {
  const here = useRef<HTMLDivElement>(null);
  const slot = useLockSlot();
  const [lifted, setLifted] = useState(false);
  const standing = top ?? (role === "note" && tone === "info" && !action && !actions);
  useLayoutEffect(() => {
    if (lifted) return;
    const el = here.current;
    // only a note that sits among the page's sections: not one inside a card, a form, a dialog or a menu
    setLifted(!!standing && !!slot && !!el && !el.parentElement?.closest(".k-card, form, [role=dialog], dialog, .modal, [role=menu], .page-lock-slot"));
  }, [standing, slot, lifted]);
  const box = (
    <div ref={here} className={`k-notice${tone === "warn" ? " warn" : ""}${lifted ? " k-notice-top" : ""}${className ? ` ${className}` : ""}`} role={role} aria-label={label}>
      <span>{children}</span>
      {action && (action.to ? <Link className="btn sm" to={action.to}>{action.label}</Link> : <button type="button" className="btn sm" onClick={action.onClick}>{action.label}</button>)}
      {actions && <span className="k-row">{actions}</span>}
    </div>
  );
  return lifted && slot && slot.isConnected ? createPortal(box, slot) : box;
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
  // one lock wording everywhere (DP2-022, DP1-018): the line icon, what is locked and on which plan (and when a monthly count
  // starts again), the price, then the button; never the emoji, never "see plans" in words beside the button
  return <Notice className="plan-note" actions={<PlanActions source="lock" />}><span className="plan-lock" aria-hidden="true"><Lock /></span><span ref={words}>{children}</span> {unlockHint(me?.offer, CFG.CONTACT_EMAIL || undefined, price)}</Notice>;
}
