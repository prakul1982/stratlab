import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export type HealthState = "ok" | "warn" | "bad";
const WORD: Record<HealthState, string> = { ok: "OK", warn: "Check", bad: "Problem" };

/** A health light: a dot (green, amber or red) with its word, so the state never rests on colour alone. */
export function Light({ state, word }: { state: HealthState; word?: string }) {
  return <span className={`k-light ${state}`}><span className="k-hl" aria-hidden="true" />{word ?? WORD[state]}</span>;
}

/** Tiles in a grid, one per service or data feed: the name, its light with a word, and a line of detail. */
export function HealthGrid({ label, children }: { label: string; children: ReactNode }) {
  return <div className="k-health" role="list" aria-label={label}>{children}</div>;
}

/** One tile of a HealthGrid. With `to`, the whole tile opens where the thing is fixed. */
export function HealthTile({ state, label, detail, to }: { state: HealthState; label: string; detail?: ReactNode; to?: string }) {
  const body = (
    <>
      <b>{label}</b>
      <Light state={state} />
      {detail && <span className="k-health-d">{detail}</span>}
    </>
  );
  return to
    ? <div role="listitem" className="k-health-cell"><Link className={`k-health-i ${state}`} to={to}>{body}</Link></div>
    : <div role="listitem" className={`k-health-i ${state}`}>{body}</div>;
}

/** A list of statuses, one row each: the name and what it says on the left, the light and any buttons on the right. */
export function StatusList({ label, children }: { label: string; children: ReactNode }) {
  return <div className="k-status-list" role="list" aria-label={label}>{children}</div>;
}

export function StatusRow({ state, label, detail, actions, word }: { state: HealthState; label: string; detail?: ReactNode; actions?: ReactNode; word?: string }) {
  return (
    <div className="k-status-row" role="listitem">
      <span className="k-status-t"><b>{label}</b>{detail && <span className="k-note k-muted">{detail}</span>}</span>
      <span className="k-row"><Light state={state} word={word} />{actions}</span>
    </div>
  );
}
