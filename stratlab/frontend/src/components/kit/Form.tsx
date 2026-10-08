import { useEffect, useId, useRef, useState, type CSSProperties, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { Info } from "../ui";

/** A form as a grid: columns of at least 190px that wrap to the width, every box on one baseline. Fields go in, then
 * one FormActions row with the main button. */
export function FormGrid({ onSubmit, children, label, pair }: { onSubmit?: (e: FormEvent<HTMLFormElement>) => void; children: ReactNode; label?: string;
  /** Two boxes that belong side by side (two companies to compare): each takes half the row, not a narrow column. */
  pair?: boolean }) {
  return <form className={`k-form${pair ? " k-form-pair" : ""}`} onSubmit={onSubmit} aria-label={label}>{children}</form>;
}

type FieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "children"> & {
  label: string;                            // one line; anything longer goes in `info`
  info?: ReactNode;                         // the (i) next to the label
  infoLabel?: string;
  optional?: boolean;                       // adds "· optional" after the label
  unit?: string;                            // sits inside the box on the right: ₹, %, % / yr
  wide?: boolean;                           // spans the whole row
  id?: string;
  /** A control that is not a plain text box (a StockPicker, a select with className "k-input"): given the id for the label. */
  children?: ReactNode | ((id: string) => ReactNode);
  /** What's wrong with the value, said under the box (and to screen readers); the box gets a red edge. */
  error?: string | null;
  /** A short line under the box: the allowed range ("1 to 28"), a format. Hidden while there's an error. */
  hint?: string;
  /** What a good value looks like ("More than 0", "1 to 28"): said under the box only once the person has been in it (typed,
   * or left it) or has tried to submit the form, so a clean form isn't a list of rules. Hidden while there's an error. */
  rule?: string;
};

/** One labelled box in a FormGrid. The label stays on one line (an (i) holds the detail), "· optional" marks what can be
 * left empty, and a unit sits inside the box. `error` and `hint` sit under it (see lib/validate for the checks). */
export function Field({ label, info, infoLabel, optional, unit, wide, id, children, error, hint, rule, ...input }: FieldProps) {
  const auto = useId();
  const [touched, setTouched] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {      // trying to submit the form counts as having been in every box
    const form = root.current?.closest("form");
    if (!rule || !form) return;
    const on = () => setTouched(true);
    form.addEventListener("submit", on, true);
    return () => form.removeEventListener("submit", on, true);
  }, [rule]);
  const shown = hint ?? (rule && touched ? rule : undefined);
  const fid = id ?? auto;
  const msgId = `${fid}-msg`;
  const box = typeof children === "function" ? children(fid) : children ?? (
    <input {...input} id={fid} className={`k-input${error ? " bad" : ""}`} aria-invalid={error ? true : undefined}
      aria-describedby={error || shown ? msgId : undefined} />
  );
  return (
    <div ref={root} className={`k-field${wide ? " wide" : ""}`} onBlur={rule ? () => setTouched(true) : undefined} onInput={rule ? () => setTouched(true) : undefined}>
      <div className="k-label-row">
        <label htmlFor={fid}>{label}{optional && <span className="opt"> · optional</span>}{unit && !children && <span className="sr-only"> ({unit})</span>}</label>
        {info && <Info label={infoLabel ?? `About ${label.toLowerCase()}`}>{info}</Info>}
      </div>
      {unit && !children ? (
        <div className="k-input-unit" style={{ "--unit-w": `${Math.round(unit.length * 6.5) + 24}px` } as CSSProperties}>
          {box}<span className="u" aria-hidden="true">{unit}</span>
        </div>
      ) : box}
      {error ? <span id={msgId} className="k-field-msg bad" role="alert">{error}</span>
        : shown ? <span id={msgId} className="k-field-msg">{shown}</span> : null}
    </div>
  );
}

/** A label (and its (i)) over a control that brings its own name (a Seg, a search box): the same look as a Field's label. */
export function FieldGroup({ label, info, infoLabel, wide, children }: { label: string; info?: ReactNode; infoLabel?: string; wide?: boolean; children: ReactNode }) {
  return (
    <div className={`k-field${wide ? " wide" : ""}`} role="group" aria-label={label}>
      <div className="k-label-row"><span className="k-lbl">{label}</span>{info && <Info label={infoLabel ?? `About ${label.toLowerCase()}`}>{info}</Info>}</div>
      {children}
    </div>
  );
}

/** A dropdown for a short fixed list that is not worth tiles (a financial year, how often): the kit's input look with
 * a chevron. Put it in a Field (`{(id) => <Select id={id} .../>}`) so its label points at it. `small` for a table cell. */
export function Select({ id, value, onChange, options, label, disabled, small }: {
  id?: string; value: string | number; onChange: (v: string) => void; options: { value: string | number; label: string; disabled?: boolean }[];
  label?: string; disabled?: boolean; small?: boolean;
}) {
  return (
    <select id={id} className={`k-input${small ? " sm" : ""}`} value={value} aria-label={label} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>)}
    </select>
  );
}

/** The row under the fields: the main button on its own row, left-aligned, with an optional line beside it. */
export function FormActions({ children }: { children: ReactNode }) {
  return <div className="k-form-actions">{children}</div>;
}
