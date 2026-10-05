import { useState, type ReactElement } from "react";

const read = (k: string) => { try { return localStorage.getItem(k) === "1"; } catch { return false; } };
const write = (k: string, v: boolean) => { try { localStorage.setItem(k, v ? "1" : "0"); } catch { /* private mode */ } };

/** A wide table shows the columns its page is for, and keeps the rest one click away: `on` says whether the extra
 * columns are showing, and `toggle` is the button that shows or hides them. Remembered per table, so a table that
 * fits a laptop screen without a sideways swipe stays that way, and one opened up stays open. */
export function useMoreColumns(id: string, extra: number): { on: boolean; toggle: ReactElement } {
  const key = `stratlab.cols.${id}`;
  const [on, setOn] = useState(() => read(key));
  const flip = () => { setOn(!on); write(key, !on); };
  const toggle = (
    <button type="button" className="btn quiet sm more-cols" aria-pressed={on} onClick={flip} data-testid={`cols-${id}`}
      title={on ? "Hide the extra columns" : `Show ${extra} more column${extra === 1 ? "" : "s"}`}>
      {on ? "Fewer columns" : `More columns (${extra})`}
    </button>
  );
  return { on, toggle };
}
