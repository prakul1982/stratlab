import type { ReactNode } from "react";
import { FactTable } from "./FactTable";

/** The answer under a calculator: a line saying what it is, the big result, one line of context, an optional split bar
 * (your part and the other part) and rows of the working. The `highlight` row is the one to read last. Put it right
 * below the form's button; `testId` and `live` let tests and screen readers find it when it appears. */
export function ResultBlock({ label, big, note, split, rows, rowsLabel = "How it is worked out", testId }: {
  label: ReactNode; big: ReactNode; note?: ReactNode;
  split?: { aLabel: string; aValue: string; aPct: number; bLabel: string; bValue: string };
  rows?: { label: ReactNode; value: ReactNode; highlight?: boolean }[]; testId?: string;
  /** The working table's name for screen readers. */
  rowsLabel?: string;
}) {
  const a = split ? Math.max(0, Math.min(100, split.aPct)) : 0;
  return (
    <div className="k-result" aria-live="polite" data-testid={testId}>
      <div className="k-result-head">
        <span className="k-stat-k">{label}</span>
        <span className="k-result-big">{big}</span>
        {note && <span className="k-stat-d">{note}</span>}
      </div>
      {split && (
        <>
          <div className="k-split" role="img" aria-label={`${split.aLabel} ${split.aValue}, ${split.bLabel} ${split.bValue}`}><span style={{ width: `${a}%` }} /><span style={{ width: `${100 - a}%` }} /></div>
          <div className="k-legend"><span><i className="me" />{split.aLabel} <b>{split.aValue}</b></span><span><i className="br" />{split.bLabel} <b>{split.bValue}</b></span></div>
        </>
      )}
      {/* the working as a table, item and amount (TABLE-SWEEP, owner 29 Oct: "wherever you can, just make a table"); the row to read
          last in bold */}
      {rows && rows.length > 0 && (
        <FactTable label={rowsLabel} itemHead="Item" figureHead="Amount" numeric
          rows={rows.map((r, i) => ({ id: String(i), k: r.highlight ? <b>{r.label}</b> : r.label, v: r.highlight ? <b>{r.value}</b> : r.value }))} />
      )}
    </div>
  );
}
