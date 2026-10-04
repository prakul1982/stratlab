import { useEffect, useId, useRef, useState } from "react";
import { api } from "../lib/api";

export type Suggestion = { symbol: string; id: string; name: string; exchange: string; market: "IN" | "US" };
type Market = "IN" | "US" | "ALL";

const cache = new Map<string, Suggestion[]>();

/** Listed companies for what's typed, up to 8 (the same answer is reused while the page is open). */
async function suggestions(q: string, market: Market): Promise<Suggestion[]> {
  const key = `${market}:${q.toUpperCase()}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const r = await api<{ rows: Suggestion[] }>(`/suggest/companies?q=${encodeURIComponent(q)}${market === "ALL" ? "" : `&market=${market}`}`);
  if (cache.size > 300) cache.clear();
  cache.set(key, r.rows);
  return r.rows;
}

/** A symbol box that suggests listed companies while typing: ↑ ↓ to move, Enter to pick, Esc to close. Picking
 * fills the identifier to save (NSE symbol, else BSE code; US ticker); an exact symbol can still be typed freely. */
export function CompanyCombobox({ label, value, onChange, onPick, market = "ALL", placeholder, hint, maxLength = 20, onEnter }: {
  label: string; value: string; onChange: (text: string) => void; onPick: (s: Suggestion) => void; market?: Market;
  placeholder?: string; hint?: string; maxLength?: number; onEnter?: () => void;
}) {
  const id = useId();
  const listId = `${id}-list`;
  const [rows, setRows] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [typed, setTyped] = useState(false);         // only suggest after the person types, not when a pick fills the box
  const asked = useRef(0);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const q = value.trim();
    if (!typed || !q) { setRows([]); setOpen(false); return; }
    const n = ++asked.current;
    const t = window.setTimeout(() => {
      suggestions(q.slice(0, 40), market).then((r) => {
        if (n !== asked.current) return;              // a later keystroke has its own answer coming
        setRows(r); setActive(-1); setOpen(document.activeElement === box.current);    // not after the person has moved on
      }).catch(() => { if (n === asked.current) { setRows([]); setOpen(false); } });
    }, 200);
    return () => window.clearTimeout(t);
  }, [value, market, typed]);

  const pick = (s: Suggestion) => {
    setTyped(false); setOpen(false); setRows([]); setActive(-1);
    onPick(s);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!open && rows.length) setOpen(true);
      setActive((a) => (rows.length ? (a + 1) % rows.length : -1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (rows.length ? (a <= 0 ? rows.length - 1 : a - 1) : -1));
    } else if (e.key === "Enter") {
      if (open && active >= 0 && rows[active]) { e.preventDefault(); pick(rows[active]); }
      else if (onEnter) { e.preventDefault(); setOpen(false); onEnter(); }
    } else if (e.key === "Escape") {
      if (open) { e.preventDefault(); e.stopPropagation(); setOpen(false); setActive(-1); }
    }
  };

  const shown = open && value.trim().length > 0;
  return (
    <div className="field combo">
      <label htmlFor={id}>{label}</label>
      <div className="combo-box">
        <input ref={box} id={id} value={value} maxLength={maxLength} placeholder={placeholder} autoComplete="off" autoCapitalize="characters" spellCheck={false}
          role="combobox" aria-expanded={shown} aria-controls={listId} aria-autocomplete="list"
          aria-activedescendant={shown && active >= 0 ? `${id}-opt-${active}` : undefined}
          onChange={(e) => { setTyped(true); onChange(e.target.value); }} onKeyDown={onKeyDown}
          onFocus={() => { if (rows.length && typed) setOpen(true); }} onBlur={() => window.setTimeout(() => setOpen(false), 120)} />
        <ul id={listId} role="listbox" aria-label="Suggestions" className="combo-list" hidden={!shown}>
          {shown && rows.map((r, i) => (
            <li key={`${r.market}:${r.id}`} id={`${id}-opt-${i}`} role="option" aria-selected={i === active} className={i === active ? "on" : undefined}
              onMouseDown={(e) => e.preventDefault()} onClick={() => pick(r)} onMouseMove={() => setActive(i)}>
              <span className="combo-text"><b>{r.name}</b><span className="tiny muted">{r.symbol}{r.id !== r.symbol ? ` · BSE code ${r.id}` : ""}{r.market === "US" ? " · United States" : " · India"}</span></span>
              <span className={`badge ${r.market === "US" ? "next" : "fact"}`}>{r.market === "US" ? "US" : r.exchange}</span>
            </li>
          ))}
          {shown && rows.length === 0 && <li className="combo-none" role="presentation">No listed company matches. An exact symbol still works.</li>}
        </ul>
      </div>
      <span className="sr-only" aria-live="polite">{shown ? `${rows.length} suggestion${rows.length === 1 ? "" : "s"}` : ""}</span>
      {hint && <span className="hint">{hint}</span>}
    </div>
  );
}
