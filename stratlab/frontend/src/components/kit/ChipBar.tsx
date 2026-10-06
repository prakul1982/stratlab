import { useEffect, useRef, useState } from "react";
import type { Choice } from "./Seg";

export type CustomUnit = { value: string; label: string; plural?: string };

function load(key: string): Choice[] {
  try {
    const raw = JSON.parse(localStorage.getItem(key) ?? "[]");
    return Array.isArray(raw) ? raw.filter((o): o is Choice => typeof o?.value === "string" && typeof o?.label === "string").slice(-8) : [];
  } catch { return []; }
}
function save(key: string, list: Choice[]) {
  try { localStorage.setItem(key, JSON.stringify(list)); } catch { /* storage off: the choice still works for this visit */ }
}

/** Many choices in one scrolling row of chips (timeframes, ranges of more than four). With `custom`, a dashed "+ Custom"
 * chip opens a number and unit box; what is added joins the row and is remembered on this device under `custom.storageKey`
 * (the chip's value is "35 minutes"-style text: `${n} ${unit.value}`). */
export function ChipBar({ label, options, value, onChange, custom }: {
  label: string; options: Choice[]; value: string; onChange: (v: string) => void;
  custom?: { storageKey: string; units: CustomUnit[]; defaultUnit?: string; max?: number };
}) {
  const [mine, setMine] = useState<Choice[]>(() => (custom ? load(custom.storageKey) : []));
  const [open, setOpen] = useState(false);
  const [n, setN] = useState("");
  const [unit, setUnit] = useState(custom?.defaultUnit ?? custom?.units[0]?.value ?? "");
  const num = useRef<HTMLInputElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) num.current?.focus(); }, [open]);

  const all = [...options, ...mine.filter((m) => !options.some((o) => o.value === m.value))];
  const count = Number(n);
  const valid = Number.isInteger(count) && count >= 1 && count <= 999;
  const add = () => {
    if (!custom || !valid) return;
    const u = custom.units.find((x) => x.value === unit);
    if (!u) return;
    const opt: Choice = { value: `${count} ${u.value}`, label: `${count} ${count === 1 ? u.label : u.plural ?? u.label}` };
    if (!all.some((o) => o.value === opt.value)) {
      const next = [...mine, opt].slice(-(custom.max ?? 8));
      setMine(next);
      save(custom.storageKey, next);
    }
    onChange(opt.value);
    setOpen(false);
    setN("");
    window.requestAnimationFrame(() => opener.current?.focus());
  };
  return (
    <div className="k-chipwrap">
      <div className="k-chipbar" role="group" aria-label={label}>
        {all.map((o) => <button key={o.value} type="button" className="k-chip" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>{o.label}</button>)}
        {custom && <button ref={opener} type="button" className="k-chip add" aria-expanded={open} onClick={() => setOpen((x) => !x)}>+ Custom</button>}
      </div>
      {custom && open && (
        <div className="k-custom" role="group" aria-label="Custom choice">
          <input ref={num} className="k-input" inputMode="numeric" placeholder="35" value={n} aria-label="How many" aria-invalid={n !== "" && !valid}
            onChange={(e) => setN(e.target.value.replace(/\D/g, "").slice(0, 3))}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } else if (e.key === "Escape") { e.preventDefault(); setOpen(false); opener.current?.focus(); } }} />
          <select className="k-input" aria-label="Unit" value={unit} onChange={(e) => setUnit(e.target.value)}>
            {custom.units.map((u) => <option key={u.value} value={u.value}>{u.plural ?? u.label}</option>)}
          </select>
          <button type="button" className="btn sm" disabled={!valid} onClick={add}>Use this</button>
        </div>
      )}
    </div>
  );
}
