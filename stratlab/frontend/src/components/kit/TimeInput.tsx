import { useEffect, useState } from "react";
import { parseClock as parseTime } from "../../lib/format";

/** A time of day in the app's one clock, 24-hour ("14:45"), with the zone it is in written beside the box ("IST").
 * The browser's own time box follows the reader's locale and can show "02:45 PM", so this is a plain text box that
 * keeps what is typed until it reads as a time. `small` for a box inside a sentence; `allowEmpty` lets it be cleared. */
export function TimeInput({ id, label, value, onChange, zone, small, allowEmpty, onEnter, onInvalid }: {
  id?: string; label?: string; value: string; onChange: (v: string) => void; zone?: string; small?: boolean; allowEmpty?: boolean; onEnter?: () => void;
  /** told what was typed when the box is left holding something that isn't a time, and goes back to `value` (DB-004:
   * "25:00" went back to 09:30 without a word) */
  onInvalid?: (typed: string) => void;
}) {
  const [txt, setTxt] = useState(value);
  // a new value from outside replaces the text, but not the value this box has just sent (mid-typing)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (parseTime(txt) !== value) setTxt(value); }, [value]);
  return (
    <span className={`k-time${small ? " sm" : ""}`}>
      <input id={id} className={`k-input k-time-box${small ? " sm" : ""}`} type="text" inputMode="numeric" autoComplete="off" placeholder="HH:MM"
        maxLength={5} aria-label={label ? `${label}${zone ? ` (${zone}, 24-hour)` : " (24-hour)"}` : undefined} value={txt}
        onChange={(e) => {
          setTxt(e.target.value);
          const t = parseTime(e.target.value);
          if (t) onChange(t);
          else if (allowEmpty && e.target.value.trim() === "") onChange("");
        }}
        onKeyDown={(e) => { if (e.key === "Enter" && onEnter) onEnter(); }}
        onBlur={() => {
          const t = parseTime(txt);
          const empty = allowEmpty && txt.trim() === "";
          if (!t && !empty && txt.trim() && txt !== value) onInvalid?.(txt);
          setTxt(t ?? (empty ? "" : value));
        }} />
      {zone && <span className="k-time-zone" aria-hidden="true">{zone}</span>}
    </span>
  );
}
