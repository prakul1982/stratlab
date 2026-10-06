import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { StateAction } from "./States";

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

/** The plan note: the sentence, then "See plans". */
export function PlanNote({ children }: { children: ReactNode }) {
  return <Notice action={{ label: "See plans", to: "/plans" }}>{children}</Notice>;
}
