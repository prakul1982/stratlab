import type { CSSProperties } from "react";

/** A slider on the kit's track and thumb, with its value in words beside it ("4 weeks"). Put it in a Field
 * (`{(id) => <Range id={id} .../>}`) so its label points at it. */
export function Range({ id, label, value, min, max, step = 1, onChange, valueText, disabled, testId }: {
  id?: string; label?: string; value: number; min: number; max: number; step?: number; onChange: (v: number) => void;
  valueText?: string; disabled?: boolean; testId?: string;
}) {
  const fill = max > min ? ((Math.min(max, Math.max(min, value)) - min) / (max - min)) * 100 : 0;
  return (
    <span className="k-range-row">
      <input id={id} className="k-range" type="range" min={min} max={max} step={step} value={value} disabled={disabled} aria-label={label}
        aria-valuetext={valueText} data-testid={testId} style={{ "--fill": `${fill}%` } as CSSProperties} onChange={(e) => onChange(+e.target.value)} />
      {valueText && <span className="k-range-value" aria-hidden="true">{valueText}</span>}
    </span>
  );
}
