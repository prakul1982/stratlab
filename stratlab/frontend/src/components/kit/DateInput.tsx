import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { addDays, addMonths, dayName, monthGrid, monthTitle, parseDay, showDay, whyNotDay } from "../../lib/dateInput";
import { istToday } from "../../lib/format";
import { Field } from "./Form";

const WEEK = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

/** The kit's calendar: one month of days in the kit's style, the month's name with the months either side, and Today. It opens under
 * its date box (owner, 7 Nov: the browser's own calendar "is so weird" in Safari and its button needed several clicks). Arrow keys move
 * a day or a week, Page Up and Page Down a month, Home and End the week's ends, Enter picks; Esc closes. Days before `min` or after
 * `max` can't be picked. */
export function DatePicker({ value, min, max, onPick, onClose, focusGrid, label, flip }: {
  value: string; min?: string; max?: string; onPick: (iso: string) => void; onClose: (back: boolean) => void;
  /** Focus goes onto a day as it opens (opened with its button or the down arrow), not left in the box being typed in. */
  focusGrid: boolean; label: string; flip: boolean;
}) {
  const today = istToday();
  const clamp = (d: string) => (min && d < min ? min : max && d > max ? max : d);
  const [at, setAt] = useState(() => clamp(value || today));       // the day with focus; its month is the month shown
  useEffect(() => { if (value) setAt(clamp(value)); }, [value]);   // eslint-disable-line react-hooks/exhaustive-deps
  const grid = useRef<HTMLDivElement>(null);
  const moved = useRef(focusGrid);
  if (focusGrid) moved.current = true;
  useEffect(() => {
    if (!moved.current) return;
    grid.current?.querySelector<HTMLElement>(`[data-day="${at}"]`)?.focus();
  }, [at, focusGrid]);
  const days = monthGrid(at);
  const month = at.slice(0, 7);
  const ok = (d: string) => !(min && d < min) && !(max && d > max);
  const go = (d: string) => { moved.current = true; setAt(clamp(d)); };
  const key = (e: KeyboardEvent) => {
    const k = e.key;
    const dow = (days.indexOf(at) % 7 + 7) % 7;
    const to = k === "ArrowLeft" ? addDays(at, -1) : k === "ArrowRight" ? addDays(at, 1) : k === "ArrowUp" ? addDays(at, -7) : k === "ArrowDown" ? addDays(at, 7)
      : k === "PageUp" ? addMonths(at, e.shiftKey ? -12 : -1) : k === "PageDown" ? addMonths(at, e.shiftKey ? 12 : 1)
      : k === "Home" ? addDays(at, -dow) : k === "End" ? addDays(at, 6 - dow) : null;
    if (to) { e.preventDefault(); go(to); }
  };
  const prevOk = !min || addDays(`${month}-01`, -1) >= min;
  const nextOk = !max || addMonths(`${month}-01`, 1) <= max;
  return (
    <div className={`k-cal${flip ? " flip" : ""}`} role="dialog" aria-label={label} aria-modal="false"
      onKeyDown={(e) => { if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(true); } }}>
      <div className="k-cal-head">
        <button type="button" className="k-cal-nav" aria-label="Previous month" disabled={!prevOk} onClick={() => go(addMonths(at, -1))}><span className="k-cal-arrow prev" aria-hidden="true" /></button>
        <span className="k-cal-title" aria-live="polite">{monthTitle(month)}</span>
        <button type="button" className="k-cal-nav" aria-label="Next month" disabled={!nextOk} onClick={() => go(addMonths(at, 1))}><span className="k-cal-arrow next" aria-hidden="true" /></button>
      </div>
      <div className="k-cal-grid" role="grid" aria-label={monthTitle(month)} ref={grid} onKeyDown={key}>
        <div role="row" className="k-cal-row">{WEEK.map((w) => <span key={w} role="columnheader" className="k-cal-dow">{w}</span>)}</div>
        {[0, 1, 2, 3, 4, 5].map((r) => (
          <div role="row" className="k-cal-row" key={r}>
            {days.slice(r * 7, r * 7 + 7).map((d) => (
              <span role="gridcell" key={d} aria-selected={d === value || undefined}>
                <button type="button" data-day={d} tabIndex={d === at ? 0 : -1} disabled={!ok(d)} aria-label={dayName(d)}
                  className={`k-cal-day${d.slice(0, 7) !== month ? " out" : ""}${d === value ? " on" : ""}${d === today ? " today" : ""}`}
                  onClick={() => onPick(d)}>{+d.slice(8)}</button>
              </span>
            ))}
          </div>
        ))}
      </div>
      <div className="k-cal-foot">
        <button type="button" className="btn quiet sm" disabled={!ok(today)} onClick={() => onPick(today)}>Today</button>
        {value && <span className="k-note">{showDay(value)}</span>}
      </div>
    </div>
  );
}

/** The one date box: it shows and reads the day first ("14 Aug 2025"; 14/08/2025 is 14 August), whatever language the
 * browser is in, with the kit's calendar under it (DatePicker): a click on the box or its calendar button opens it at once, the
 * down arrow opens it from the keyboard. `value` and `onChange` are calendar days, "YYYY-MM-DD" ("" for none). A day it can't
 * read, or one outside `min`/`max`, is said under the box and not passed on. */
export function DateInput({ id, value, onChange, min, max, ariaLabel, onProblem, placeholder = "e.g. 14 Aug 2025", describedBy, bad }: {
  id?: string; value: string; onChange: (iso: string) => void; min?: string; max?: string; ariaLabel?: string;
  /** Hears what's wrong with the typed text (null when it's fine), for the Field to show. */
  onProblem?: (problem: string | null) => void; placeholder?: string; describedBy?: string; bad?: boolean;
}) {
  const auto = useId();
  const fid = id ?? auto;
  const [text, setText] = useState(showDay(value));
  const sent = useRef(value);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [cal, setCal] = useState<null | { grid: boolean }>(null);
  const [flip, setFlip] = useState(false);
  // a new value from outside (a reset, a loaded record) shows; one this box just sent keeps the text as typed
  useEffect(() => { if (value !== sent.current) { sent.current = value; setText(showDay(value)); } }, [value]);

  const read = (t: string): { iso: string; problem: string | null } => {
    if (!t.trim()) return { iso: "", problem: null };
    const iso = parseDay(t);
    if (!iso) return { iso: "", problem: whyNotDay(t) };
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
  const pick = (iso: string) => {
    sent.current = iso; setText(showDay(iso)); onProblem?.(null); onChange(iso);
    setCal(null);
    input.current?.focus();
  };
  const close = (back: boolean) => { setCal(null); if (back) input.current?.focus(); };
  // a click or a tap anywhere else, or focus moving out, closes the calendar
  useEffect(() => {
    if (!cal) return;
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) setCal(null); };
    const focus = (e: FocusEvent) => { if (!box.current?.contains(e.target as Node)) setCal(null); };
    document.addEventListener("pointerdown", down);
    document.addEventListener("focusin", focus);
    return () => { document.removeEventListener("pointerdown", down); document.removeEventListener("focusin", focus); };
  }, [cal]);
  // a calendar that would run past the screen's right edge opens to the box's right end instead
  useLayoutEffect(() => {
    if (!cal || !box.current) { setFlip(false); return; }
    const r = box.current.getBoundingClientRect();
    setFlip(r.left + 296 > document.documentElement.clientWidth - 8 && r.right - 296 >= 8);
  }, [cal]);
  const typing = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown" && (e.altKey || !cal?.grid)) { e.preventDefault(); setCal({ grid: true }); }
    else if (e.key === "Escape" && cal) { e.preventDefault(); e.stopPropagation(); setCal(null); }
    else if (e.key === "Enter" && cal) setCal(null);
  };
  const typed = read(text).iso;
  const name = ariaLabel ? ariaLabel.toLowerCase() : "a date";
  return (
    <div className="k-date" ref={box}>
      <input ref={input} id={fid} className={`k-input${bad ? " bad" : ""}`} value={text} placeholder={placeholder} inputMode="text" autoComplete="off" aria-label={ariaLabel}
        aria-invalid={bad ? true : undefined} aria-describedby={describedBy}
        onChange={(e) => take(e.target.value)} onClick={() => { if (!cal) setCal({ grid: false }); }} onKeyDown={typing}
        onBlur={() => { const { iso, problem } = read(text); onProblem?.(problem); if (iso) setText(showDay(iso)); }} />
      <button type="button" className="k-date-btn" aria-label={`Pick ${name} on a calendar`} aria-expanded={!!cal} tabIndex={-1}
        onClick={() => setCal(cal ? null : { grid: true })}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
      </button>
      {cal && <DatePicker value={typed || value} min={min} max={max} onPick={pick} onClose={close} focusGrid={cal.grid} flip={flip}
        label={ariaLabel ? `Pick ${name}` : "Pick a date"} />}
    </div>
  );
}

/** A labelled date box in a FormGrid: Field + DateInput, with the problem said under it. */
export function DateField({ label, value, onChange, min, max, optional, info, wide, ariaLabel, hint, error, placeholder }: {
  label: string; value: string; onChange: (iso: string) => void; min?: string; max?: string; optional?: boolean; info?: ReactNode; wide?: boolean;
  ariaLabel?: string; hint?: string;
  /** the example in the empty box: a form for dates ahead gives a day ahead (DH-042: "e.g. 14 Aug 2025" in a calendar) */
  placeholder?: string;
  /** A problem the form found (a required day left empty, the server's check); the box's own reading comes first. */
  error?: string | null;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  const shown = problem ?? error ?? null;
  return (
    <Field label={label} optional={optional} info={info} wide={wide} error={shown} hint={hint}>
      {(id) => <DateInput id={id} value={value} onChange={onChange} min={min} max={max} ariaLabel={ariaLabel} onProblem={setProblem} placeholder={placeholder}
        bad={!!shown} describedBy={shown || hint ? `${id}-msg` : undefined} />}
    </Field>
  );
}
