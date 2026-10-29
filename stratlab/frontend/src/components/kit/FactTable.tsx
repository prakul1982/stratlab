import type { ReactNode } from "react";
import { DataTable, usePhone, type Column } from "./DataTable";

/** One row of a fact table: what it is, its figure, and (optionally) a note beside it. */
export type Fact = { id: string; k: ReactNode; v: ReactNode; n?: ReactNode };

/** A block of facts as a table (the owner's rule: tables, not tiles): the item in the first column, its figure beside it and, where any row has
 * one, a note column. The headers say what the columns are; `noteHead` names the third ("Note", "Rule", "Against NAV"). A row with nothing to say is
 * left out by the caller. On a phone the note goes under the item, so the table stays two columns across and fits the screen even where
 * it opens inside a fold (TABLE-SWEEP: a three-column table in a fund's fold pushed a 390px page sideways). */
export function FactTable({ label, rows, itemHead = "Item", figureHead = "Figure", noteHead = "Note", numeric = false }: {
  label: string; rows: Fact[]; itemHead?: string; figureHead?: string; noteHead?: string; numeric?: boolean;
}) {
  const phone = usePhone();
  const notes = rows.some((r) => r.n);
  const under = phone && notes;
  const cols: Column<Fact>[] = [
    { key: "k", header: itemHead, rowHeader: true, wrap: true, cell: (r) => <>{r.k}{under && r.n && <span className="k-sub-line">{r.n}</span>}</> },
    // a figure column stays as wide as its figures (TABLE-SWEEP: the wrap's 160px floor pushed a two-column table off a 360px phone)
    { key: "v", header: figureHead, wrap: !numeric, numeric, cell: (r) => r.v },
    ...(notes && !under ? [{ key: "n", header: noteHead, wrap: true, cell: (r: Fact) => (r.n ? <span className="k-note">{r.n}</span> : "") } as Column<Fact>] : []),
  ];
  return <div className="k-facts"><DataTable label={label} rows={rows} rowKey={(r) => r.id} columns={cols} /></div>;
}
