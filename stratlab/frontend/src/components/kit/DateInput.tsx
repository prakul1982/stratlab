import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { parseDay, showDay } from "../../lib/dateInput";
import { Field } from "./Form";

/** The one date box: it shows and reads the day first ("14 Aug 2025"; 14/08/2025 is 14 August), whatever language the
 * browser is in, with a button for the browser's own calendar. `value` and `onChange` are calendar days, "YYYY-MM-DD"
 * ("" for none). A day it can't read, or one outside `min`/`max`, is said under the box and not passed on. */
export function DateInput({ id, value, onChange, min, max, ariaLabel, onProblem, placeholder = "e.g. 14 Aug 2025", describedBy, bad }: {
  id?: string; value: string; onChange: (iso: string) => void; min?: string; max?: string; ariaLabel?: string;
  /** Hears what's wrong with the typed text (null when it's fine), for the Field to show. */
  onProblem?: (problem: string | null) => void; placeholder?: string; describedBy?: string; bad?: boolean;
}) {
  const auto = useId();
  const fid = id ?? auto;
  const [text, setText] = useState(showDay(value));
  const sent = useRef(value);
  const native = useRef<HTMLInputElement>(null);
  // a new value from outside (a reset, a loaded record) shows; one this box just sent keeps the text as typed
  useEffect(() => { if (value !== sent.current) { sent.current = value; setText(showDay(value)); } }, [value]);

  const read = (t: string): { iso: string; problem: string | null } => {
    if (!t.trim()) return { iso: "", problem: null };
    const iso = parseDay(t);
    if (!iso) return { iso: "", problem: "Write the date day first, like 14 Aug 2025 or 14/08/2025." };
    if (min && iso < min) return { iso: "", problem: `Pick a day from ${showDay(min)}.` };
    if (max && iso > max) return { iso: "", problem: `Pick a day up to ${showDay(max)}.` };
    return { iso, problem: null };
  };
  const take = (t: string) => {
    setText(t);
    const { iso, problem } = read(t);
    onProblem?.(problem && t.trim().length >= 6 ? problem : null);       // no complaint while the first characters go in
    if (iso !== sent.current) { sent.current = iso; onChange(iso); }
  };
  const openCalendar = () => {
    const n = native.current;
    if (!n) return;
    try { n.showPicker(); } catch { n.focus(); }
  };
  return (
    <div className="k-date">
      <input id={fid} className={`k-input${bad ? " bad" : ""}`} value={text} placeholder={placeholder} inputMode="text" autoComplete="off" aria-label={ariaLabel}
        aria-invalid={bad ? true : undefined} aria-describedby={describedBy}
        onChange={(e) => take(e.target.value)}
        onBlur={() => { const { iso, problem } = read(text); onProblem?.(problem); if (iso) setText(showDay(iso)); }} />
      <button type="button" className="k-date-btn" aria-label={`Pick ${ariaLabel ? ariaLabel.toLowerCase() : "a date"} on a calendar`} onClick={openCalendar} tabIndex={-1}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
      </button>
      <input ref={native} type="date" className="k-date-native" tabIndex={-1} aria-hidden="true" value={value} min={min} max={max}
        onChange={(e) => { const iso = e.target.value; sent.current = iso; setText(showDay(iso)); onProblem?.(null); onChange(iso); }} />
    </div>
  );
}

/** A labelled date box in a FormGrid: Field + DateInput, with the problem said under it. */
export function DateField({ label, value, onChange, min, max, optional, info, wide, ariaLabel, hint, error }: {
  label: string; value: string; onChange: (iso: string) => void; min?: string; max?: string; optional?: boolean; info?: ReactNode; wide?: boolean;
  ariaLabel?: string; hint?: string;
  /** A problem the form found (a required day left empty, the server's check); the box's own reading comes first. */
  error?: string | null;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  const shown = problem ?? error ?? null;
  return (
    <Field label={label} optional={optional} info={info} wide={wide} error={shown} hint={hint}>
      {(id) => <DateInput id={id} value={value} onChange={onChange} min={min} max={max} ariaLabel={ariaLabel} onProblem={setProblem}
        bad={!!shown} describedBy={shown || hint ? `${id}-msg` : undefined} />}
    </Field>
  );
}
