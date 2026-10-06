import { useRef, type KeyboardEvent } from "react";

export type Choice = { value: string; label: string; disabled?: boolean };

/** A switch for 2 to 4 choices, as wide as its choices and never stretched. A radio group for screen readers: one tab
 * stop, arrow keys move and choose. More than four choices belong in a ChipBar. `label` names the group ("Range"). */
export function Seg({ label, options, value, onChange }: { label: string; options: Choice[]; value: string; onChange: (v: string) => void }) {
  const box = useRef<HTMLDivElement>(null);
  if (import.meta.env.DEV && (options.length < 2 || options.length > 4)) console.warn(`Seg "${label}" has ${options.length} choices; use 2 to 4 (a ChipBar for more).`);
  const enabled = options.filter((o) => !o.disabled);
  const stop = enabled.some((o) => o.value === value) ? value : enabled[0]?.value;
  const key = (e: KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step || !enabled.length) return;
    e.preventDefault();
    const at = enabled.findIndex((o) => o.value === value);
    const next = enabled[(at + step + enabled.length) % enabled.length];
    onChange(next.value);
    window.requestAnimationFrame(() => box.current?.querySelector<HTMLElement>(`[data-v="${CSS.escape(next.value)}"]`)?.focus());
  };
  return (
    <div className="k-seg" role="radiogroup" aria-label={label} ref={box} onKeyDown={key}>
      {options.map((o) => (
        <button key={o.value} type="button" role="radio" aria-checked={o.value === value} data-v={o.value} disabled={o.disabled}
          tabIndex={o.value === stop ? 0 : -1} onClick={() => onChange(o.value)}>{o.label}</button>
      ))}
    </div>
  );
}
