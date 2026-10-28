import type { ReactNode } from "react";

/** A sentence with each signed money figure in it ("−$16.35", "+₹1,557") kept on one line, so a sign never ends a line on its own
 * and leaves its number on the next (LIVE1B-020: "−" then "$16.35" on a phone). */
export function NoBreak({ text }: { text: string }): ReactNode {
  return text.split(/([−+-]?[$₹][\d,]+(?:\.\d+)?)/).map((part, i) => (i % 2 ? <span key={i} className="k-nb">{part}</span> : part));
}
