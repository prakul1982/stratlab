import type { ReactNode } from "react";
import { useNoOrphan } from "../lib/noOrphan";

/** A grid of equal tiles (the cards of a group page, the "more you can do" tiles): the same CSS grid as ever, but it never leaves the last
 * tile alone on a line (UI-FIX-1, R9). `className` is the grid's own class (explore-grid, nav-cards). `fill`: two cards share the whole row instead of leaving its right third empty (VR3-001). */
export function TileGrid({ className, children, fill = false }: { className: string; children: ReactNode; fill?: boolean }) {
  const ref = useNoOrphan<HTMLDivElement>(fill);
  return <div className={className} ref={ref}>{children}</div>;
}
