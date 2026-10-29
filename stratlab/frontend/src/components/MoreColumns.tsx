import { useState, type ReactElement } from "react";

const stored = (k: string): boolean | null => { try { const v = localStorage.getItem(k); return v === "1" ? true : v === "0" ? false : null; } catch { return null; } };
const write = (k: string, v: boolean) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch { /* private mode */ } };

/** The window width from which a `wide` table opens with every column. */
export const WIDE_FROM = 1280;

/** A wide table shows the columns its page is for, and keeps the rest one click away: `on` says whether the extra
 * columns are showing, and `toggle` is the button that shows or hides them. Remembered per table, so a table that
 * fits a laptop screen without a sideways swipe stays that way, and one opened up stays open. `wide`: a table that fits a
 * laptop in full (the tax report's sales: LIVE1B-012 had its purchase date and quantity folded at 1440px) opens with every
 * column from 1280px up, until the person chooses. */
export function useMoreColumns(id: string, extra: number, wide = false): { on: boolean; toggle: ReactElement } {
  const key = `stratlab.cols.${id}`;
  const [on, setOn] = useState(() => stored(key) ?? (wide && typeof window !== "undefined" && window.innerWidth >= WIDE_FROM));
  const flip = () => { setOn(!on); write(key, !on); };
  const toggle = (
    <button type="button" className="btn quiet sm more-cols" aria-pressed={on} onClick={flip} data-testid={`cols-${id}`}
      title={on ? "Hide the extra columns" : `Show ${extra} more column${extra === 1 ? "" : "s"}`}>
      {on ? "Fewer columns" : `More columns (${extra})`}
    </button>
  );
  return { on, toggle };
}
