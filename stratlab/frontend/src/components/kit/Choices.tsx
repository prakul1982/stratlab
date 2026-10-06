import type { ReactNode } from "react";

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
