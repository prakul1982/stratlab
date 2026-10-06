import type { ReactNode } from "react";

/** A fold for the detail ("How this is worked out"): one line when closed, open only when asked. */
export function Disclosure({ summary, children, open }: { summary: ReactNode; children: ReactNode; open?: boolean }) {
  return (
    <details className="k-disclosure" open={open}>
      <summary>{summary}</summary>
      <div className="k-disclosure-body">{children}</div>
    </details>
  );
}
