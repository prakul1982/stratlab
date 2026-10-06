import type { ReactNode } from "react";

/** A fold for the detail ("How this is worked out"): one line when closed, open only when asked. `onToggle` tells the page
 * when it opens or closes (to remember it); `className` and `testId` let a page name its fold. */
export function Disclosure({ summary, children, open, onToggle, className, testId }: {
  summary: ReactNode; children: ReactNode; open?: boolean; onToggle?: (open: boolean) => void; className?: string; testId?: string;
}) {
  return (
    <details className={`k-disclosure${className ? ` ${className}` : ""}`} open={open} data-testid={testId}
      onToggle={onToggle ? (e) => onToggle((e.currentTarget as HTMLDetailsElement).open) : undefined}>
      <summary>{summary}</summary>
      <div className="k-disclosure-body">{children}</div>
    </details>
  );
}
