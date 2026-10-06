import type { ReactNode } from "react";
import { Info } from "../ui";

export type Column<R> = {
  key: string;
  header: ReactNode;
  info?: ReactNode;                          // an (i) in the header
  numeric?: boolean;                         // right-aligned, in the header too
  rowHeader?: boolean;                       // the cell that names the row (a stock): read as the row's header
  cell: (row: R) => ReactNode;
};

/** The one table: a header row, right-aligned numbers, a hover row, and its own horizontal scroll box so a wide table
 * never makes the page scroll sideways. `label` names the table for screen readers. `rowNote` turns a row into its
 * first cell plus one line of words across the rest (a stock with no data). An empty list shows `empty` in one row. */
export function DataTable<R>({ label, columns, rows, rowKey, empty = "Nothing to show yet.", rowAttrs, rowNote }: {
  label: string; columns: Column<R>[]; rows: R[]; rowKey: (row: R) => string; empty?: ReactNode;
  rowAttrs?: (row: R) => Record<string, string>; rowNote?: (row: R) => ReactNode | undefined;
}) {
  return (
    <div className="k-tbl-wrap" role="region" aria-label={`${label}, scrolls sideways`} tabIndex={0}>
      <table className="k-table" aria-label={label}>
        <thead>
          <tr>{columns.map((c) => (
            <th key={c.key} scope="col" className={c.numeric ? "k-num" : undefined}>{c.header}{c.info && <Info label={`About ${typeof c.header === "string" ? c.header.toLowerCase() : "this column"}`}>{c.info}</Info>}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td className="k-empty-row" colSpan={columns.length}>{empty}</td></tr>}
          {rows.map((r) => {
            const note = rowNote?.(r);
            return (
              <tr key={rowKey(r)} {...rowAttrs?.(r)}>
                {columns.map((c, i) => {
                  if (note !== undefined && i > 0) return i === 1 ? <td key={c.key} colSpan={columns.length - 1} className="k-row-note">{note}</td> : null;
                  return c.rowHeader ? <th key={c.key} scope="row">{c.cell(r)}</th> : <td key={c.key} className={c.numeric ? "k-num" : undefined}>{c.cell(r)}</td>;
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
