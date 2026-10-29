import type { ReactNode } from "react";

/** The long qualifiers under a table or a card, numbered (TABLE-SWEEP, owner 29 Oct: "long qualifiers as numbered notes"): one
 * short sentence or two each, in the page's small muted type, so a figure's caveat is read as a note, not a wall of bullets. */
export function Notes({ items, label = "Notes", start, testId }: { items: ReactNode[]; label?: string; start?: number; testId?: string }) {
  const shown = items.filter((x) => x != null && x !== false && x !== "");
  if (!shown.length) return null;
  return <ol className="k-notes" aria-label={label} start={start} data-testid={testId}>{shown.map((x, i) => <li key={i}>{x}</li>)}</ol>;
}
