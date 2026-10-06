import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { suggestions, type Market, type Suggestion } from "../CompanyCombobox";

const initials = (s: Suggestion) => s.symbol.replace(/[^A-Za-z0-9]/g, "").slice(0, 2).toUpperCase() || "–";

/** The one box for typing a stock. It suggests listed companies as you type (the same list as the rest of the app): a
 * logo-initials tile, the symbol, the name and the exchange. Up and down move, Enter picks, Esc closes. Picking, or
 * pressing Enter on an exact symbol you typed, calls `onPick(symbol, region)`.
 * `value` is the symbol the page is showing now; the box shows it until you type. Give it an `id` (a Field does) so
 * its label points at it. */
export function StockPicker({ value = "", onPick, market = "IN", id, placeholder = "Search by name or symbol, like RELIANCE", clearOnPick, autoFocus }: {
  value?: string; onPick: (symbol: string, region: "IN" | "US") => void; market?: Market; id?: string; placeholder?: string; clearOnPick?: boolean; autoFocus?: boolean;
}) {
  const auto = useId();
  const fid = id ?? auto;
  const listId = `${fid}-list`;
  const [text, setText] = useState(value);
  const [typed, setTyped] = useState(false);
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [on, setOn] = useState(0);
  const asked = useRef(0);
  const box = useRef<HTMLInputElement>(null);
  useEffect(() => { setText(value); setTyped(false); }, [value]);

  useEffect(() => {
    const q = text.trim();
    if (!typed || !q) { setRows([]); setOpen(false); return; }
    const n = ++asked.current;
    const t = window.setTimeout(() => {
      suggestions(q.slice(0, 40), market).then((r) => {
        if (n !== asked.current) return;
        setRows(r); setOn(0); setOpen(document.activeElement === box.current);
      }).catch(() => { if (n === asked.current) { setRows([]); setOpen(false); } });
    }, 200);
    return () => window.clearTimeout(t);
  }, [text, market, typed]);

  const pick = (s: Suggestion) => {
    asked.current++;
    setOpen(false); setRows([]); setTyped(false);
    setText(clearOnPick ? "" : s.id);
    onPick(s.id, s.market);
  };
  const exact = () => {
    const s = text.trim().toUpperCase();
    if (!/^[A-Z0-9&.-]{1,20}$/.test(s)) return;
    asked.current++;
    setOpen(false); setTyped(false);
    setText(clearOnPick ? "" : s);
    onPick(s, market === "US" ? "US" : "IN");
  };
  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") { e.preventDefault(); if (!open && rows.length) setOpen(true); setOn((a) => (rows.length ? (a + 1) % rows.length : 0)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setOn((a) => (rows.length ? (a - 1 + rows.length) % rows.length : 0)); }
    else if (e.key === "Enter") { e.preventDefault(); if (open && rows[on]) pick(rows[on]); else exact(); }
    else if (e.key === "Escape" && open) { e.preventDefault(); e.stopPropagation(); setOpen(false); }
  };
  const shown = open && text.trim().length > 0;
  return (
    <div className="k-picker">
      <svg className="lens" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
      <input ref={box} id={fid} className="k-input" value={text} placeholder={placeholder} autoFocus={autoFocus} autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={40}
        role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list" aria-activedescendant={shown && rows[on] ? `${fid}-o${on}` : undefined}
        onChange={(e) => { setTyped(true); setText(e.target.value); }} onKeyDown={key}
        onFocus={() => { if (typed && rows.length) setOpen(true); }} onBlur={() => window.setTimeout(() => setOpen(false), 120)} />
      <ul id={listId} role="listbox" aria-label="Suggestions" className="k-suggest" hidden={!shown}>
        {shown && rows.map((r, i) => (
          <li key={`${r.market}:${r.id}`} id={`${fid}-o${i}`} role="option" aria-selected={i === on} className={`k-sug${i === on ? " on" : ""}`}
            onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)} onMouseMove={() => setOn(i)}>
            <span className="k-logo" aria-hidden="true">{initials(r)}</span>
            <span className="k-sug-t"><b>{r.symbol}</b><span>{r.name}{r.id !== r.symbol ? ` · BSE code ${r.id}` : ""}</span></span>
            <span className="k-sug-x">{r.market === "US" ? "US" : r.exchange}</span>
          </li>
        ))}
        {shown && rows.length === 0 && <li className="k-sug-none" role="presentation">No listed company matches. An exact symbol still works: press Enter.</li>}
      </ul>
      <span className="sr-only" aria-live="polite">{shown ? `${rows.length} suggestion${rows.length === 1 ? "" : "s"}` : ""}</span>
    </div>
  );
}
