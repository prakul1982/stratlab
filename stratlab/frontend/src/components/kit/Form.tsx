import { useId, type CSSProperties, type FormEvent, type InputHTMLAttributes, type ReactNode } from "react";
import { Info } from "../ui";

/** A form as a grid: columns of at least 190px that wrap to the width, every box on one baseline. Fields go in, then
 * one FormActions row with the main button. */
export function FormGrid({ onSubmit, children, label }: { onSubmit?: (e: FormEvent<HTMLFormElement>) => void; children: ReactNode; label?: string }) {
  return <form className="k-form" onSubmit={onSubmit} aria-label={label}>{children}</form>;
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
};

/** One labelled box in a FormGrid. The label stays on one line (an (i) holds the detail), "· optional" marks what can be
 * left empty, and a unit sits inside the box. */
export function Field({ label, info, infoLabel, optional, unit, wide, id, children, ...input }: FieldProps) {
  const auto = useId();
  const fid = id ?? auto;
  const box = typeof children === "function" ? children(fid) : children ?? <input {...input} id={fid} className="k-input" />;
  return (
    <div className={`k-field${wide ? " wide" : ""}`}>
      <div className="k-label-row">
        <label htmlFor={fid}>{label}{optional && <span className="opt"> · optional</span>}{unit && !children && <span className="sr-only"> ({unit})</span>}</label>
        {info && <Info label={infoLabel ?? `About ${label.toLowerCase()}`}>{info}</Info>}
      </div>
      {unit && !children ? (
        <div className="k-input-unit" style={{ "--unit-w": `${Math.round(unit.length * 6.5) + 24}px` } as CSSProperties}>
          {box}<span className="u" aria-hidden="true">{unit}</span>
        </div>
      ) : box}
    </div>
  );
}

/** The row under the fields: the main button on its own row, left-aligned, with an optional line beside it. */
export function FormActions({ children }: { children: ReactNode }) {
  return <div className="k-form-actions">{children}</div>;
}
