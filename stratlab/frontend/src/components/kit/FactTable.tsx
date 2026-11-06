import type { ReactNode } from "react";
import { DataTable, sparseNotes, usePhone, type Column } from "./DataTable";

/** One row of a fact table: what it is, its figure, and (optionally) a note beside it. */
export type Fact = { id: string; k: ReactNode; v: ReactNode; n?: ReactNode };

/** A block of facts as a table (the owner's rule: tables, not tiles): the item in the first column, its figure beside it and, where any row has
 * one, a note column. The headers say what the columns are; `noteHead` names the third ("Note", "Rule", "Against NAV"). A row with nothing to say is
 * left out by the caller. On a phone the table is a list of cards, as every table here is; with `noteUnder` the note goes under the item
 * there instead, so the table stays two columns across and fits even where it opens inside a fold (TABLE-SWEEP: a three-column table in
 * a fund's fold pushed a 390px page sideways). */
export function FactTable({ label, rows, itemHead = "Item", figureHead = "Figure", noteHead = "Note", numeric = false, noteUnder = false, across = false }: {
  label: string; rows: Fact[]; itemHead?: string; figureHead?: string; noteHead?: string; numeric?: boolean; noteUnder?: boolean;
  /** A few totals (up to four) read across one row, each under its own heading with its note under the figure, instead of a two-column
   * table 1,000 px wide holding one to three rows (LIVE5 partial: Net worth's "Where you stand"). A phone keeps the rows. */
  across?: boolean;
}) {
  const phone = usePhone();
  if (across && !phone && rows.length > 0 && rows.length <= 4) {
    const cols: Column<{ id: string }>[] = rows.map((r) => ({ key: r.id, header: <>{r.k}</>, csvHeader: typeof r.k === "string" ? r.k : r.id, numeric,
      cell: () => <span className="k-facts-cell">{r.v}{r.n && <span className="k-sub-line">{r.n}</span>}</span> }));
    return <div className="k-facts k-facts-across"><DataTable label={label} rows={[{ id: "now" }]} rowKey={(r) => r.id} columns={cols} /></div>;
  }
  const notes = rows.some((r) => r.n);
  // a note only some rows have goes under the item on every screen, not in a column blank in half its rows (LIVE3-015, LIVE3-021)
  const under = notes && ((noteUnder && phone) || sparseNotes(rows.filter((r) => r.n).length, rows.length));
  const cols: Column<Fact>[] = [
    { key: "k", header: itemHead, rowHeader: true, wrap: true, cell: (r) => <>{r.k}{under && r.n && <span className="k-sub-line">{r.n}</span>}</> },
    // a figure column stays as wide as its figures (TABLE-SWEEP: the wrap's 160px floor pushed a two-column table off a 360px phone)
    { key: "v", header: figureHead, wrap: !numeric, numeric, cell: (r) => r.v },
    ...(notes && !under ? [{ key: "n", header: noteHead, wrap: true, cell: (r: Fact) => (r.n ? <span className="k-note">{r.n}</span> : "") } as Column<Fact>] : []),
  ];
  return <div className="k-facts"><DataTable label={label} rows={rows} rowKey={(r) => r.id} columns={cols} /></div>;
}
