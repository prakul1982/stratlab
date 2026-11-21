import { useEffect, useRef, useState, type ReactNode } from "react";

/** Several things that can each be on or off (which categories to show): chips you press, in a labelled group.
 * (One choice among a few is a Seg; one among many a ChipBar.) */
export function ChipSet({ label, options, on, onToggle }: { label: string; options: { value: string; label: string }[]; on: string[]; onToggle: (v: string) => void }) {
  return (
    <div className="k-chipset" role="group" aria-label={label}>
      {options.map((o) => <button key={o.value} type="button" className="k-chip" aria-pressed={on.includes(o.value)} onClick={() => onToggle(o.value)}>{o.label}</button>)}
    </div>
  );
}

/** One yes/no with its words beside it. */
export function CheckField({ label, checked, onChange, disabled }: { label: ReactNode; checked: boolean; onChange: (on: boolean) => void; disabled?: boolean }) {
  return (
    <label className="k-check"><input type="checkbox" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />{label}</label>
  );
}

/** SEARCH FILINGS (site87, owner: "what is this UI": a Sector column of four rows of chips beside a one-box Companies column): several
 * choices from a long list as one control the height of a box: it says what is picked ("All sectors", "Energy", "3 sectors") and opens a
 * list of tick boxes under it. Closes on a click outside or Escape. */
export function MultiPick({ id, label, options, on, onToggle, onClear, all, noun }: {
  id?: string; label: string; options: { value: string; label: string }[]; on: string[]; onToggle: (v: string) => void; onClear?: () => void;
  /** what nothing picked means ("All sectors") */ all: string; /** the plural word for a count ("sectors") */ noun: string;
}) {
  const box = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const away = (e: Event) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); box.current?.querySelector("summary")?.focus(); } };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("pointerdown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  const names = options.filter((o) => on.includes(o.value)).map((o) => o.label);
  const said = !names.length ? all : names.length === 1 ? names[0] : `${names.length} ${noun}`;
  return (
    <details ref={box} className="k-multi" open={open} onToggle={(e) => setOpen((e.currentTarget as HTMLDetailsElement).open)}>
      <summary id={id} className={`k-input k-multi-btn${names.length ? " on" : ""}`} aria-label={`${label}: ${said}`}>
        <span className="k-multi-said">{said}</span><span className="k-multi-caret" aria-hidden="true" />
      </summary>
      <div className="k-multi-pop" role="group" aria-label={label}>
        {options.map((o) => (
          <label key={o.value} className="k-check k-multi-opt"><input type="checkbox" checked={on.includes(o.value)} onChange={() => onToggle(o.value)} />{o.label}</label>
        ))}
        {onClear && names.length > 0 && <button type="button" className="btn quiet sm k-multi-clear" onClick={onClear}>Clear</button>}
      </div>
    </details>
  );
}
