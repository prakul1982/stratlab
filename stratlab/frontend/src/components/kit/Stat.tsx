import type { ReactNode } from "react";

/** A change as a pill: ▲ up, ▼ down. The colour follows the sign (`tone="auto"`); pass `tone="neutral"` where a rise is
 * not good news and a fall is not bad (the market's margin-funded book, open interest): the arrow still shows the
 * direction, the colour does not judge. Screen readers hear "up" or "down". `value` only decides the direction. */
export function Delta({ value, children, tone = "auto" }: { value: number | null | undefined; children: ReactNode; tone?: "auto" | "neutral" }) {
  if (value == null || !Number.isFinite(value)) return null;
  const dir = value > 0 ? "up" : value < 0 ? "down" : "flat";
  const cls = tone === "neutral" ? "flat" : dir;
  return (
    <span className={`k-delta ${cls}`}>
      {dir !== "flat" && <span aria-hidden="true">{dir === "up" ? "▲" : "▼"}</span>}
      <span className="sr-only">{dir === "up" ? "Up " : dir === "down" ? "Down " : ""}</span>
      {children}
    </span>
  );
}

/** One figure: a small label, a big number (the page's sans font, never mono) and a note under it. `tone` colours the
 * number up or down; `delta` puts a Delta pill in the note line. */
export function Stat({ label, value, note, delta, tone, item }: { label: ReactNode; value: ReactNode; note?: ReactNode; delta?: ReactNode; tone?: "up" | "down"; item?: boolean }) {
  return (
    <div className="k-stat" role={item ? "listitem" : undefined}>
      <span className="k-stat-k">{label}</span>
      <span className={`k-stat-v${tone ? ` k-${tone}` : ""}`}>{value}</span>
      {(delta || note) && <span className="k-stat-d">{delta}{delta && note ? " " : ""}{note}</span>}
    </div>
  );
}

/** Stats side by side; they wrap to the width (about three across on a desktop card, one on a phone). */
export function StatRow({ children, label }: { children: ReactNode; label?: string }) {
  return <div className="k-stats" role={label ? "list" : undefined} aria-label={label}>{children}</div>;
}
