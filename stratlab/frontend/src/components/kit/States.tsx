import { useEffect, useState, type ReactNode } from "react";
import { SLOW_LOAD_MS, SLOW_LOAD_NOTE } from "../../lib/phoneFit";
import { Link } from "react-router-dom";

export type StateAction = { label: string; onClick?: () => void; to?: string };

const Action = ({ a }: { a: StateAction }) => (a.to ? <Link className="btn sm" to={a.to}>{a.label}</Link> : <button type="button" className="btn sm" onClick={a.onClick}>{a.label}</button>);

/** Nothing here yet: a calm box that says what it is and what to do next (an optional button). */
export function EmptyState({ title, children, action, icon }: { title: string; children?: ReactNode; action?: StateAction; icon?: ReactNode }) {
  return (
    <div className="k-state">
      <div className="ic" aria-hidden="true"><svg viewBox="0 0 24 24">{icon ?? <path d="M4 7h16M4 12h16M4 17h10" />}</svg></div>
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action && <Action a={action} />}
    </div>
  );
}

/** Something could not be read: the same box with an orange edge, announced to screen readers. Say what happened in plain
 * words and what happens next; offer "Try again" when trying again can help. */
export function ErrorState({ title, children, action }: { title: string; children?: ReactNode; action?: StateAction }) {
  return (
    <div className="k-state error" role="alert">
      <div className="ic" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" /><path d="M12 8v5M12 16.5v.5" /></svg></div>
      <b>{title}</b>
      {children && <p>{children}</p>}
      {action && <Action a={action} />}
    </div>
  );
}

/** A card's placeholder while it loads: a few shimmering lines and a caption saying what is loading. With `onRetry`, a load that
 * takes more than SLOW_LOAD_MS says so and offers a Retry (R25-005: a first visit of the day waited 10 s with nothing to do). */
export function Skeleton({ label, lines = 4, onRetry, slowAfter = SLOW_LOAD_MS }: { label: string; lines?: number; onRetry?: () => void; slowAfter?: number }) {
  const [slow, setSlow] = useState(false);
  const canRetry = !!onRetry;                // not the function itself: a new one each render would restart the clock
  useEffect(() => {
    if (!canRetry) return;
    setSlow(false);
    const t = window.setTimeout(() => setSlow(true), slowAfter);
    return () => window.clearTimeout(t);
  }, [canRetry, slowAfter, label]);
const widths = [40, 100, 85, 60, 92, 70];
  return (
    <div className="k-skel-box" role="status" aria-busy="true" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => <span key={i} className="k-skel" style={{ width: `${widths[i % widths.length]}%` }} />)}
      <span className="k-stat-d">{label}…</span>
      {slow && onRetry && <span className="k-row" data-testid="skel-slow"><span className="k-stat-d">{SLOW_LOAD_NOTE}</span><button type="button" className="btn sm" onClick={() => { setSlow(false); onRetry(); }}>Retry</button></span>}
    </div>
  );
}
