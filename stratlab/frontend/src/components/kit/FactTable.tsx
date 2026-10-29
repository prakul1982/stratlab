import type { ReactNode } from "react";
import { DataTable, type Column } from "./DataTable";

/** One row of a fact table: what it is, its figure, and (optionally) a note beside it. */
export type Fact = { id: string; k: ReactNode; v: ReactNode; n?: ReactNode };

/** A block of facts as a table (the owner's rule: tables, not tiles): the item in the first column, its figure beside it and, where any row has
 * one, a note column. The headers say what the columns are; `noteHead` names the third ("Note", "Rule", "Against NAV"). A row with nothing to say is
 * left out by the caller. On a phone the table is a list of cards, as every table here is. */
export function FactTable({ label, rows, itemHead = "Item", figureHead = "Figure", noteHead = "Note", numeric = false }: {
  label: string; rows: Fact[]; itemHead?: string; figureHead?: string; noteHead?: string; numeric?: boolean;
}) {
  const notes = rows.some((r) => r.n);
  const cols: Column<Fact>[] = [
    { key: "k", header: itemHead, rowHeader: true, wrap: true, cell: (r) => r.k },
    { key: "v", header: figureHead, wrap: true, numeric, cell: (r) => r.v },
    ...(notes ? [{ key: "n", header: noteHead, wrap: true, cell: (r: Fact) => (r.n ? <span className="k-note">{r.n}</span> : "") } as Column<Fact>] : []),
  ];
  return <DataTable label={label} rows={rows} rowKey={(r) => r.id} columns={cols} />;
}
