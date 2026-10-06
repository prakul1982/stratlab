import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export type SuggestItem = { key: string; label: string; note?: string; tag?: string };

const initials = (s: string) => s.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "–";

/** The box for typing a name that is not a listed company (a fund or a person, say), with suggestions as you type: the
 * same look and keys as StockPicker. `load` answers for what is typed (called a moment after the last key, from `minChars`
 * letters); up and down move, Enter picks the marked one (or submits the text when nothing is marked), Esc closes.
 * `onText` hears every change; `onPick` hears a choice from the list. `empty` is the line shown when nothing matches. */
export function Suggest({ id, value = "", load, onPick, onText, onSubmit, minChars = 3, placeholder, empty = "No name matches that.", label }: {
  id?: string; value?: string; load: (q: string) => Promise<SuggestItem[]>; onPick: (item: SuggestItem) => void; onText?: (text: string) => void;
  onSubmit?: (text: string) => void; minChars?: number; placeholder?: string; empty?: string; label?: string;
}) {
  const auto = useId();
  const fid = id ?? auto;
  const listId = `${fid}-list`;
  const [text, setText] = useState(value);
  const [typed, setTyped] = useState(false);
  const [rows, setRows] = useState<SuggestItem[]>([]);
  const [open, setOpen] = useState(false);
  const [on, setOn] = useState(-1);
  const asked = useRef(0);
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => { setText(value); setTyped(false); }, [value]);

  useEffect(() => {
    const q = text.trim();
    if (!typed || q.length < minChars) { setRows([]); setOpen(false); return; }
    const n = ++asked.current;
    const t = window.setTimeout(() => {
      load(q).then((r) => {
        if (n !== asked.current) return;
        setRows(r.slice(0, 8)); setOn(-1); setOpen(document.activeElement === box.current);
      }).catch(() => { if (n === asked.current) { setRows([]); setOpen(false); } });
    }, 220);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, typed, minChars]);

  const pick = (s: SuggestItem) => {
    asked.current++;
    setOpen(false); setRows([]); setTyped(false); setOn(-1);
    setText(s.label);
    onPick(s);
  };
  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!open && rows.length) setOpen(true); setOn((a) => (rows.length ? (a + 1) % rows.length : -1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setOn((a) => (rows.length ? (a <= 0 ? rows.length - 1 : a - 1) : -1)); }
    else if (e.key === "Enter") {
      if (open && on >= 0 && rows[on]) { e.preventDefault(); pick(rows[on]); }
      else if (onSubmit) { e.preventDefault(); asked.current++; setOpen(false); onSubmit(text.trim()); }
    }
    else if (e.key === "Escape" && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); }
  };
  const shown = open && text.trim().length >= minChars;
  return (
    <div className="k-picker">
      <svg className="lens" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input ref={box} id={fid} className="k-input" type="search" value={text} placeholder={placeholder} autoComplete="off" spellCheck={false} maxLength={80} aria-label={label}
        role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown && rows[on] ? `${fid}-o${on}` : undefined}
        onChange={(e) => { setTyped(true); setText(e.target.value); onText?.(e.target.value); }} onKeyDown={key}
        onFocus={() => { if (typed && rows.length) setOpen(true); }} onBlur={() => window.setTimeout(() => setOpen(false), 120)} />
      <ul id={listId} role="listbox" aria-label="Suggestions" className="k-suggest" hidden={!shown}>
        {shown && rows.map((r, i) => (
          <li key={r.key} id={`${fid}-o${i}`} role="option" aria-selected={i === on} className={`k-sug${i === on ? " on" : ""}`}
            onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)} onMouseMove={() => setOn(i)}>
            <span className="k-logo" aria-hidden="true">{initials(r.label)}</span>
            <span className="k-sug-t"><b>{r.label}</b>{r.note && <span>{r.note}</span>}</span>
            {r.tag && <span className="k-sug-x">{r.tag}</span>}
          </li>
        ))}
        {shown && rows.length === 0 && <li className="k-sug-none" role="presentation">{empty}</li>}
      </ul>
      <span className="sr-only" aria-live="polite">{shown ? `${rows.length} suggestion${rows.length === 1 ? "" : "s"}` : ""}</span>
    </div>
  );
}
