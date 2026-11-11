/* Adding to a list (MW-2; owner, 9 Nov: "while adding something why is it so cluttered"). One search field over every market the
 * app covers, and its results in the panel's own list area: symbol, name and exchange on each row, the arrow keys to move, Enter or
 * a click to add, and one line that says what came of it. Added, the search ends and the field is ready for the next one, with the
 * new row marked on the list; not added (there already, or the list is full), the results stay with the reason over them. No market
 * picker and no rows of quick picks beside the field. */
import { useCallback, useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { api } from "../../lib/api";
import { useApp } from "../../lib/app";
import type { Instrument } from "../../lib/types";
import { addRows, stepRow, type AddRow, type WatchItem } from "../../lib/watch";
import { Close, Plus, Search } from "../Icons";
import { Working } from "../kit/States";

const SAID_MS = 6000;

export interface AddSearch {
  q: string; type: (v: string) => void; clear: () => void; focus: () => void;
  /** Enough is typed for a search: the panel's list area shows the results instead of the list. */
  active: boolean; busy: boolean; searched: boolean;
  rows: AddRow[]; on: number; setOn: (i: number) => void; add: (r: AddRow) => void;
  said: { ok: boolean; text: string } | null;
  key: (e: KeyboardEvent<HTMLInputElement>) => void;
  input: RefObject<HTMLInputElement | null>; listId: string;
}

/** The search's state, shared by the field (in the panel's bar) and the results (in its list area). `has` says what the open list
 * holds, `onAdd` adds one and answers with what happened; `listKey` is the open list, so its line is not said about another. */
export function useAddSearch(has: (id: string) => boolean, onAdd: (it: WatchItem) => { ok: boolean; text: string }, listKey: string): AddSearch {
  const { fail } = useApp();
  const [q, setQ] = useState("");
  const [found, setFound] = useState<Instrument[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [on, setOn] = useState(-1);
  const [said, setSaid] = useState<AddSearch["said"]>(null);
  const input = useRef<HTMLInputElement>(null);
  const asked = useRef(0);
  const listId = `${useId()}-found`;
  const term = q.trim();
  const active = term.length >= 2;

  useEffect(() => {
    const n = ++asked.current;
    if (!active) { setFound(null); setBusy(false); setOn(-1); return; }
    setBusy(true);
    const timer = window.setTimeout(async () => {
      try {
        const got = await api<Instrument[]>(`/instruments/search?q=${encodeURIComponent(term)}`);       // no market named: every market at once
        if (n === asked.current) { setFound(got); setOn(got.length ? 0 : -1); setBusy(false); }
      } catch (e) { if (n === asked.current) { setFound([]); setBusy(false); fail(e); } }
    }, 250);
    return () => window.clearTimeout(timer);
  }, [term, active, fail]);
  useEffect(() => { setSaid(null); }, [listKey]);
  // "Added INFY to your watchlist." is said for a few seconds: by then the row itself is on the list
  useEffect(() => {
    if (!said?.ok) return;
    const t = window.setTimeout(() => setSaid(null), SAID_MS);
    return () => window.clearTimeout(t);
  }, [said]);

  const rows = useMemo(() => (found ? addRows(found, has) : []), [found, has]);
  const type = useCallback((v: string) => { setQ(v); setSaid(null); }, []);
  const clear = useCallback(() => { setQ(""); setSaid(null); }, []);
  const add = useCallback((r: AddRow) => {
    const out = onAdd(r.item);
    setSaid(out);
    if (out.ok) setQ("");          // added: back to the list, the field ready for the next one
  }, [onAdd]);
  const key = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!rows.length) return;
      e.preventDefault();
      const to = stepRow(on, rows.length, e.key);
      setOn(to);
      document.getElementById(`${listId}-${to}`)?.scrollIntoView({ block: "nearest" });
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!busy && rows[on]) add(rows[on]);          // not while the rows are still those of what was typed before
    } else if (e.key === "Escape" && q) {          // the first Esc ends the search; the panel takes the next one
      e.preventDefault(); e.stopPropagation();
      clear();
    }
  };
  return { q, type, clear, focus: () => input.current?.focus(), active, busy, searched: found !== null, rows, on: Math.min(on, rows.length - 1), setOn, add, said, key, input, listId };
}

/** The one field: type a name or a ticker. */
export function AddField({ s, disabled }: { s: AddSearch; disabled?: boolean }) {
  const shown = s.active && s.rows.length > 0;
  return (
    <div className="mw-search">
      <Search size={16} />
      <input ref={s.input} value={s.q} disabled={disabled} autoComplete="off" spellCheck={false} enterKeyHint="search" aria-label="Search to add a symbol"
        placeholder="Add a symbol: name or ticker" role="combobox" aria-expanded={s.active} aria-controls={s.listId} aria-autocomplete="list"
        aria-activedescendant={shown && s.on >= 0 ? `${s.listId}-${s.on}` : undefined} onChange={(e) => s.type(e.target.value)} onKeyDown={s.key} />
      {s.q && <button type="button" className="mw-search-x" aria-label="Clear the search" title="Clear the search" onClick={() => { s.clear(); s.focus(); }}><Close size={14} /></button>}
    </div>
  );
}

/** The line that says what came of a search or an add: over the results while searching, over the list for a few seconds after. */
export function AddSaid({ s }: { s: AddSearch }) {
  const none = s.active && s.searched && !s.busy && s.rows.length === 0;
  // how to pick, in the words of what is in the hand: keys with a keyboard, a tap on a touch screen
  const touch = typeof window.matchMedia === "function" && window.matchMedia("(pointer: coarse)").matches;
  return (
    <p className={`mw-said${s.said ? (s.said.ok ? " ok" : " no") : ""}`} role="status" data-testid="mw-said">
      {s.said ? s.said.text : none ? `Nothing the app covers matches "${s.q.trim()}". Try the ticker, or part of the name.` : s.active && s.rows.length ? touch ? "Tap a result to add it to this list" : "↑ ↓ to move · Enter adds · Esc ends the search" : ""}
    </p>
  );
}

/** What the search found, in the list area: a row an instrument. */
export function AddResults({ s }: { s: AddSearch }) {
  return (
    <div className="mw-results" data-testid="mw-results">
      {s.busy && s.rows.length === 0 && <div className="mw-pad"><Working label="Searching every market" small /></div>}
      <ul id={s.listId} className="mw-found" role="listbox" aria-label="Search results">
        {s.rows.map((r, i) => (
          <li key={r.item.id} id={`${s.listId}-${i}`} role="option" aria-selected={i === s.on} className={`mw-f${i === s.on ? " on" : ""}${r.on ? " have" : ""}`}
            onMouseDown={(e) => e.preventDefault()} onMouseMove={() => { if (i !== s.on) s.setOn(i); }} onClick={() => s.add(r)}>
            <span className="mw-f-name"><b>{r.symbol}</b><small>{r.name || r.kind}</small></span>
            <span className="mw-f-ex">{r.exchange}</span>
            <span className="mw-f-act">{r.on ? "On this list" : <Plus size={16} />}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
