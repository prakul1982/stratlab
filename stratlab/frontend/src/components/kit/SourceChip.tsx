import type { ReactNode } from "react";
import { Working } from "./States";

/** A connected source as one small chip (R15, owner 7 Nov: "make this whole thing small buttons and like tickers"): a dot, its name and
 * when it was last read ("● Zerodha · 13 h ago ↻"). With `onRead` the chip is the button that reads it now, and shows the kit's loading bar
 * in place of the ↻ while it reads; without, a plain chip (the statement inbox's address). `off`: a source whose login has ended (its dot
 * muted). `label` names the button for assistive tools ("Read from Zerodha now"); `title` is the longer word on hover. `children`: small
 * controls after the chip, on its line (Copy, Settings). */
export function SourceChip({ name, when, off, busy, onRead, label, title, testId, children }: {
  name: ReactNode; when?: ReactNode; off?: boolean; busy?: boolean; onRead?: () => void; label?: string; title?: string; testId?: string; children?: ReactNode;
}) {
  const face = (
    <>
      <span className="k-source-dot" aria-hidden="true" />
      <span className="k-source-name">{name}{when && <span className="k-muted"> · {when}</span>}</span>
      {onRead && (busy ? <Working inline label={label ? `${label}: reading` : "Reading"} /> : <span className="k-source-go" aria-hidden="true">↻</span>)}
    </>
  );
  return (
    <span className={`k-source${off ? " off" : ""}`} data-testid={testId}>
      {onRead
        ? <button type="button" className="k-chip k-source-chip" onClick={onRead} disabled={busy} aria-busy={busy || undefined} aria-label={label} title={title}>{face}</button>
        : <span className="k-chip k-source-chip static" title={title}>{face}</span>}
      {children}
    </span>
  );
}
