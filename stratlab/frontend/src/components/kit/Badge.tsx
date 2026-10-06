import type { ReactNode } from "react";

/** A status word with a dot, never colour alone. `live` is the green pulsing dot (it stops pulsing when the reader has
 * asked their device for less motion). `ok` blue, `warn` orange, `plain` neutral. */
export function Badge({ tone = "plain", dot = true, children }: { tone?: "ok" | "warn" | "plain" | "live"; dot?: boolean; children: ReactNode }) {
  return (
    <span className={`k-badge ${tone}`}>
      {dot && <span className="k-dot" aria-hidden="true" />}
      {children}
    </span>
  );
}
